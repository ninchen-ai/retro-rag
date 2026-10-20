
#!/usr/bin/env python3
"""Listet importierte PDF-Handbücher aus Retro-RAG auf."""

import os
import getpass
import argparse
import psycopg


def list_manuals(manufacturer=None):
    password = os.environ.get("RETRO_RAG_READER_PASSWORD")
    if not password:
        password = getpass.getpass("PostgreSQL-Passwort: ")

    query = """
        SELECT
            d.document_key,
            d.title,
            d.nextcloud_path,
            p.page_count,
            COUNT(c.id) AS chunks
        FROM knowledge.document d
        LEFT JOIN knowledge.pdf_metadata p
            ON p.document_id = d.id
        LEFT JOIN rag.chunk c
            ON c.document_id = d.id
        WHERE d.document_kind = 'manual'
          AND d.is_active = true
          AND (
              %s::text IS NULL
              OR d.nextcloud_path ILIKE %s
          )
        GROUP BY
            d.id, d.document_key, d.title,
            d.nextcloud_path, p.page_count
        ORDER BY d.nextcloud_path
    """

    pattern = f"%{manufacturer}%" if manufacturer else None

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_reader",
        password=password,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (manufacturer, pattern))
            return cur.fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manufacturer",
        help="Filter im Nextcloud-Pfad, z.B. ASUS"
    )
    args = parser.parse_args()

    manuals = list_manuals(args.manufacturer)

    print(f"\nGefundene PDF-Handbücher: {len(manuals)}\n")

    for key, title, path, pages, chunks in manuals:
        print(f"Dokument: {key}")
        print(f"Titel:    {title}")
        print(f"Pfad:     {path}")
        print(f"Seiten:   {pages}")
        print(f"Chunks:   {chunks}")
        print("-" * 60)


if __name__ == "__main__":
    main()
