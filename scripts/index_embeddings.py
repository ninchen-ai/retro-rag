#!/usr/bin/env python3
"""Retro-RAG initial vector indexer. Nextcloud is the source of truth.
Default: dry-run. --apply writes embeddings using the restricted ingest role.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import psycopg
import yaml

MODEL = 'nomic-embed-text'
MAX_CHARS = 2800


def get_url(url, *, username=None, password=None, json_payload=None):
    headers = {'User-Agent': 'retro-rag-indexer/0.1'}
    if username is not None:
        token = base64.b64encode(f'{username}:{password}'.encode()).decode()
        headers['Authorization'] = f'Basic {token}'
    if json_payload is not None:
        headers['Content-Type'] = 'application/json'
        method = 'POST'
        data = json.dumps(json_payload).encode('utf-8')
    else:
        method, data = 'GET', None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def read_md(raw):
    text = raw.decode('utf-8-sig')
    m = re.match(r'\A---\s*\n(.*?)\n---\s*\n(.*)\Z', text, flags=re.S)
    if not m:
        raise ValueError('YAML-Frontmatter fehlt oder ist nicht abgeschlossen')
    metadata = yaml.safe_load(m.group(1))
    if not isinstance(metadata, dict):
        raise ValueError('YAML-Frontmatter muss ein Mapping sein')
    body = m.group(2).strip()
    # Include the factual metadata in retrieval; otherwise a minimal markdown
    # description might omit component references or the asset tag.
    relevant = {k: v for k, v in metadata.items() if k not in {'status'}}
    synopsis = yaml.safe_dump(relevant, allow_unicode=True, sort_keys=True).strip()
    return f'Hardware-/Retro-Computing-Dokument\n{synopsis}\n\n{body}'.strip()


def chunk_text(text, max_chars=MAX_CHARS):
    """Split long documents into consecutive non-empty passages; no omissions."""
    result = []
    while text:
        if len(text) <= max_chars:
            piece, text = text, ''
        else:
            at = text.rfind('\n\n', 0, max_chars)
            if at < max_chars // 2:
                at = text.rfind('\n', 0, max_chars)
            if at < max_chars // 2:
                at = max_chars
            piece, text = text[:at], text[at:]
        piece = piece.strip()
        text = text.lstrip()
        if piece:
            result.append(piece)
    return result


def embed(ollama_url, content):
    endpoint = ollama_url.rstrip('/') + '/api/embed'
    payload = {'model': MODEL, 'input': content, 'truncate': False}
    result = json.loads(get_url(endpoint, json_payload=payload))
    embeddings = result.get('embeddings') or []
    if len(embeddings) != 1 or len(embeddings[0]) != 768:
        raise ValueError(f'Embedding-Dimension unerwartet: {[len(x) for x in embeddings]}')
    return embeddings[0]


def main():
    p = argparse.ArgumentParser(description='Nextcloud Markdown -> pgvector, default dry-run')
    p.add_argument('--cloud-url', default='http://127.0.0.1:8080')
    p.add_argument('--cloud-user', default='nina')
    p.add_argument('--folder', default='Retro-Computing')
    p.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    password = os.environ.get('NEXTCLOUD_APP_PASSWORD') or getpass.getpass('Nextcloud-App-Passwort: ')
    pgpassword = os.environ.get('PGPASSWORD') or getpass.getpass('Passwort für retro_rag_ingest: ')
    prefix = f'/remote.php/dav/files/{args.cloud_user}/{args.folder}/'
    changes = 0
    skipped = 0
    with psycopg.connect(host='127.0.0.1', port=5432, dbname='retro_rag', user='retro_rag_ingest',
                         password=pgpassword, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(r'''
    SELECT id, document_key, nextcloud_path, content_sha256, origin
    FROM knowledge.document
    WHERE document_kind IN (
        'hardware_model',
        'inventory_item',
        'system',
        'reference'
    )
    AND nextcloud_path ~* '\.md$'
    ORDER BY id
''')
            documents = cur.fetchall()
        for doc_id, key, path, expected_sha, origin in documents:
            if origin not in ('own', 'approved_external'):
                raise ValueError(f'{key}: unzulässiger Dokumentstatus {origin}')
            if not path.startswith(prefix) or not path.lower().endswith('.md'):
                raise ValueError(f'{key}: unerwarteter Nextcloud-Pfad: {path}')
            path_url = urllib.parse.quote(path, safe='/%')
            raw = get_url(args.cloud_url.rstrip('/') + path_url,
                          username=args.cloud_user, password=password)
            actual_sha = hashlib.sha256(raw).hexdigest()
            if actual_sha.lower() != expected_sha.lower():
                raise ValueError(f'{key}: SHA256 stimmt nicht überein. Erst Nextcloud-Synchronisierung abwarten.')
            text = read_md(raw)
            chunks = chunk_text(text)
            with conn.cursor() as cur:
                cur.execute('''SELECT chunk_index, content FROM rag.chunk
                               WHERE document_id = %s AND embedding_model = %s
                               ORDER BY chunk_index''', (doc_id, MODEL))
                previous = cur.fetchall()
            if [(i, x) for i, x in enumerate(chunks)] == previous:
                print(f'SKIP {key}: {len(chunks)} Chunk(s) bereits aktuell')
                skipped += 1
                continue
            print(f'{"INDEX" if args.apply else "PLAN"} {key}: {len(chunks)} Chunk(s)')
            changes += 1
            if not args.apply:
                continue
            vectors = [embed(args.ollama_url, c) for c in chunks]
            with conn.transaction():
                with conn.cursor() as cur:
                    # Synchronizer might have changed the document during embedding.
                    cur.execute('''SELECT content_sha256 FROM knowledge.document
                                   WHERE id = %s FOR UPDATE''', (doc_id,))
                    row = cur.fetchone()
                    if not row or row[0].lower() != expected_sha.lower():
                        raise ValueError(f'{key}: Dokument während der Embedding-Erstellung verändert')
                    cur.execute('DELETE FROM rag.chunk WHERE document_id = %s AND embedding_model = %s',
                                (doc_id, MODEL))
                    for i, (content, vector) in enumerate(zip(chunks, vectors)):
                        cur.execute('''INSERT INTO rag.chunk
                                       (document_id, chunk_index, heading, content, token_count, embedding_model, embedding)
                                       VALUES (%s, %s, %s, %s, NULL, %s, %s::vector)''',
                                    (doc_id, i, None, content, MODEL, json.dumps(vector)))
                    cur.execute('UPDATE knowledge.document SET indexed_at = now() WHERE id = %s', (doc_id,))
    print(f'Fertig: {changes} zu indexieren, {skipped} unverändert; '
          f'{"Änderungen gespeichert" if args.apply else "kein Schreibzugriff"}.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, urllib.error.URLError, psycopg.Error, UnicodeError) as exc:
        print(f'FEHLER: {exc}', file=sys.stderr)
        sys.exit(1)
