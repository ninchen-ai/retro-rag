#!/usr/bin/env python3
"""Retro-RAG PDF discovery via Nextcloud WebDAV. Read-only."""

import argparse
import base64
import getpass
import os
import psycopg
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote
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
            xml = ET.fromstring(response.read())

        for item in xml.findall("d:response", DAV):
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
                """)
                rows = cur.fetchall()

        return {
            str(file_id): {
                "document_key": key,
                "path": path,
                "etag": etag,
                "size": size,
                "page_count": page_count,
                "chunk_count": chunk_count,
            }
            for file_id, key, path, etag, size, page_count, chunk_count in rows
        }
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

        elif existing["path"] != item["path"]:
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
            and existing["path"] == item["path"]
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