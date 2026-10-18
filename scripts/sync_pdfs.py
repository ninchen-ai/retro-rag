#!/usr/bin/env python3
"""Nextcloud-PDF-Synchronisierung mit vorsichtiger Lebenszyklusverwaltung."""

import argparse
import base64
import getpass
import os
import psycopg
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from collections import deque
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

DAV = {"d": "DAV:", "oc": "http://owncloud.org/ns"}


def discover(url, user, password, folder):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ungültige Nextcloud-URL")
    if parsed.scheme == "http" and parsed.hostname not in (
        "127.0.0.1", "localhost", "::1"
    ):
        raise ValueError("HTTP ist nur über localhost erlaubt")

    base = url.rstrip("/")
    prefix = (
        "/remote.php/dav/files/"
        + quote(user, safe="")
        + "/"
        + quote(folder.strip("/"), safe="/")
        + "/"
    )

    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {
        "Authorization": "Basic " + auth,
        "Depth": "1",
        "Content-Type": "application/xml",
    }
    propfind = b"""<?xml version="1.0"?>
    <d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
      <d:prop>
        <oc:fileid/>
        <d:getcontentlength/>
        <d:getetag/>
        <d:getlastmodified/>
        <d:resourcetype/>
      </d:prop>
    </d:propfind>"""

    queue = deque([prefix])
    visited = set()
    files = []

    while queue:
        directory = queue.popleft()
        if directory in visited:
            continue
        visited.add(directory)

        request = Request(
            base + directory,
            data=propfind,
            headers=headers,
            method="PROPFIND",
        )

        with urlopen(request, timeout=30) as response:
            if response.status != 207:
                raise RuntimeError(
                    f"WebDAV PROPFIND: HTTP {response.status} für {directory}"
                )
            xml = ET.fromstring(response.read())

        if xml.tag != "{DAV:}multistatus":
            raise RuntimeError(
                f"Ungültige WebDAV-Antwort für {directory}"
            )

        responses = xml.findall("d:response", DAV)

        if not responses:
            raise RuntimeError(
                f"Leere WebDAV-Verzeichnisantwort für {directory}"
            )

        for item in responses:
            href = item.findtext("d:href", namespaces=DAV)
            if not href:
                continue

            path = urlsplit(href).path
            clean = unquote(path)
            root = unquote(prefix)

            if clean.rstrip("/") == root.rstrip("/"):
                continue

            if not clean.startswith(root):
                raise ValueError("WebDAV-Pfad außerhalb von Retro-Computing")

            is_dir = item.find(
                ".//d:resourcetype/d:collection", DAV
            ) is not None

            if is_dir:
                queue.append(path if path.endswith("/") else path + "/")
                continue

            if not clean.lower().endswith(".pdf"):
                continue

            file_id = item.findtext(".//oc:fileid", namespaces=DAV)
            size = item.findtext(".//d:getcontentlength", namespaces=DAV)
            etag = item.findtext(".//d:getetag", namespaces=DAV)
            modified = item.findtext(".//d:getlastmodified", namespaces=DAV)

            if not file_id or not file_id.strip():
                raise ValueError(f"Nextcloud-Datei-ID fehlt: {clean}")

            files.append({
                "path": clean,
                "fileid": file_id.strip(),
                "size": int(size) if size else None,
                "etag": etag,
                "modified": modified,
            })

    return sorted(files, key=lambda f: f["path"])

def check_webdav_path(base, path, user, password, expected_file_id=None, return_status=False,):
    """Prüft einen gespeicherten WebDAV-Pfad ohne Datei-Download."""

    parsed = urlsplit(base)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ungültige Nextcloud-URL")

    if parsed.scheme == "http" and parsed.hostname not in (
        "127.0.0.1", "localhost", "::1"
    ):
        raise ValueError("HTTP ist nur über localhost erlaubt")

    prefix = f"/remote.php/dav/files/{quote(user, safe='')}/"

    if not unquote(path).startswith(unquote(prefix)):
        raise ValueError("WebDAV-Pfad außerhalb des Benutzerverzeichnisses")

    # Gespeicherte Pfade können bereits URL-kodiert sein.
    encoded_path = quote(unquote(path), safe="/")

    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    request = Request(
        base.rstrip("/") + encoded_path,
        data=(
            b'<d:propfind xmlns:d="DAV:" '
            b'xmlns:oc="http://owncloud.org/ns">'
            b'<d:prop><d:resourcetype/><oc:fileid/></d:prop>'
            b'</d:propfind>'
        ),
        headers={
            "Authorization": "Basic " + auth,
            "Depth": "0",
            "Content-Type": "application/xml",
        },
        method="PROPFIND",
    )

    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 207:
                raise RuntimeError(
                    f"Unerwartete WebDAV-Antwort: HTTP {response.status}"
                )

            xml = ET.fromstring(response.read())

            if xml.tag != "{DAV:}multistatus":
                raise RuntimeError("Ungültige WebDAV-Antwort")

            responses = xml.findall("d:response", DAV)
            if len(responses) != 1:
                raise RuntimeError("Unerwartete Anzahl WebDAV-Dateiantworten")

            file_id = responses[0].findtext(".//oc:fileid", namespaces=DAV)
            if not file_id:
                raise RuntimeError("Nextcloud-Datei-ID fehlt")

            if (
                expected_file_id is not None
                and file_id.strip() != str(expected_file_id)
            ):
                status = "MISMATCH"
            else:
                status = "MATCH"

            return status if return_status else status == "MATCH"

    except HTTPError as exc:
        if exc.code == 404:
            return "MISSING" if return_status else False
        raise

def get_known_pdfs(password):
    """Read existing PDF records using the read-only database role."""
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_reader",
        password=password,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        d.id,
                        d.is_active,
                        d.nextcloud_file_id,
                        d.document_key,
                        d.nextcloud_path,
                        s.etag,
                        s.file_size,
                        pm.page_count,
                        (
                            SELECT COUNT(*)
                            FROM rag.chunk c
                            WHERE c.document_id = d.id
                                AND c.embedding_model = 'nomic-embed-text'
                        ) AS chunk_count
                    FROM knowledge.document d
                    LEFT JOIN knowledge.pdf_sync_state s
                        ON s.document_id = d.id
                    LEFT JOIN knowledge.pdf_metadata pm
                        ON pm.document_id = d.id
                    WHERE d.document_kind = 'manual'
                        AND d.origin = 'own'
                """)
                rows = cur.fetchall()

        return {
            str(file_id): {
                "id": document_id,
                "fileid": str(file_id),
                "is_active": is_active,
                "document_key": key,
                "path": path,
                "etag": etag,
                "size": size,
                "page_count": page_count,
                "chunk_count": chunk_count,
            }
            for document_id, is_active, file_id, key, path, etag, size, page_count, chunk_count in rows
        }

def missing_grace_period_elapsed(first_missing_at, now=None):
    """Prüft, ob die erste Fehlmeldung mindestens 10 Minuten zurückliegt."""
    if now is None:
        now = datetime.now(timezone.utc)

    return now - first_missing_at >= timedelta(minutes=10)

def get_missing_state(document_id, password):
    """Liest den bisherigen Fehlstatus einer PDF."""

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_ingest",
        password=password,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT first_missing_at, last_checked_at
                FROM knowledge.pdf_missing_state
                WHERE document_id = %s
            """, (document_id,))

            return cur.fetchone()

def record_missing_pdf(document_id, password):
    """Merkt die erste bestätigte Abwesenheit einer PDF vor."""

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_ingest",
        password=password,
        connect_timeout=10,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge.pdf_missing_state (
                    document_id,
                    first_missing_at,
                    last_checked_at
                )
                VALUES (%s, now(), now())
                ON CONFLICT (document_id)
                DO UPDATE SET
                    last_checked_at = now()
            """, (document_id,))

def clear_missing_pdf(document_id, password):
    """Entfernt die Fehlvormerkung einer wiedergefundenen PDF."""

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_ingest",
        password=password,
        connect_timeout=10,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM knowledge.pdf_missing_state
                WHERE document_id = %s
            """, (document_id,))

def update_missing_lifecycle(document_id, password, dry_run=True):
    """Verarbeitet eine bestätigte Abwesenheit atomar."""

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_ingest",
        password=password,
        connect_timeout=10,
    ) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT is_active
                    FROM knowledge.document
                    WHERE id = %s
                    FOR UPDATE
                """, (document_id,))

                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("Dokument nicht gefunden")

                is_active = row[0]

                cur.execute("""
                    SELECT
                        first_missing_at,
                        now() AS checked_at
                    FROM knowledge.pdf_missing_state
                    WHERE document_id = %s
                """, (document_id,))

                missing = cur.fetchone()

                if not is_active:
                    result = "ALREADY_INACTIVE"

                elif missing is None:
                    cur.execute("""
                        INSERT INTO knowledge.pdf_missing_state (
                            document_id,
                            first_missing_at,
                            last_checked_at
                        )
                        VALUES (%s, now(), now())
                    """, (document_id,))
                    result = "PENDING"

                else:
                    first_missing_at, checked_at = missing

                    if checked_at - first_missing_at < timedelta(minutes=10):
                        cur.execute("""
                            UPDATE knowledge.pdf_missing_state
                            SET last_checked_at = now()
                            WHERE document_id = %s
                        """, (document_id,))
                        result = "WAITING"
                    else:
                        cur.execute("""
                            UPDATE knowledge.pdf_missing_state
                            SET last_checked_at = now()
                            WHERE document_id = %s
                        """, (document_id,))

                        cur.execute("""
                            UPDATE knowledge.document
                            SET is_active = false
                            WHERE id = %s
                              AND is_active = true
                        """, (document_id,))

                        result = "DEACTIVATED"

            if dry_run:
                conn.rollback()
            else:
                conn.commit()

            return result

        except Exception:
            conn.rollback()
            raise


def validate_pdf_index(document_id, password):
    """Prüft PDF-Metadaten und eine lückenlose Embedding-Sequenz."""

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_reader",
        password=password,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    pm.page_count,
                    COUNT(c.id),
                    MIN(c.chunk_index),
                    MAX(c.chunk_index)
                FROM knowledge.pdf_metadata pm
                LEFT JOIN rag.chunk c
                    ON c.document_id = pm.document_id
                   AND c.embedding_model = 'nomic-embed-text'
                WHERE pm.document_id = %s
                GROUP BY pm.page_count
            """, (document_id,))

            row = cur.fetchone()
            if row is None:
                return False

            page_count, chunk_count, first_index, last_index = row

            return (
                page_count > 0
                and chunk_count > 0
                and first_index == 0
                and last_index == chunk_count - 1
            )

def pdf_metadata_matches(item, existing):
    """Vergleicht die aktuelle Nextcloud-PDF mit ihrem DB-Synchronisierungsstand."""

    if existing is None:
        return False

    return (
        str(item["fileid"]) == str(existing.get("fileid"))
        and unquote(item["path"]) == unquote(existing["path"])
        and bool(existing["etag"])
        and item["etag"] == existing["etag"]
        and item["size"] is not None
        and item["size"] == existing["size"]
        and existing["page_count"] is not None
        and existing["page_count"] > 0
        and existing["chunk_count"] > 0
    )

def pdf_ready_for_reactivation(item, existing, reader_password):
    """Prüft, ob der gespeicherte PDF-Index zur Nextcloud-Datei passt."""

    if not pdf_metadata_matches(item, existing):
        return False

    return validate_pdf_index(
        existing["id"],
        reader_password,
    )

def reactivate_pdf(
    document_id, password, expected_etag, expected_size,
    expected_file_id, expected_path, dry_run=True
):
    """Reaktiviert ein validiertes PDF und entfernt seine Fehlvormerkung."""

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_ingest",
        password=password,
        connect_timeout=10,
    ) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT is_active, nextcloud_file_id, nextcloud_path
                    FROM knowledge.document
                    WHERE id = %s
                    FOR UPDATE
                """, (document_id,))

                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("Dokument nicht gefunden")
                was_active, stored_file_id, stored_path = row
                if (
                    str(stored_file_id) != str(expected_file_id)
                    or unquote(stored_path or "") != unquote(expected_path)
                ):
                    raise RuntimeError("Reaktivierung abgebrochen: Datei-ID/Pfad verändert")

                cur.execute("""
                    SELECT etag, file_size
                    FROM knowledge.pdf_sync_state
                    WHERE document_id = %s
                    FOR UPDATE
                """, (document_id,))

                sync_row = cur.fetchone()

                if (
                    sync_row is None
                    or sync_row[0] != expected_etag
                    or sync_row[1] != expected_size
                ):
                    raise RuntimeError(
                        "Reaktivierung abgebrochen: PDF-Version stimmt nicht überein"
                    )

                # Auch unter Dokument-Lock auf vollständigen Index prüfen.
                cur.execute("""
                    SELECT pm.page_count, COUNT(c.id),
                           MIN(c.chunk_index), MAX(c.chunk_index)
                    FROM knowledge.pdf_metadata pm
                    LEFT JOIN rag.chunk c
                      ON c.document_id = pm.document_id
                     AND c.embedding_model = 'nomic-embed-text'
                    WHERE pm.document_id = %s
                    GROUP BY pm.page_count
                """, (document_id,))
                index_row = cur.fetchone()
                if not index_row or not (
                    index_row[0] > 0 and index_row[1] > 0
                    and index_row[2] == 0
                    and index_row[3] == index_row[1] - 1
                ):
                    raise RuntimeError("Reaktivierung abgebrochen: PDF-Index ungültig")

                cur.execute("""
                    UPDATE knowledge.document
                    SET is_active = true
                    WHERE id = %s
                      AND is_active = false
                """, (document_id,))

                cur.execute("""
                    DELETE FROM knowledge.pdf_missing_state
                    WHERE document_id = %s
                """, (document_id,))

                result = "ALREADY_ACTIVE" if was_active else "REACTIVATED"

            if dry_run:
                conn.rollback()
            else:
                conn.commit()

            return result

        except Exception:
            conn.rollback()
            raise

def import_document(item, args):
    """Import a single PDF through the existing importer."""

    prefix = f"/remote.php/dav/files/{args.user}/"
    path = item["path"]

    if not path.startswith(prefix):
        raise ValueError("PDF-Pfad außerhalb des Nextcloud-Benutzers")

    relative_path = path[len(prefix):]

    if (
        not relative_path.startswith(args.folder.strip("/") + "/")
        or not relative_path.lower().endswith(".pdf")
        or ".." in relative_path.split("/")
    ):
        raise ValueError("Ungültiger PDF-Pfad")

    importer = Path(__file__).resolve().with_name("import_pdf.py")

    command = [
        sys.executable,
        str(importer),
        "--file", relative_path,
        "--cloud-url", args.url,
        "--cloud-user", args.user,
        "--apply",
    ]

    print(f"IMPORT: {relative_path}", flush=True)

    result = subprocess.run(
        command,
        check=False,
        timeout=1800,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"PDF-Import fehlgeschlagen: {relative_path}"
        )

def pdf_is_unchanged(item, existing):
    """Prüft, ob eine PDF gemäß dem gespeicherten Sync-Stand unverändert ist."""

    return bool(
        existing
        and unquote(existing["path"]) == unquote(item["path"])
        and existing["etag"] == item["etag"]
        and existing["size"] == item["size"]
        and existing["page_count"] is not None
        and existing["chunk_count"] > 0
    )

def main():
    parser = argparse.ArgumentParser(
        description="Retro-RAG: PDF-Dateien in Nextcloud finden"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--user", default="nina")
    parser.add_argument("--folder", default="Retro-Computing")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Neue und geänderte PDFs automatisch importieren"
    )
    args = parser.parse_args()

    password = os.getenv("NEXTCLOUD_APP_PASSWORD")
    if not password:
        password = getpass.getpass("Nextcloud-App-Passwort: ")

    files = discover(args.url, args.user, password, args.folder)
    db_password = os.getenv("RETRO_RAG_READER_PASSWORD")
    if not db_password:
        db_password = getpass.getpass("PostgreSQL-Reader-Passwort: ")

    known = get_known_pdfs(db_password)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"PDF-Synchronisierung: {mode}\n")

    new_count = 0
    known_count = 0

    for item in files:
        existing = known.get(item["fileid"])

        if existing is None:
            status = "NEW"
            new_count += 1

        elif (
            not existing["etag"]
            or existing["size"] is None
            or existing["page_count"] is None
            or existing["chunk_count"] == 0
        ):
            status = "CHECK"
            known_count += 1

        elif unquote(existing["path"]) != unquote(item["path"]):
            status = "CHANGED"
            known_count += 1

        elif (
            existing["etag"] == item["etag"]
            and existing["size"] == item["size"]
        ):
            status = "UNCHANGED"
            known_count += 1

        else:
            status = "CHANGED"
            known_count += 1

        print(
            f"{status:<5} {item['fileid']:>8}  "
            f"{item['size']} Bytes  "
            f"{item['path']}"
        )

    # Gespeicherte PDFs erkennen, die beim WebDAV-Scan fehlen.
    # Nur unterhalb des synchronisierten Ordners prüfen.
    root = f"/remote.php/dav/files/{args.user}/{args.folder.strip('/')}/"
    discovered_ids = {str(item["fileid"]) for item in files}

    orphaned = []

    for file_id, existing in known.items():
        if file_id in discovered_ids:
            continue

        stored_path = existing["path"]

        if stored_path and unquote(stored_path).startswith(unquote(root)):
            orphaned.append((file_id, existing))

    for file_id, existing in orphaned:
        status = check_webdav_path(
            args.url,
            existing["path"],
            args.user,
            password,
            expected_file_id=file_id,
            return_status=True,
        )

        print(
            f"{status:<8} {file_id:>8}  "
            f"{existing['document_key']}  "
            f"{existing['path']}"
        )

    print(f"\nNeu: {new_count} | Bekannt: {known_count}")

    if not args.apply:
        print("Downloads: 0 | Datenbankänderungen: 0 | Embeddings: 0")
        return

    if not os.getenv("NEXTCLOUD_APP_PASSWORD") or not os.getenv("PGPASSWORD"):
        raise RuntimeError(
            "Automatischer Import benötigt NEXTCLOUD_APP_PASSWORD und PGPASSWORD"
        )

    # Ein zweiter vollständiger Scan schützt gegen vorübergehend unvollständige
    # Verzeichnisantworten. Bei Abweichung keine Lebenszyklus-Änderungen.
    def snapshot(entries):
        return {str(entry["fileid"]): (
            unquote(entry["path"]), entry["etag"], entry["size"]
        ) for entry in entries}

    second_files = discover(args.url, args.user, password, args.folder)
    if snapshot(files) != snapshot(second_files):
        raise RuntimeError("Nextcloud-Inhalt während der Scans verändert; Sync abgebrochen")

    ingest_password = os.environ["PGPASSWORD"]
    failures = []

    for item in files:
        existing = known.get(str(item["fileid"]))
        unchanged = pdf_is_unchanged(item, existing)

        if unchanged and existing["is_active"]:
            # Eine alte Fehlvormerkung darf nicht zur späteren Deaktivierung
            # führen, wenn die Datei zwischenzeitlich wieder erschienen ist.
            if get_missing_state(existing["id"], ingest_password) is not None:
                clear_missing_pdf(existing["id"], ingest_password)
            continue

        try:
            if unchanged and existing and not existing["is_active"]:
                if pdf_ready_for_reactivation(item, existing, db_password):
                    print(f"REACTIVATION_READY: {existing['document_key']}")
                else:
                    print(f"REIMPORT_REQUIRED: {existing['document_key']}")
                    import_document(item, args)
            else:
                import_document(item, args)

            # Nach dem Import die DB neu lesen (neue Dokumente werden erst
            # jetzt sichtbar) und einen weiteren WebDAV-Scan ausführen.
            refreshed = get_known_pdfs(db_password).get(str(item["fileid"]))
            current = discover(args.url, args.user, password, args.folder)
            live = next((entry for entry in current
                         if str(entry["fileid"]) == str(item["fileid"])), None)
            if live is None or not pdf_ready_for_reactivation(live, refreshed, db_password):
                raise RuntimeError("PDF nach Import/Reaktivierungsprüfung nicht mehr aktuell")
            if not pdf_metadata_matches(item, refreshed):
                raise RuntimeError("PDF hat sich seit dem Ausgangsscan verändert")

            outcome = reactivate_pdf(
                refreshed["id"], ingest_password, live["etag"], live["size"],
                live["fileid"], live["path"], dry_run=False,
            )
            if not existing or not existing["is_active"] or outcome != "ALREADY_ACTIVE":
                print(f"{outcome}: {refreshed['document_key']}")

        except (RuntimeError, ValueError, subprocess.TimeoutExpired, psycopg.Error,
                HTTPError, OSError) as exc:
            print(f"FEHLER: {exc}", file=sys.stderr)
            failures.append(item["path"])

    # Fehlende IDs dürfen nur vorgemerkt/deaktiviert werden, wenn sie in
    # beiden vollständigen Scans fehlten. Der alte Pfad wird separat geprüft.
    # MATCH bedeutet: ein Scan war offenbar unvollständig -> sicherheitshalber
    # keine Deaktivierung. MISSING oder MISMATCH: alter Dateieintrag fehlt.
    for file_id, existing in orphaned:
        try:
            status = check_webdav_path(
                args.url, existing["path"], args.user, password,
                expected_file_id=file_id, return_status=True,
            )
            if status == "MATCH":
                print(f"ORPHAN_UNCERTAIN: {existing['document_key']} (Pfad existiert)")
                continue
            outcome = update_missing_lifecycle(
                existing["id"], ingest_password, dry_run=False
            )
            print(f"{outcome}: {existing['document_key']} ({status})")
        except (RuntimeError, ValueError, psycopg.Error, HTTPError, OSError) as exc:
            print(f"FEHLER Lebenszyklus {file_id}: {exc}", file=sys.stderr)
            failures.append(existing["path"])

    if failures:
        raise RuntimeError(f"{len(failures)} PDF-Verarbeitung(en) fehlgeschlagen")


if __name__ == "__main__":
    main()