#!/usr/bin/env python3
"""Retro-RAG PDF discovery via Nextcloud WebDAV. Read-only."""

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

def check_webdav_path(base, path, user, password):
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
        data=b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>',
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
            return True

    except HTTPError as exc:
        if exc.code == 404:
            return False
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

        if stored_path and stored_path.startswith(root):
            orphaned.append((file_id, existing))

    for file_id, existing in orphaned:
        exists = check_webdav_path(
            args.url,
            existing["path"],
            args.user,
            password,
        )

        status = "MISSING" if not exists else "CHECK"

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

    failures = []

    for item in files:
        existing = known.get(item["fileid"])

        if (
            existing
            and unquote(existing["path"]) == unquote(item["path"])
            and existing["etag"] == item["etag"]
            and existing["size"] == item["size"]
            and existing["page_count"] is not None
            and existing["chunk_count"] > 0
        ):
            continue

        try:
            import_document(item, args)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"FEHLER: {exc}", file=sys.stderr)
            failures.append(item["path"])

    if failures:
        raise RuntimeError(
            f"{len(failures)} PDF-Import(e) fehlgeschlagen"
        )


if __name__ == "__main__":
    main()