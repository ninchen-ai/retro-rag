#!/usr/bin/env python3
"""Nextcloud Markdown -> PDF-Handbuchbeziehungen; nur Dry-Run."""

import argparse
from genericpath import exists
import getpass
import os
import sys
from pathlib import PurePosixPath
from urllib.parse import unquote

import psycopg

from scripts.import_pg import Cloud, check, validate_relations


def validate_manual_path(value):
    check(isinstance(value, str), "Handbuchpfad muss Text sein")
    check(value == value.strip(), "Leerzeichen am Pfadrand")
    check(value != "", "Leerer Handbuchpfad")
    check("\\" not in value, "Backslash im Handbuchpfad")

    path = PurePosixPath(value)
    check(
        not path.is_absolute()
        and all(part not in (".", "..", "") for part in value.split("/"))
        and value.lower().endswith(".pdf"),
        f"Ungültiger relativer PDF-Pfad: {value}",
    )
    return value

def normalize_manual_entry(entry):
    """Vereinheitlicht alte und neue PDF-Referenzen."""

    if isinstance(entry, str):
        return {
            "path": validate_manual_path(entry),
            "relation": "manual",
            "applies_to": "mainboard",
            "chip": None,
        }

    check(
        isinstance(entry, dict),
        "Handbuchreferenz muss Text oder YAML-Objekt sein",
    )

    path = validate_manual_path(entry.get("path"))
    relation = entry.get("relation")
    applies_to = entry.get("applies_to")

    check(
        (relation, applies_to) in {
            ("manual", "mainboard"),
            ("datasheet", "chip"),
            ("reference", "chip"),
            ("errata", "chip"),
        },
        f"Ungültige Dokumentbeziehung: {relation}/{applies_to}",
    )

    chip = entry.get("chip")

    if applies_to == "chip":
        check(
            isinstance(chip, str) and bool(chip.strip()),
            f"Chip-Angabe fehlt: {path}",
        )
        check(chip == chip.strip(), "Leerzeichen am Chipnamen")
    else:
        check(chip is None, "Mainboard-Handbuch darf keinen Chip angeben")

    return {
        "path": path,
        "relation": relation,
        "applies_to": applies_to,
        "chip": chip,
    }

def main():
    parser = argparse.ArgumentParser(
        description="Prüft Handbuchverknüpfungen aus Nextcloud-Markdown"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--user", default="nina")
    parser.add_argument("--folder", default="Retro-Computing")
    parser.add_argument(
    "--apply",
    action="store_true",
    help="Validierte Handbuchbeziehungen in PostgreSQL speichern",
    )
    args = parser.parse_args()

    nc_password = (
        os.environ.get("NEXTCLOUD_APP_PASSWORD")
        or getpass.getpass("Nextcloud-App-Passwort: ")
    )
    db_password = (
        os.environ.get("RETRO_RAG_READER_PASSWORD")
        or getpass.getpass("PostgreSQL-Lesepasswort: ")
    )

    cloud = Cloud(args.url, args.user, nc_password, args.folder)
    docs = cloud.listing()
    check(bool(docs), "Keine Markdown-Dokumente gefunden")
    validate_relations(docs)

    # Exakt denselben Nextcloud-Pfadstil wie der Importer verwenden.
    root = unquote(cloud.prefix)
    requested = []
    seen_relations = set()

    for doc in docs:
        meta = doc["meta"]

        if meta["type"] != "hardware_model":
            continue

        manuals = meta.get("manuals", [])

        check(
            isinstance(manuals, list),
            f"{meta['id']}: manuals muss eine Liste sein",
        )

        chips = meta.get("chips", [])

        for raw_entry in manuals:
            entry = normalize_manual_entry(raw_entry)

            chip_manufacturer = None
            chip_role = None

            if entry["applies_to"] == "chip":
                matches = [
                    chip for chip in chips
                    if chip["name"] == entry["chip"]
                ]

                check(
                    len(matches) == 1,
                    f"{meta['id']}: Chip {entry['chip']} "
                    "nicht eindeutig im Mainboard definiert",
                )

                chip_manufacturer = matches[0]["manufacturer"]
                chip_role = matches[0]["role"]

            identity = (
                meta["id"],
                entry["path"],
                entry["relation"],
                entry["applies_to"],
                chip_manufacturer,
                entry["chip"],
            )

            check(
                identity not in seen_relations,
                f"Doppelte Dokumentreferenz: {identity}",
            )
            seen_relations.add(identity)

            requested.append({
                "model_key": meta["id"],
                "pdf_path": root + entry["path"],
                "relation": entry["relation"],
                "applies_to": entry["applies_to"],
                "chip_manufacturer": chip_manufacturer,
                "chip": entry["chip"],
                "chip_role": chip_role,
            })

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_reader",
        password=db_password,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            print("\n===== GEPLANTE HANDBUCHBEZIEHUNGEN =====")

            errors = 0
            pending = []

            for entry in requested:
                model_key = entry["model_key"]
                pdf_path = entry["pdf_path"]
                relation = entry["relation"]
                applies_to = entry["applies_to"]

                # PDF eindeutig auflösen.
                cur.execute("""
                    SELECT id, document_key
                    FROM knowledge.document
                    WHERE nextcloud_path = %s
                      AND document_kind = 'manual'
                      AND origin = 'own'
                      AND is_active = true
                """, (pdf_path,))

                manuals = cur.fetchall()

                if len(manuals) != 1:
                    errors += 1
                    print(
                        f"ERROR {model_key} -> {pdf_path} "
                        f"(PDFs={len(manuals)})"
                    )
                    continue

                document_id, manual_key = manuals[0]

                # Mainboard und Chipbeziehungen unterschiedlich auflösen.
                if applies_to == "mainboard":
                    cur.execute("""
                        SELECT cm.id
                        FROM hw.component_model cm
                        JOIN knowledge.document d
                          ON d.id = cm.document_id
                        WHERE d.document_key = %s
                          AND d.origin = 'own'
                          AND d.is_active = true
                    """, (model_key,))

                    targets = cur.fetchall()

                    if len(targets) != 1:
                        errors += 1
                        print(f"ERROR Mainboard: {model_key}")
                        continue

                    target_id = targets[0][0]

                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1
                            FROM knowledge.document_component
                            WHERE document_id = %s
                              AND component_model_id = %s
                              AND relation = %s
                        )
                    """, (document_id, target_id, relation))

                else:
                    # Chip muss zum angegebenen Mainboard gehören.
                    cur.execute("""
                        SELECT c.id
                        FROM hw.chip c
                        JOIN hw.manufacturer m
                          ON m.id = c.manufacturer_id
                        JOIN hw.component_chip cc
                          ON cc.chip_id = c.id
                        JOIN hw.component_model cm
                          ON cm.id = cc.component_model_id
                        JOIN knowledge.document d
                          ON d.id = cm.document_id
                        WHERE d.document_key = %s
                          AND d.origin = 'own'
                          AND d.is_active = true
                          AND m.name = %s
                          AND c.name = %s
                          AND cc.role = %s
                    """, (
                        model_key,
                        entry["chip_manufacturer"],
                        entry["chip"],
                        entry["chip_role"],
                    ))

                    targets = cur.fetchall()

                    if len(targets) != 1:
                        errors += 1
                        print(
                            f"ERROR Chip: {model_key} -> "
                            f"{entry['chip']}"
                        )
                        continue

                    target_id = targets[0][0]

                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1
                            FROM knowledge.document_chip
                            WHERE document_id = %s
                              AND chip_id = %s
                              AND relation = %s
                        )
                    """, (document_id, target_id, relation))

                exists = cur.fetchone()[0]
                status = "EXISTS" if exists else "PLANNED"

                if not exists:
                    pending.append((
                        applies_to,
                        document_id,
                        target_id,
                        relation,
                    ))

                target_name = (
                    model_key
                    if applies_to == "mainboard"
                    else f"{entry['chip_manufacturer']} {entry['chip']}"
                )

                print(
                    f"{status:7} {manual_key} "
                    f"-> {target_name} ({relation})"
                )
    if errors:
        print(
            f"\nABBRUCH: {errors} Referenzen konnten nicht "
            "eindeutig aufgelöst werden."
        )
        print("Keine Datenbankänderungen.")
        return 1

    if not args.apply:
        print(
            f"\nDRY-RUN: {len(requested)} Referenzen, "
            f"{len(pending)} neue Beziehungen. "
            "Keine Datenbankänderungen."
        )
        return 0

    if not pending:
        print("\nKeine Änderungen erforderlich.")
        return 0

    print(f"\nAPPLY: {len(pending)} Beziehungen werden angelegt.")

    ingest_password = (
        os.environ.get("PGPASSWORD")
        or getpass.getpass("PostgreSQL-Importpasswort: ")
    )

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_ingest",
        password=ingest_password,
        connect_timeout=10,
    ) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT current_user, current_database()
                """)
                role, database = cur.fetchone()

                check(
                    role == "retro_rag_ingest"
                    and database == "retro_rag",
                    "Falsche Datenbank oder Benutzerrolle",
                )

                for applies_to, document_id, target_id, relation in pending:

                    if applies_to == "mainboard":
                        cur.execute("""
                            INSERT INTO knowledge.document_component
                                (document_id, component_model_id, relation)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (
                            document_id,
                            target_id,
                            relation,
                        ))

                    elif applies_to == "chip":
                        cur.execute("""
                            INSERT INTO knowledge.document_chip
                                (document_id, chip_id, relation)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (
                            document_id,
                            target_id,
                            relation,
                        ))

                    else:
                        raise ValueError(
                            f"Unbekannter Beziehungstyp: {applies_to}"
                        )

    print(
        f"COMMIT: Bis zu {len(pending)} neue "
        "Handbuchbeziehungen synchronisiert."
    )
    return 0



if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
