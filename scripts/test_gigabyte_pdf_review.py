import getpass
import os
import re
import json

from llm_import.model_context import find_shared_board_layout
from llm_import.video_evidence import suggest_video_evidence
from llm_import.validation import verify_video_outputs_evidence
from llm_import.document import extract_document_text
from llm_import.webdav import (
    list_inbox_documents,
    download_inbox_document,
)
from scripts.import_llm import (
    process_multi_model_document,
    DEFAULT_URL,
)

url = "http://127.0.0.1:8080"
user = "nina"
filename = "vga_manual_r92s128t_e.pdf"

password = (
    os.getenv("NEXTCLOUD_APP_PASSWORD")
    or getpass.getpass("Nextcloud-App-Passwort: ")
)

documents = list_inbox_documents(
    url=url,
    user=user,
    password=password,
)

document = next(
    d for d in documents
    if d["filename"] == filename
)

pdf_bytes = download_inbox_document(
    url=url,
    user=user,
    password=password,
    document=document,
)

source = extract_document_text(pdf_bytes, filename)

print("\n===== MODELLBEZOGENE VIDEOAUSGÄNGE =====")

values = ["VGA", "S-Video"]

for model_name in (
    "GV-R92S128T",
    "GV-R92S64T",
    "GV-R92S256T",
):
    context = find_shared_board_layout(source, model_name)

    print(f"\nModell: {model_name}")
    print("Kontext:", context["status"])
    print("Modellbeleg:", context["model_evidence"])

    if context["status"] != "SHARED":
        print("Keine automatische Zuordnung")
        continue

    section = context["section"]
    suggestions = suggest_video_evidence(section, values)

    evidence = [
        suggestions.get(value, "")
        for value in values
    ]

    for value, snippet in zip(values, evidence):
        print(f"{value}: {snippet or 'KEIN BELEG'}")

    valid = verify_video_outputs_evidence(
        values,
        evidence,
        section,
    )

    print("Quellenprüfung:", valid)

print("\n===== QUELLENTEXT: VIDEOAUSGÄNGE =====")

lines = source.splitlines()

for index, line in enumerate(lines):
    if re.search(
        r"D-Sub|S-Video|TV-Out|VGA|connector",
        line,
        flags=re.IGNORECASE,
    ):
        print(f"\nFundstelle Zeile {index + 1}")

        for position in range(
            max(0, index - 1),
            min(len(lines), index + 2),
        ):
            print(f"{position + 1}: {lines[position]}")

result = process_multi_model_document(
    source_bytes=pdf_bytes,
    filename=filename,
    model="qwen3.5:4b",
    ollama_url=DEFAULT_URL,
)

for item in result["results"]:
    classification = item.get("classification", {})
    review = item.get("review", {})
    os_data = item.get("evidence", {}).get(
        "minimum_os_requirements"
    )
    video_data = item.get("evidence", {}).get(
        "video_outputs"
    )

    print("\n================================")
    print("Modell:", classification.get("model"))
    print("Status:", review.get("status"))
    print("OS-Mindestanforderungen:", os_data)
    print("Videoausgänge:", video_data)

    print("\n===== IMPORTER-DIAGNOSE =====")

    for message in item.get("diagnostics", []):
        print(message)

    for finding in review.get("findings", []):
        print(
            finding.get("code"),
            "|",
            finding.get("field"),
        )

    print("\n===== STRUKTURIERTE BELEGVORSCHLÄGE =====")

    suggestions = item.get("evidence_suggestions", {})

    print(
        json.dumps(
            suggestions,
            ensure_ascii=False,
            indent=2,
        )
    )

    os_errors = [
        finding
        for finding in review.get("findings", [])
        if finding.get("field") == "minimum_os_requirements"
    ]

    print("OS-Validierungsfehler:", len(os_errors))