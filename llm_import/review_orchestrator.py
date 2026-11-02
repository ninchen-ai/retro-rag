
"""Erstellt einen vollständigen Review-Dry-Run ohne Schreibzugriff."""

from llm_import.review_package import (
    plan_review_directories,
    plan_review_package,
)

REVIEW_ROOT = "Retro-Computing/Import/review"


def build_review_dry_run(import_result: dict) -> dict:
    """Validiert ein Review-Paket und plant dessen WebDAV-Aktionen."""

    if not isinstance(import_result, dict):
        raise ValueError("Import-Ergebnis muss ein Dictionary sein")

    file_plan = plan_review_package(import_result)
    directory_plan = plan_review_directories(file_plan)

    seen_paths = set()
    model_files = {}

    for entry in file_plan:
        path = entry["path"]
        content = entry["content"]

        if path in seen_paths:
            raise ValueError(f"Doppelter Dateipfad: {path}")
        seen_paths.add(path)

        if entry["status"] != "PLANNED":
            raise ValueError(f"Unerwarteter Dateistatus: {path}")

        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Leerer Dateiinhalt: {path}")

        model_directory = path.rsplit("/", 1)[0]
        filename = path.rsplit("/", 1)[1]

        model_files.setdefault(model_directory, set()).add(filename)

    for model_directory, filenames in model_files.items():
        model = model_directory.rsplit("/", 1)[1]
        expected = {
            f"{model}.md",
            f"{model}.review.md",
        }

        if filenames != expected:
            raise ValueError(
                f"Unvollständiges Review-Paket: {model_directory}"
            )

    actions = [{
        "operation": "VERIFY_DIRECTORY",
        "path": REVIEW_ROOT + "/",
        "status": "PLANNED",
    }]

    for path in directory_plan:
        actions.append({
            "operation": "MKCOL",
            "path": path,
            "status": "PLANNED",
        })

    for entry in file_plan:
        actions.append({
            "operation": "PUT",
            "path": entry["path"],
            "status": "PLANNED",
            "content_bytes": len(entry["content"].encode("utf-8")),
        })

    return {
        "mode": "DRY_RUN",
        "source_count": 1,
        "model_count": len(model_files),
        "directory_count": len(directory_plan),
        "file_count": len(file_plan),
        "actions": actions,
    }
