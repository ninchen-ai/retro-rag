
"""Kontrollierter Review-Paketdurchlauf mit injiziertem Test-Transport.

Keine direkte WebDAV-Anbindung und keine Kommandozeilenschnittstelle.
"""

from llm_import.review_package import plan_review_package
from llm_import.review_orchestrator import build_review_dry_run
from llm_import.review_executor import validate_execution_plan
from llm_import.review_resume import decide_review_upload


def execute_review_package(import_result: dict, *, transport) -> dict:
    """Prüft und verarbeitet ein Review-Paket über einen Test-Transport."""

    file_plan = plan_review_package(import_result)
    dry_run = build_review_dry_run(import_result)
    validate_execution_plan(dry_run)

    files = {
        entry["path"]: entry["content"].encode("utf-8")
        for entry in file_plan
    }

    if len(files) != len(file_plan):
        raise ValueError("Doppelte Dateipfade")

    actions = dry_run["actions"]
    expected_puts = {
        action["path"]: action["content_bytes"]
        for action in actions
        if action["operation"] == "PUT"
    }

    if set(files) != set(expected_puts):
        raise ValueError("Dateiplan stimmt nicht mit Ausführungsplan überein")

    for path, content in files.items():
        if len(content) != expected_puts[path]:
            raise ValueError(f"Abweichende Dateigröße: {path}")

    # Phase 1: Alle Dateien prüfen, bevor irgendeine Änderung erfolgt.
    precheck = {}

    for path, content in files.items():
        try:
            remote = transport.read(path)
            decision = decide_review_upload(
                local_content=content,
                remote_content=remote,
            )
        except Exception as exc:
            return {
                "status": "BLOCKED",
                "reason": type(exc).__name__,
                "results": [],
            }

        precheck[path] = decision["status"]

        if decision["status"] == "CONFLICT":
            return {
                "status": "BLOCKED",
                "reason": "CONFLICT",
                "results": [],
            }

    # Phase 2: Aktionen in der validierten Reihenfolge ausführen.
    results = []
    failed = False

    for action in actions:
        operation = action["operation"]
        path = action["path"]

        if failed:
            results.append({
                "operation": operation,
                "path": path,
                "status": "SKIPPED",
            })
            continue

        try:
            if operation == "VERIFY_DIRECTORY":
                if not transport.verify_directory(path):
                    raise RuntimeError("Basisverzeichnis fehlt")
                status = "EXISTS"

            elif operation == "MKCOL":
                status = transport.create_directory(path)
                if status not in {"CREATED", "EXISTS"}:
                    raise RuntimeError("Verzeichniserstellung fehlgeschlagen")

            elif operation == "PUT":
                if precheck[path] == "UNCHANGED":
                    status = "UNCHANGED"
                else:
                    try:
                        status = transport.upload(
                            path,
                            files[path],
                        )
                    except Exception:
                        # Ergebnis des PUT ist unklar.
                        # Ein erneutes GET kann den Erfolg bestätigen.
                        remote = transport.read(path)

                        decision = decide_review_upload(
                            local_content=files[path],
                            remote_content=remote,
                        )

                        if decision["status"] != "UNCHANGED":
                            raise RuntimeError(
                                "Upload-Ausgang nicht bestätigt"
                            )

                        status = "CONFIRMED"

                    if status not in {"CREATED", "CONFIRMED"}:
                        raise RuntimeError(
                            "Datei wurde nicht erstellt"
                        )

                    # Nachprüfung des tatsächlich gespeicherten Inhalts.
                    remote = transport.read(path)
                    decision = decide_review_upload(
                        local_content=files[path],
                        remote_content=remote,
                    )

                    if decision["status"] != "UNCHANGED":
                        raise RuntimeError("Upload-Nachprüfung fehlgeschlagen")

                    status = "CONFIRMED"

            results.append({
                "operation": operation,
                "path": path,
                "status": status,
            })

        except Exception as exc:
            failed = True
            results.append({
                "operation": operation,
                "path": path,
                "status": "FAILED",
                "error": type(exc).__name__,
            })

    return {
        "status": "FAILED" if failed else "COMPLETED",
        "results": results,
    }
