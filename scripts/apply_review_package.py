
"""Manuell freigegebener Upload des Gigabyte-Review-Pakets."""

import argparse
import json
import sys
from getpass import getpass
from hashlib import sha256
from pathlib import Path

from llm_import.review_apply import execute_review_package
from llm_import.review_package import plan_review_package
from llm_import.review_preview import build_review_preview
from llm_import.review_transport import NextcloudReviewTransport
from llm_import.review_write_transport import NextcloudReviewWriteTransport
from llm_import.nextcloud_review import (
    create_review_directory,
    upload_review_file,
)

SOURCE_SHA = (
    "38627464c49c63dc82dd3ff6f4d2fafe727ed666262fff69e651772209d8da22"
)
CACHE = Path("data/review-results") / f"{SOURCE_SHA[:16]}.json"
EXPECTED_MODELS = {"GV-R92S128T", "GV-R92S64T"}
CONFIRMATION = f"UPLOAD {SOURCE_SHA[:16]}"


def load_package(data: bytes) -> dict:
    result = json.loads(data.decode("utf-8"))
    plan = plan_review_package(result)

    entries = result["results"]
    models = {
        item["classification"]["model"]
        for item in entries
    }
    hashes = {
        item["source"]["sha256"]
        for item in entries
    }

    if (
        len(entries) != 2
        or models != EXPECTED_MODELS
        or hashes != {SOURCE_SHA}
        or len(plan) != 4
    ):
        raise ValueError("Unerwartetes Gigabyte-Review-Paket")

    if any(
        item.get("review", {}).get("status") != "REVIEW"
        for item in entries
    ):
        raise ValueError("Unerwarteter fachlicher Review-Status")

    return result


def manifest(preview: dict) -> tuple:
    return tuple(
        (
            item["path"],
            item["sha256"],
            item["size_bytes"],
        )
        for item in preview["files"]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Nach ausdrücklicher Bestätigung Upload ausführen",
    )
    args = parser.parse_args()

    original_bytes = CACHE.read_bytes()
    original_sha = sha256(original_bytes).hexdigest()
    package = load_package(original_bytes)

    password = getpass("Nextcloud-App-Passwort: ")

    connection = {
        "base_url": "http://127.0.0.1:8080",
        "user": "nina",
        "password": password,
    }

    reader = NextcloudReviewTransport(**connection)

    preview = build_review_preview(
        package,
        transport=reader,
    )

    print("\n===== REVIEW-VORSCHAU =====")
    print("Status:", preview["status"])
    print("Cache-SHA-256:", original_sha)
    print("Quelle:", preview["source_sha256"])

    for item in preview["files"]:
        print(
            item["status"],
            item["path"],
            item["sha256"],
        )

    print("Schreiboperationen bisher: 0")

    if preview["status"] != "READY":
        raise SystemExit("Paket blockiert: kein Upload")

    if not args.apply:
        print("\nNur Vorschau. Für Freigabe --apply verwenden.")
        return

    if not sys.stdin.isatty():
        raise SystemExit("Interaktive Freigabe erforderlich")

    print("\nACHTUNG: Echte Nextcloud-Schreiboperationen")
    print("Zur Bestätigung exakt eingeben:")
    print(CONFIRMATION)

    if input("Freigabe: ").strip() != CONFIRMATION:
        raise SystemExit("Upload nicht freigegeben")

    # Nach Freigabe Cache erneut einlesen und vergleichen.
    current_bytes = CACHE.read_bytes()

    if sha256(current_bytes).hexdigest() != original_sha:
        raise SystemExit("Cache wurde verändert: Upload abgebrochen")

    approved_package = load_package(current_bytes)

    # Nextcloud unmittelbar vor der Ausführung erneut lesen.
    second_preview = build_review_preview(
        approved_package,
        transport=reader,
    )

    if (
        second_preview["status"] != "READY"
        or manifest(second_preview) != manifest(preview)
    ):
        raise SystemExit(
            "Review-Paket oder Nextcloud-Zustand verändert"
        )

    # Erst ab hier sind WebDAV-Schreiboperationen erlaubt.
    writer = NextcloudReviewWriteTransport(
        **connection,
        mkcol=create_review_directory,
        put=upload_review_file,
    )

    result = execute_review_package(
        approved_package,
        transport=writer,
    )

    print("\n===== AUSFÜHRUNGSERGEBNIS =====")

    for action in result["results"]:
        print(
            action["status"],
            action["operation"],
            action["path"],
        )

    print("Gesamtstatus:", result["status"])

    if result["status"] != "COMPLETED":
        raise SystemExit("Paketupload nicht vollständig abgeschlossen")


if __name__ == "__main__":
    main()
