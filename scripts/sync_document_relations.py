
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

from import_pg import Cloud, check, validate_relations


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

    for doc in docs:
        meta = doc["meta"]
        if meta["type"] != "hardware_model":
            continue

        manuals = meta.get("manuals", [])
        check(
            isinstance(manuals, list),
            f"{meta['id']}: manuals muss eine Liste sein",
        )

        check(
            len(manuals) == len(set(
                validate_manual_path(p) for p in manuals
            )),
            f"{meta['id']}: Doppelte Handbuchreferenz",
        )

        for manual in manuals:
            relative = validate_manual_path(manual)
            requested.append((
                meta["id"],
                root + relative,
            ))

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

            for model_key, pdf_path in requested:
                cur.execute("""
                    SELECT cm.id
                    FROM hw.component_model cm
                    JOIN knowledge.document d
                      ON d.id = cm.document_id
                    WHERE d.document_key = %s
                      AND d.is_active = true
                      AND d.origin = 'own'
                """, (model_key,))
                models = cur.fetchall()

                cur.execute("""
                    SELECT id, document_key
                    FROM knowledge.document
                    WHERE nextcloud_path = %s
                      AND document_kind = 'manual'
                      AND origin = 'own'
                      AND is_active = true
                """, (pdf_path,))
                manuals = cur.fetchall()

                if len(models) != 1 or len(manuals) != 1:
                    errors += 1
                    print(
                        f"ERROR {model_key} -> {pdf_path} "
                        f"(Modelle={len(models)}, PDFs={len(manuals)})"
                    )
                    continue

                model_id = models[0][0]
                document_id, manual_key = manuals[0]

                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM knowledge.document_component
                        WHERE document_id = %s
                          AND component_model_id = %s
                          AND relation = 'manual'
                    )
                """, (document_id, model_id))

                exists = cur.fetchone()[0]
                status = "EXISTS" if exists else "PLANNED"

                if not exists:
                    pending.append((document_id, model_id))

                print(
                    f"{status:7} {manual_key} "
                    f"-> {model_key}"
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

                for document_id, model_id in pending:
                    cur.execute("""
                        INSERT INTO knowledge.document_component
                            (document_id, component_model_id, relation)
                        VALUES (%s, %s, 'manual')
                        ON CONFLICT DO NOTHING
                    """, (document_id, model_id))

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
