
"""Lesende Vorschau eines Retro-RAG-Review-Pakets.

Keine MKCOL- oder PUT-Aufrufe.
"""

from hashlib import sha256

from llm_import.review_package import plan_review_package
from llm_import.review_orchestrator import build_review_dry_run
from llm_import.review_executor import validate_execution_plan
from llm_import.review_resume import decide_review_upload


REVIEW_ROOT = "Retro-Computing/Import/review/"


def build_review_preview(import_result: dict, *, transport) -> dict:
    """Prüft ein Review-Paket ohne Schreibzugriff."""

    file_plan = plan_review_package(import_result)
    dry_run = build_review_dry_run(import_result)
    validate_execution_plan(dry_run)

    source_hash = import_result["results"][0]["source"]["sha256"]

    models = [
        item["classification"]["model"]
        for item in import_result["results"]
    ]

    directories = [
        action["path"]
        for action in dry_run["actions"]
        if action["operation"] == "MKCOL"
    ]

    root_exists = transport.verify_directory(REVIEW_ROOT)

    if not root_exists:
        return {
            "mode": "READ_ONLY",
            "status": "BLOCKED",
            "reason": "REVIEW_ROOT_MISSING",
            "source_sha256": source_hash,
            "models": models,
            "directories": directories,
            "files": [],
            "write_operations": 0,
        }

    files = []
    blocked = False

    for entry in file_plan:
        path = entry["path"]
        local_content = entry["content"].encode("utf-8")

        local_hash = sha256(local_content).hexdigest()

        try:
            remote = transport.read(path)

            decision = decide_review_upload(
                local_content=local_content,
                remote_content=remote,
            )

            status = decision["status"]

        except Exception:
            status = "ERROR"

        if status not in {"UPLOAD_REQUIRED", "UNCHANGED"}:
            blocked = True

        files.append({
            "path": path,
            "sha256": local_hash,
            "size_bytes": len(local_content),
            "status": status,
        })

    return {
        "mode": "READ_ONLY",
        "status": "BLOCKED" if blocked else "READY",
        "source_sha256": source_hash,
        "models": models,
        "directories": directories,
        "files": files,
        "write_operations": 0,
    }
