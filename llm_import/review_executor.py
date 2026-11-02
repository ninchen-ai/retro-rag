
"""Simulierter Review-Executor ohne Netzwerk- oder Schreibzugriff."""

from copy import deepcopy
from llm_import.review_orchestrator import REVIEW_ROOT

ALLOWED_OPERATIONS = {
    "VERIFY_DIRECTORY",
    "MKCOL",
    "PUT",
}

def validate_execution_plan(dry_run: dict) -> None:
    """Prüft Pfade, Reihenfolge und Abhängigkeiten des Ausführungsplans."""

    if not isinstance(dry_run, dict):
        raise ValueError("Ungültiger Review-Plan")

    if dry_run.get("mode") != "DRY_RUN":
        raise ValueError("Nur Dry-Run-Pläne erlaubt")

    actions = dry_run.get("actions")

    if not isinstance(actions, list) or not actions:
        raise ValueError("Leerer oder ungültiger Aktionsplan")

    first = actions[0]

    if not isinstance(first, dict) or first != {
        "operation": "VERIFY_DIRECTORY",
        "path": REVIEW_ROOT + "/",
        "status": "PLANNED",
    }:
        raise ValueError("Basisverzeichnisprüfung fehlt")

    phase = "DIRECTORIES"
    seen_paths = set()
    created_directories = {REVIEW_ROOT + "/"}

    for action in actions[1:]:
        if not isinstance(action, dict):
            raise ValueError("Ungültiger Aktionseintrag")

        operation = action.get("operation")
        path = action.get("path")

        if operation not in {"MKCOL", "PUT"}:
            raise ValueError("Unzulässige Operation")

        if action.get("status") != "PLANNED":
            raise ValueError("Ungültiger Aktionsstatus")

        if not isinstance(path, str):
            raise ValueError("Ungültiger Aktionspfad")

        if not path.startswith(REVIEW_ROOT + "/"):
            raise ValueError("Pfad außerhalb des Review-Bereichs")

        if path in seen_paths:
            raise ValueError("Doppelter Aktionspfad")

        seen_paths.add(path)

        if operation == "MKCOL":
            if phase != "DIRECTORIES":
                raise ValueError("MKCOL nach PUT nicht erlaubt")

            if not path.endswith("/"):
                raise ValueError("MKCOL benötigt Verzeichnispfad")

            parent = path.rstrip("/").rsplit("/", 1)[0] + "/"

            if parent not in created_directories:
                raise ValueError("Übergeordnetes Verzeichnis fehlt")

            created_directories.add(path)

        else:
            phase = "FILES"

            if path.endswith("/"):
                raise ValueError("PUT benötigt Dateipfad")

            parent = path.rsplit("/", 1)[0] + "/"

            if parent not in created_directories:
                raise ValueError("PUT-Zielverzeichnis fehlt")

def simulate_review_execution(
    dry_run: dict,
    *,
    fail_at: int | None = None,
) -> dict:
    """Simuliert die Ausführung eines zuvor erstellten Review-Plans."""

    if not isinstance(dry_run, dict):
        raise ValueError("Ungültiger Review-Plan")

    if dry_run.get("mode") != "DRY_RUN":
        raise ValueError("Nur Dry-Run-Pläne erlaubt")

    actions = dry_run.get("actions")

    if not isinstance(actions, list) or not actions:
        raise ValueError("Leerer oder ungültiger Aktionsplan")

    if fail_at is not None:
        if type(fail_at) is not int or not 0 <= fail_at < len(actions):
            raise ValueError("Ungültige Fehlerposition")

    # Vor der Simulation den vollständigen Aktionsplan prüfen.
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Ungültiger Aktionseintrag")

        if action.get("operation") not in ALLOWED_OPERATIONS:
            raise ValueError("Unbekannte WebDAV-Operation")

        if action.get("status") != "PLANNED":
            raise ValueError("Aktion ist nicht im PLANNED-Status")

        if not isinstance(action.get("path"), str):
            raise ValueError("Ungültiger Aktionspfad")

    validate_execution_plan(dry_run)
    results = deepcopy(actions)
    failed = False

    for index, action in enumerate(results):
        if failed:
            action["status"] = "SKIPPED"
            continue

        if index == fail_at:
            action["status"] = "FAILED"
            action["message"] = "Simulierter Fehler"
            failed = True
            continue

        if action["operation"] == "VERIFY_DIRECTORY":
            action["status"] = "EXISTS"
        elif action["operation"] == "MKCOL":
            action["status"] = "CREATED"
        elif action["operation"] == "PUT":
            action["status"] = "CREATED"

    return {
        "mode": "SIMULATION",
        "status": "FAILED" if failed else "COMPLETED",
        "actions": results,
    }
