
"""Retro-RAG: PDF-Inbox scannen und neue Dokumente analysieren."""

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path

from llm_import.webdav import (
    list_inbox_documents,
    download_inbox_document,
)
from llm_import.review_package import plan_review_package
from scripts.import_llm import (
    process_multi_model_document,
    DEFAULT_URL,
)

URL = "http://127.0.0.1:8080"
USER = "nina"
CACHE_DIR = Path("data/review-results")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--process",
        action="store_true",
        help="Neue PDFs analysieren und lokal als JSON speichern",
    )
    args = parser.parse_args()

    password = getpass.getpass("Nextcloud-App-Passwort: ")

    documents = list_inbox_documents(
        url=URL,
        user=USER,
        password=password,
    )

    pdfs = sorted(
        (
            doc for doc in documents
            if doc["filename"].lower().endswith(".pdf")
        ),
        key=lambda doc: doc["filename"].lower(),
    )

    print(f"\nPDF-Dateien gefunden: {len(pdfs)}")

    counts = {
        "CACHED": 0,
        "NEW": 0,
        "PROCESSED": 0,
        "FAILED": 0,
    }

    for document in pdfs:
        filename = document["filename"]

        print(f"\n===== {filename} =====", flush=True)

        try:
            pdf_bytes = download_inbox_document(
                url=URL,
                user=USER,
                password=password,
                document=document,
            )

            source_hash = hashlib.sha256(pdf_bytes).hexdigest()
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache = CACHE_DIR / f"{source_hash[:16]}.json"

            print("SHA-256:", source_hash)

            if cache.exists():
                with cache.open(encoding="utf-8") as handle:
                    cached = json.load(handle)

                plan_review_package(cached)

                cached_hashes = {
                    item["source"]["sha256"]
                    for item in cached["results"]
                }

                if cached_hashes != {source_hash}:
                    raise ValueError("Cache passt nicht zur PDF-Quelle")

                counts["CACHED"] += 1
                print("[CACHED] Bereits analysiert")
                continue

            if not args.process:
                counts["NEW"] += 1
                print("[NEW] Analyse erforderlich")
                continue

            print("[PROCESSING] Qwen3.5:4b", flush=True)

            result = process_multi_model_document(
                source_bytes=pdf_bytes,
                filename=filename,
                model="qwen3.5:4b",
                ollama_url=DEFAULT_URL,
            )

            plan = plan_review_package(result)

            result_hashes = {
                item["source"]["sha256"]
                for item in result["results"]
            }

            if result_hashes != {source_hash}:
                raise ValueError("Analyseergebnis passt nicht zur PDF")

            serialized = json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n"

            # Eindeutiger temporärer Pfad; finale Datei nie überschreiben.
            temporary = CACHE_DIR / (
                f".{source_hash[:16]}.{os.getpid()}.tmp"
            )

            try:
                with temporary.open("x", encoding="utf-8") as handle:
                    handle.write(serialized)

                # Exklusives Anlegen der finalen Datei.
                # Hardlink verhindert Überschreiben bei parallelen Läufen.
                os.link(temporary, cache)
            finally:
                temporary.unlink(missing_ok=True)

            counts["PROCESSED"] += 1

            print("[PROCESSED] Analyse erfolgreich")
            print("Modelle:", len(result["results"]))
            print("Review-Dateien:", len(plan))
            print("Cache:", cache)

            for item in result["results"]:
                print(
                    " -",
                    item["classification"]["model"],
                    "|",
                    item.get("review", {}).get("status"),
                )

        except Exception as exc:
            counts["FAILED"] += 1
            print(
                f"[FAILED] {type(exc).__name__}: {exc}",
                flush=True,
            )

    print("\n===== ZUSAMMENFASSUNG =====")

    for status, count in counts.items():
        print(f"{status}: {count}")

    print("\nNextcloud-Schreiboperationen: 0")
    print("PostgreSQL-Änderungen: 0")


if __name__ == "__main__":
    main()
