#!/usr/bin/env python3
"""Retrieval-Evaluierung für Intel-Chipsatzdokumente."""

import getpass
import os
import sys

import psycopg

from scripts.retrieval_v2 import hybrid_search


TEST_CASES = [
    {
        "name": "Intel 82443BX Speicherarten",
        "question": (
            "Welche Speicherarten unterstützt der Intel 82443BX?"
        ),
        "expected_document": "manual-nc-249",
        "expected_chunks": {24},
    },
    {
        "name": "Intel 440BX maximale Speicherkapazität",
        "question": (
            "Wie viel Arbeitsspeicher unterstützt "
            "der Intel 440BX maximal?"
        ),
        "expected_document": "manual-nc-249",
        "expected_chunks": {2, 24},
        "known_failure": True,
    },
    {
        "name": "Intel 440BX RDRAM",
        "question": "Unterstützt der Intel 440BX RDRAM?",
        "expected_document": "manual-nc-249",
        "expected_chunks": {24},
    },
    {
        "name": "Intel 82443BX AGP",
        "question": (
            "Welche Funktionen besitzt der "
            "Intel 82443BX AGP-Controller?"
        ),
        "expected_document": "manual-nc-249",
        "expected_chunks": {2, 19, 24},
    },
]


def evaluate(cur, test):
    result = hybrid_search(
        cur,
        question=test["question"],
        candidates=20,
        top_k=5,
    )

    expected_rank = None

    for position, item in enumerate(
        result["results"], start=1
    ):
        row = item["row"]
        document_key = row[1]
        chunk_index = row[2]

        if (
            document_key == test["expected_document"]
            and chunk_index in test["expected_chunks"]
        ):
            expected_rank = position
            break

    return result, expected_rank


def main():
    password = (
        os.environ.get("RETRO_RAG_READER_PASSWORD")
        or getpass.getpass("PostgreSQL-Lesepasswort: ")
    )

    passed = 0
    xfailed = 0
    failed = 0

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
            for test in TEST_CASES:
                print("\n" + "=" * 65)
                print("TEST:", test["name"])

                result, rank = evaluate(cur, test)

                print("Frage:", test["question"])
                print("Suchbegriffe:", result["search_terms"])
                print("Treffer:")

                for position, item in enumerate(
                    result["results"], start=1
                ):
                    _, doc, chunk, page, _ = item["row"]

                    print(
                        f"  {position}. {doc} "
                        f"| Chunk {chunk} "
                        f"| Seite {page}"
                    )

                if rank is not None:
                    passed += 1
                    status = (
                        "XPASS" if test.get("known_failure")
                        else "PASS"
                    )
                    print(
                        f"{status}: Zielabschnitt auf Rang {rank}"
                    )
                elif test.get("known_failure"):
                    xfailed += 1
                    print(
                        "XFAIL: Bekannte Schwäche – "
                        "Zielabschnitt nicht in Top 5"
                    )
                else:
                    failed += 1
                    print(
                        "FAIL: Erwarteter Zielabschnitt "
                        "nicht in Top 5"
                    )

    print("\n" + "=" * 65)
    print(
        f"ERGEBNIS: {passed} PASS/XPASS, "
        f"{xfailed} XFAIL, {failed} FAIL"
    )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
PY