#!/usr/bin/env python3
"""Diagnose natürlicher Fragen ohne manuelle Suchbegriffe."""

import getpass
import os

import psycopg

from scripts.retrieval_v2 import hybrid_search


QUESTIONS = [
    (
        "Boot Virus Detection",
        "Wie funktioniert Boot Virus Detection beim ASUS CUBX?",
        "manual-asus-cubx-103",
        97,
    ),
    (
        "Prozessorunterstützung",
        "Welche Prozessoren unterstützt das ASUS CUSL2-C?",
        "manual-nc-173",
        11,
    ),
    (
        "BIOS Beep Codes",
        "Welche Bedeutung haben die Award BIOS Beep Codes beim ASUS CUSL2-C?",
        "manual-nc-173",
        66,
    ),
    (
        "Deutsche Piepton-Frage",
        "Was bedeuten die Pieptöne beim Start des ASUS CUSL2-C?",
        "manual-nc-173",
        66,
    ),
]


def main():
    password = (
        os.environ.get("RETRO_RAG_READER_PASSWORD")
        or getpass.getpass("PostgreSQL-Lesepasswort: ")
    )

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_reader",
        password=password,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            for name, question, expected_doc, expected_chunk in QUESTIONS:
                result = hybrid_search(
                    cur,
                    question=question,
                    term=None,
                    candidates=20,
                    top_k=5,
                )

                print(f"\n===== {name} =====")
                print("Frage:", question)
                print("Suchbegriffe:", result["search_terms"])

                primary = result["primary_document"]
                print(
                    "Hauptquelle:",
                    [row[0] for row in primary],
                )

                found_rank = None

                for rank, item in enumerate(result["results"], 1):
                    row = item["row"]

                    print(
                        f"{rank}. {row[1]} "
                        f"| Chunk {row[2]} "
                        f"| Seite {row[3]} "
                        f"| Qualität {item.get('quality', 'unbekannt')}"
                    )

                    if (
                        row[1] == expected_doc
                        and row[2] == expected_chunk
                    ):
                        found_rank = rank

                print(
                    "ERGEBNIS:",
                    f"PASS (Rang {found_rank})"
                    if found_rank is not None
                    else "FAIL (Zielchunk nicht in Top 5)",
                )


if __name__ == "__main__":
    main()
