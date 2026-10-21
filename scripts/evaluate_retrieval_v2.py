
#!/usr/bin/env python3
"""Regressionstests für Retro-RAG Retrieval v2."""

import getpass
import os
import sys
import psycopg

from scripts.retrieval_v2 import hybrid_search

TEST_CASES = [
    {
        "name": "CUBX Boot Virus Detection",
        "question": (
            "Wie funktioniert Boot Virus Detection "
            "beim ASUS CUBX?"
        ),
        "term": "Boot Virus Detection",
        "expected_document": "manual-asus-cubx-103",
        "expected_primary": "mainboard-asus-cubx",
        "expected_chunk": 97,
    },
    {
        "name": "CUSL2-C Prozessorunterstützung",
        "question": (
            "Welche Prozessoren unterstützt "
            "das ASUS CUSL2-C?"
        ),
        "term": "Pentium III",
        "expected_document": "manual-nc-173",
        "expected_chunk": 11,
        "expected_primary": "mainboard-asus-cusl2-c",
    },
    {
        "name": "CUSL2-C Award BIOS Beep Codes",
        "question": (
            "Welche Bedeutung haben die Award BIOS "
            "Beep Codes beim ASUS CUSL2-C?"
        ),
        "term": "Award BIOS Beep Codes",
        "expected_document": "manual-nc-173",
        "expected_primary": "mainboard-asus-cusl2-c",
        "expected_chunk": 66,
    },
    {
        "name": "CUSL2-C deutsche Piepton-Frage",
        "question": (
            "Was bedeuten die Pieptöne beim Start "
            "des ASUS CUSL2-C?"
        ),
        "term": "Pieptöne",
        "expected_document": "manual-nc-173",
        "expected_primary": "mainboard-asus-cusl2-c",
        "expected_chunk": 66,
    },
]

def evaluate(cur, test):
    result = hybrid_search(
        cur,
        question=test["question"],
        term=test["term"],
        candidates=20,
        top_k=5,
    )

    # Hauptquelle unabhängig vom PDF-Ranking prüfen.
    primary_keys = {
        row[0] for row in result["primary_document"]
    }

    primary_ok = (
        test["expected_primary"] in primary_keys
    )

    # Relevanten PDF-Abschnitt prüfen.
    pdf_rank = None

    for position, item in enumerate(
        result["results"], start=1
    ):
        row = item["row"]

        if (
            row[1] == test["expected_document"]
            and row[2] == test["expected_chunk"]
        ):
            pdf_rank = position
            break

    return primary_ok, pdf_rank


def main():
    password = (
        os.environ.get("RETRO_RAG_READER_PASSWORD")
        or getpass.getpass(
            "PostgreSQL-Lesepasswort: "
        )
    )

    passed = 0

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
                print(
                    f"\nTEST: {test['name']}",
                    flush=True,
                )

                rank = evaluate(cur, test)

                primary_ok, pdf_rank = evaluate(cur, test)

                if primary_ok and pdf_rank is not None:
                    passed += 1
                    print(
                        f"PASS: Hauptquelle vorhanden, "
                        f"PDF-Zieltreffer auf Rang {pdf_rank}"
                    )
                else:
                    print(
                        f"FAIL: Hauptquelle={primary_ok}, "
                        f"PDF-Rang={pdf_rank}"
                    )
    print(
        f"\nERGEBNIS: {passed}/{len(TEST_CASES)} "
        "Tests bestanden"
    )

    return 0 if passed == len(TEST_CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
