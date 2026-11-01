import getpass
import os

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

    for finding in review.get("findings", []):
        print(
            finding.get("code"),
            "|",
            finding.get("field"),
        )

    os_errors = [
        finding
        for finding in review.get("findings", [])
        if finding.get("field") == "minimum_os_requirements"
    ]

    print("OS-Validierungsfehler:", len(os_errors))