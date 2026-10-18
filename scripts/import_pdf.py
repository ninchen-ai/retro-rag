#!/usr/bin/env python3
"""Single-manual PDF -> Retro-RAG; dry-run by default, --apply for DB writes.

Initial test source: ASUS CUBX manual in Nextcloud. No changes to the Markdown pipeline.
"""
from __future__ import annotations

import argparse
import base64
from curses import raw
import getpass
import hashlib
from importlib.metadata import files
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import psycopg
import pymupdf

FILE_PATH = 'Retro-Computing/Hardware/Mainboards/cubx-103.pdf'
DOC_KEY = 'manual-asus-cubx-103'
TITLE = "ASUS CUBX User's Manual"
MODEL = 'nomic-embed-text'
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_CHARS = 2500
BASE = 'http://127.0.0.1:8080'
OLLAMA = 'http://127.0.0.1:11434'

def document_identity(file_id: str, file_path: str) -> tuple[str, str]:
    """Stable document key and initial title for a Nextcloud PDF."""

    if file_id == "172":
        if file_path != FILE_PATH:
            fail("CUBX-Datei hat einen unerwarteten Pfad")
        return DOC_KEY, TITLE

    if not file_id.isdecimal():
        fail("Ungueltige Nextcloud-Datei-ID")

    filename = file_path.rsplit("/", 1)[-1]
    if not filename.lower().endswith(".pdf"):
        fail("Keine PDF-Datei")

    return f"manual-nc-{file_id}", filename[:-4]

def fail(message):
    raise RuntimeError(message)


def get_webdav(base: str, user: str, password: str, file_path: str):
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ('http', 'https') or (
        parts.scheme == 'http'
        and parts.hostname not in ('127.0.0.1', 'localhost', '::1')
    ):
        fail('Unverschluesseltes WebDAV ist nur via localhost erlaubt')

    path = (
        '/remote.php/dav/files/'
        + urllib.parse.quote(user, safe='')
        + '/'
        + urllib.parse.quote(file_path, safe='/')
    )
    url = base.rstrip('/') + path

    authorization = (
        'Basic '
        + base64.b64encode(f'{user}:{password}'.encode()).decode()
    )
    headers = {'Authorization': authorization}

    prop = (
        b'<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
        b'<d:prop>'
        b'<oc:fileid/>'
        b'<d:getetag/>'
        b'<d:getcontentlength/>'
        b'<d:getlastmodified/>'
        b'</d:prop>'
        b'</d:propfind>'
    )

    def metadata():
        request = urllib.request.Request(
            url,
            method='PROPFIND',
            data=prop,
            headers={
                **headers,
                'Depth': '0',
                'Content-Type': 'application/xml',
            },
        )

        with urllib.request.urlopen(request, timeout=30) as reply:
            xml = ET.fromstring(reply.read())

        ns_dav = '{DAV:}'
        ns_oc = '{http://owncloud.org/ns}'

        file_id = xml.findtext(f'.//{ns_oc}fileid')
        etag = xml.findtext(f'.//{ns_dav}getetag')
        size = xml.findtext(f'.//{ns_dav}getcontentlength')
        modified = xml.findtext(f'.//{ns_dav}getlastmodified')

        if not file_id or not etag or not size:
            fail('Unvollstaendige Nextcloud-Dateimetadaten')

        return {
            'fileid': file_id.strip(),
            'etag': etag.strip(),
            'size': int(size),
            'modified': modified,
        }

    before = metadata()

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as reply:
        declared = reply.headers.get('Content-Length')

        if declared and int(declared) > MAX_PDF_BYTES:
            fail('PDF groesser als 50 MiB: Abbruch')

        raw = reply.read(MAX_PDF_BYTES + 1)

    if len(raw) > MAX_PDF_BYTES or not raw.startswith(b'%PDF-'):
        fail('Keine gueltige PDF-Datei oder PDF groesser als 50 MiB')

    after = metadata()

    if before != after:
        fail('PDF wurde waehrend des Downloads geaendert')

    if len(raw) != after['size']:
        fail('PDF-Dateigroesse stimmt nicht mit Nextcloud ueberein')

    return raw, path, after


def split_page(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split within a page, preferring paragraph and then line boundaries."""
    text = text.replace('\x00', '').replace('\r\n', '\n').strip()
    if not text:
        return []
    chunks = []
    while text:
        if len(text) <= limit:
            segment, text = text, ''
        else:
            point = text.rfind('\n\n', limit // 2, limit)
            if point < 0:
                point = text.rfind('\n', limit // 2, limit)
            if point < 0:
                point = text.rfind(' ', limit // 2, limit)
            if point < 0:
                point = limit
            segment, text = text[:point], text[point:]
        if segment.strip():
            chunks.append(segment.strip())
        text = text.lstrip()
    return chunks


def extract(raw: bytes, document_title: str):
    chunks = []
    empty = []
    with pymupdf.open(stream=raw, filetype='pdf') as doc:
        if doc.needs_pass:
            fail('PDF ist passwortgeschuetzt')
        metadata = doc.metadata or {}
        for pageno, page in enumerate(doc, start=1):
            text = page.get_text('text', sort=True)
            segments = split_page(text)
            if not segments:
                empty.append(pageno)
            for segment in segments:
                # Include stable source locator in the embedded text.
                body = f'{document_title} | PDF-Seite {pageno}\n{segment}'
                chunks.append((pageno, body))
        return {
            'page_count': len(doc),
            'pdf_version': metadata.get('format') or None,
            'producer': metadata.get('producer') or None,
            'author': metadata.get('author') or None,
            'chunks': chunks,
            'empty_pages': empty,
        }


def embedding(text: str, ollama_base: str) -> list[float]:
    body = json.dumps({'model': MODEL, 'input': text, 'truncate': False}).encode()
    request = urllib.request.Request(
        ollama_base.rstrip('/') + '/api/embed', data=body,
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(request, timeout=180) as reply:
        output = json.load(reply)
    vectors = output.get('embeddings') or []
    if len(vectors) != 1 or len(vectors[0]) != 768:
        fail('Ollama lieferte keinen 768-dimensionalen Vektor')
    return vectors[0]


def check_role(cur):
    cur.execute('SELECT current_user, current_database()')
    if cur.fetchone() != ('retro_rag_ingest', 'retro_rag'):
        fail('Abbruch: falsche Datenbank oder Datenbankrolle')


def existing_state(conn, digest, path, fid, expected_chunks, document_key):
    with conn.cursor() as cur:
        check_role(cur)
        cur.execute('''SELECT id, origin, document_kind, content_sha256,
                              nextcloud_path, nextcloud_file_id
                       FROM knowledge.document WHERE document_key = %s''', (document_key,))
        row = cur.fetchone()
        if row:
            doc_id, origin, kind, stored_hash, stored_path, stored_fid = row
            if origin != 'own' or kind != 'manual':
                fail('Dokument-ID ist bereits fuer eine andere Herkunft/Art vergeben')
            cur.execute('''SELECT COUNT(*), MIN(chunk_index), MAX(chunk_index)
                           FROM rag.chunk WHERE document_id=%s AND embedding_model=%s''',
                        (doc_id, MODEL))
            count, first_index, last_index = cur.fetchone()
            cur.execute('SELECT COUNT(*) FROM knowledge.pdf_metadata WHERE document_id=%s', (doc_id,))
            meta_count = cur.fetchone()[0]
            return (stored_hash == digest and stored_path == path and stored_fid == fid
                    and count == expected_chunks and count > 0
                    and first_index == 0 and last_index == count - 1
                    and meta_count == 1)
        return False


def store(conn, pdf, path, fid, digest, vectors, etag, file_size,
          last_modified, document_key, document_title):
    with conn.transaction():
        with conn.cursor() as cur:
            check_role(cur)
            # Atomic metadata and vector replacement: old chunks survive failures.
            cur.execute('''INSERT INTO knowledge.document
                (document_key,document_kind,origin,nextcloud_file_id,nextcloud_path,
                 content_sha256,title,indexed_at)
                VALUES (%s,'manual','own',%s,%s,%s,%s,now())
                ON CONFLICT (document_key) DO UPDATE SET
                   nextcloud_file_id = EXCLUDED.nextcloud_file_id,
                   nextcloud_path = EXCLUDED.nextcloud_path,
                   content_sha256 = EXCLUDED.content_sha256,
                   title = EXCLUDED.title,
                   indexed_at = now()
                WHERE knowledge.document.origin = 'own'
                  AND knowledge.document.document_kind = 'manual'
                  AND knowledge.document.nextcloud_file_id = EXCLUDED.nextcloud_file_id
                RETURNING id''', (document_key, fid, path, digest, document_title))
            row = cur.fetchone()
            if row is None:
                fail('Import nicht erlaubt: bestehende Dokument-ID')
            doc_id = row[0]

            # PDF-Metadaten speichern oder aktualisieren
            cur.execute('''
                INSERT INTO knowledge.pdf_metadata
                    (document_id, page_count, pdf_version, producer,
                     author, extracted_at, extraction_engine)
                VALUES (%s, %s, %s, %s, %s, now(), 'PyMuPDF')
                ON CONFLICT (document_id) DO UPDATE SET
                    page_count = EXCLUDED.page_count,
                    pdf_version = EXCLUDED.pdf_version,
                    producer = EXCLUDED.producer,
                    author = EXCLUDED.author,
                    extracted_at = now(),
                    extraction_engine = 'PyMuPDF'
            ''', (
                doc_id,
                pdf['page_count'],
                pdf['pdf_version'],
                pdf['producer'],
                pdf['author']
            ))

            cur.execute(
                'DELETE FROM rag.chunk WHERE document_id=%s AND embedding_model=%s',
                (doc_id, MODEL)
            )

            for index, ((page, content), vector) in enumerate(zip(pdf['chunks'], vectors)):
                cur.execute('''INSERT INTO rag.chunk
                    (document_id, chunk_index, heading, content, token_count,
                     embedding_model, embedding, page_start, page_end)
                    VALUES (%s,%s,NULL,%s,NULL,%s,%s::vector,%s,%s)''',
                    (doc_id, index, content, MODEL, json.dumps(vector), page, page))

            # Synchronisierungsstatus atomar mit den PDF-Chunks speichern.
            cur.execute('''
                INSERT INTO knowledge.pdf_sync_state
                    (document_id, etag, file_size, last_modified, synced_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (document_id) DO UPDATE SET
                    etag = EXCLUDED.etag,
                    file_size = EXCLUDED.file_size,
                    last_modified = EXCLUDED.last_modified,
                    synced_at = now()
            ''', (doc_id, etag, file_size, last_modified))

    return doc_id

def update_sync_state(conn, digest, path, fid, expected_chunks, metadata, document_key):
    """Record sync metadata only if existing PDF content is unchanged."""
    with conn.transaction():
        with conn.cursor() as cur:
            check_role(cur)

            cur.execute('''
                SELECT d.id
                FROM knowledge.document d
                JOIN knowledge.pdf_metadata pm ON pm.document_id = d.id
                WHERE d.document_key = %s
                  AND d.document_kind = 'manual'
                  AND d.origin = 'own'
                  AND d.content_sha256 = %s
                  AND d.nextcloud_path = %s
                  AND d.nextcloud_file_id = %s
                  AND (
                      SELECT COUNT(*)
                      FROM rag.chunk c
                      WHERE c.document_id = d.id
                        AND c.embedding_model = %s
                  ) = %s
                  AND (SELECT MIN(c.chunk_index) FROM rag.chunk c
                       WHERE c.document_id = d.id AND c.embedding_model = %s) = 0
                  AND (SELECT MAX(c.chunk_index) FROM rag.chunk c
                       WHERE c.document_id = d.id AND c.embedding_model = %s) = %s - 1
                FOR UPDATE OF d
            ''', (document_key, digest, path, fid, MODEL, expected_chunks,
                        MODEL, MODEL, expected_chunks))

            row = cur.fetchone()
            if row is None:
                return False

            cur.execute('''
                INSERT INTO knowledge.pdf_sync_state
                    (document_id, etag, file_size, last_modified, synced_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (document_id) DO UPDATE SET
                    etag = EXCLUDED.etag,
                    file_size = EXCLUDED.file_size,
                    last_modified = EXCLUDED.last_modified,
                    synced_at = now()
            ''', (
                row[0],
                metadata['etag'],
                metadata['size'],
                parsedate_to_datetime(metadata['modified'])
                if metadata['modified'] else None
            ))

    return True

def main():
    parser = argparse.ArgumentParser(description='Retro-RAG: Nextcloud-PDFs nach PostgreSQL/pgvector importieren')
    parser.add_argument(
        '--file',
        default=FILE_PATH,
        help='PDF-Pfad relativ zum Nextcloud-Benutzerverzeichnis'
    )
    parser.add_argument('--apply', action='store_true', help='Datenbank und Embeddings schreiben')
    parser.add_argument('--cloud-url', default=BASE)
    parser.add_argument('--cloud-user', default='nina')
    parser.add_argument('--ollama-url', default=OLLAMA)
    args = parser.parse_args()
    password = os.getenv('NEXTCLOUD_APP_PASSWORD') or getpass.getpass('Nextcloud-App-Passwort: ')
    raw, path, metadata = get_webdav(
        args.cloud_url, args.cloud_user, password, args.file
    )
    fid = metadata['fileid']
    document_key, document_title = document_identity(fid, args.file)

    digest = hashlib.sha256(raw).hexdigest()
    pdf = extract(raw, document_title)
    print(f'Dokument: {document_key} | Nextcloud-ID: {fid}')
    print(f'PDF: {pdf["page_count"]} Seiten | {len(raw)} Bytes | SHA-256: {digest[:16]}...')
    print(f'Extrahierte Chunks: {len(pdf["chunks"])} | Seiten ohne Text: {len(pdf["empty_pages"])}')
    if not args.apply:
        print('DRY-RUN: keine Datenbank-Schreiboperationen, keine Embeddings erzeugt.')
        return
    if not pdf['chunks']:
        fail('PDF hat keinen maschinenlesbaren Text; Import abgebrochen')
    pgpassword = os.getenv('PGPASSWORD') or getpass.getpass('Passwort fuer retro_rag_ingest: ')
    conn_args = dict(host='127.0.0.1', port=5432, dbname='retro_rag',
                     user='retro_rag_ingest', password=pgpassword, connect_timeout=10)
    with psycopg.connect(**conn_args) as conn:
        up_to_date = existing_state(
            conn, digest, path, fid, len(pdf['chunks']), document_key
        )

    if up_to_date:
        with psycopg.connect(**conn_args) as conn:
            synced = update_sync_state(
                conn, digest, path, fid,
                len(pdf['chunks']), metadata, document_key
            )

        if not synced:
            fail('Synchronisierungsstatus konnte nicht bestätigt werden')

        print('SKIP: PDF und Embeddings bereits aktuell.')
        print('SYNC: Nextcloud-ETag erfolgreich gespeichert.')
        return

    vectors = []
    for i, (_, content) in enumerate(pdf['chunks'], 1):
        vectors.append(embedding(content, args.ollama_url))
        if i % 20 == 0 or i == len(pdf['chunks']):
            print(f'Embeddings: {i}/{len(pdf["chunks"])}', flush=True)

    with psycopg.connect(**conn_args) as conn:
        document_id = store(
            conn, pdf, path, fid, digest, vectors,
            metadata["etag"],
            metadata["size"],
            parsedate_to_datetime(metadata["modified"])
            if metadata["modified"] else None,
            document_key,
            document_title
        )
    print(f'COMMIT: Dokument-ID {document_id}, {len(vectors)} Chunks mit PDF-Seitenreferenzen gespeichert.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, psycopg.Error, urllib.error.URLError,
            urllib.error.HTTPError, pymupdf.FileDataError) as exc:
        print(f'FEHLER: {exc}', file=sys.stderr)
        sys.exit(1)
