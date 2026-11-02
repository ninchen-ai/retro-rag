"""Entscheidungslogik für sichere Wiederaufnahme von Review-Uploads."""

import hashlib
from llm_import.nextcloud_review import read_review_file
from llm_import.review_package import plan_review_package
from llm_import.review_orchestrator import build_review_dry_run
from llm_import.review_executor import validate_execution_plan


def sha256_content(content: bytes) -> str:
    """Berechnet den SHA-256-Hash eines Dateiinhalts."""
    if not isinstance(content, bytes):
        raise ValueError("Dateiinhalt muss bytes sein")

    return hashlib.sha256(content).hexdigest()


def decide_review_upload(
    *,
    local_content: bytes,
    remote_content: bytes | None,
) -> dict:
    """Entscheidet über einen Upload ohne Netzwerk- oder Schreibzugriff."""

    local_hash = sha256_content(local_content)

    if remote_content is None:
        return {
            "status": "UPLOAD_REQUIRED",
            "local_sha256": local_hash,
            "remote_sha256": None,
        }

    remote_hash = sha256_content(remote_content)

    if local_hash == remote_hash:
        return {
            "status": "UNCHANGED",
            "local_sha256": local_hash,
            "remote_sha256": remote_hash,
        }

    return {
        "status": "CONFLICT",
        "local_sha256": local_hash,
        "remote_sha256": remote_hash,
    }

def inspect_review_upload(
    *,
    base_url: str,
    user: str,
    password: str,
    path: str,
    local_content: bytes,
) -> dict:
    """Prüft eine Review-Datei lesend auf Wiederaufnahmefähigkeit.

    Keine WebDAV-Schreiboperationen.
    """

    # Ungültige lokale Inhalte vor dem Netzwerkzugriff ablehnen.
    local_hash = sha256_content(local_content)

    remote_content = read_review_file(
        base_url=base_url,
        user=user,
        password=password,
        path=path,
    )

    decision = decide_review_upload(
        local_content=local_content,
        remote_content=remote_content,
    )

    return {
        "path": path,
        "status": decision["status"],
        "local_sha256": local_hash,
        "remote_sha256": decision["remote_sha256"],
    }

def inspect_review_package(
    import_result: dict,
    *,
    base_url: str,
    user: str,
    password: str,
) -> dict:
    """Prüft ein vollständiges Review-Paket lesend vor.

    Führt keine WebDAV-Schreiboperationen aus.
    """

    # Zuerst das gesamte Paket lokal planen und validieren.
    file_plan = plan_review_package(import_result)
    dry_run = build_review_dry_run(import_result)
    validate_execution_plan(dry_run)

    planned_puts = {
        action["path"]: action
        for action in dry_run["actions"]
        if action["operation"] == "PUT"
    }

    actual_paths = {entry["path"] for entry in file_plan}

    if len(actual_paths) != len(file_plan):
        raise ValueError("Doppelte Quelldateipfade")

    if actual_paths != set(planned_puts):
        raise ValueError("Dateiplan stimmt nicht mit Dry-Run überein")

    # Vor jedem Netzwerkzugriff alle geplanten Inhalte abgleichen.
    for entry in file_plan:
        path = entry["path"]
        content = entry["content"].encode("utf-8")

        if len(content) != planned_puts[path]["content_bytes"]:
            raise ValueError(
                f"Dateigröße stimmt nicht mit Dry-Run überein: {path}"
            )

    results = []
    blocked = False

    for entry in file_plan:
        path = entry["path"]
        content = entry["content"].encode("utf-8")

        try:
            result = inspect_review_upload(
                base_url=base_url,
                user=user,
                password=password,
                path=path,
                local_content=content,
            )

            if result["path"] != path or result["status"] not in {
                "UPLOAD_REQUIRED", "UNCHANGED", "CONFLICT"
            }:
                raise RuntimeError("Ungültige Antwort der Datei-Vorprüfung")

        except Exception as exc:
            results.append({
                "path": path,
                "status": "FAILED",
                "error": type(exc).__name__,
            })
            blocked = True
            break

        results.append(result)

        if result["status"] == "CONFLICT":
            blocked = True
            break

    if blocked:
        for entry in file_plan[len(results):]:
            results.append({
                "path": entry["path"],
                "status": "SKIPPED",
            })

    return {
        "mode": "PRECHECK",
        "status": "BLOCKED" if blocked else "READY",
        "file_count": len(file_plan),
        "results": results,
    }

def verify_uncertain_review_upload(
    *,
    base_url: str,
    user: str,
    password: str,
    path: str,
    local_content: bytes,
) -> dict:
    """Prüft den Zustand nach einem unklaren PUT-Ergebnis.

    Ausschließlich lesend. Keine erneute Übertragung.
    """

    # Ungültige Eingaben vor jeglichem Netzwerkzugriff ablehnen.
    local_hash = sha256_content(local_content)

    try:
        remote_content = read_review_file(
            base_url=base_url,
            user=user,
            password=password,
            path=path,
        )
    except Exception as exc:
        return {
            "path": path,
            "status": "UNKNOWN",
            "local_sha256": local_hash,
            "remote_sha256": None,
            "error": type(exc).__name__,
        }

    decision = decide_review_upload(
        local_content=local_content,
        remote_content=remote_content,
    )

    status_mapping = {
        "UPLOAD_REQUIRED": "MISSING",
        "UNCHANGED": "CONFIRMED",
        "CONFLICT": "CONFLICT",
    }

    return {
        "path": path,
        "status": status_mapping[decision["status"]],
        "local_sha256": local_hash,
        "remote_sha256": decision["remote_sha256"],
    }

def plan_package_resume(precheck: dict) -> dict:
    """Plant einen Wiederanlauf anhand einer Paketvorprüfung.

    Rein lokale Auswertung; kein Netzwerk- oder Schreibzugriff.
    """

    if not isinstance(precheck, dict):
        raise ValueError("Ungültige Paketvorprüfung")

    if precheck.get("mode") != "PRECHECK":
        raise ValueError("Nur PRECHECK-Ergebnisse erlaubt")

    results = precheck.get("results")
    file_count = precheck.get("file_count")

    if not isinstance(results, list) or not results:
        raise ValueError("Keine Dateiergebnisse vorhanden")

    if type(file_count) is not int or file_count != len(results):
        raise ValueError("Unvollständige Paketvorprüfung")

    allowed = {
        "UNCHANGED",
        "UPLOAD_REQUIRED",
        "CONFLICT",
        "FAILED",
        "UNKNOWN",
        "SKIPPED",
    }

    seen = set()
    decisions = []
    blocked = False

    for item in results:
        if not isinstance(item, dict):
            raise ValueError("Ungültiger Dateieintrag")

        path = item.get("path")
        status = item.get("status")

        if not isinstance(path, str) or not path:
            raise ValueError("Ungültiger Dateipfad")

        if path in seen:
            raise ValueError("Doppelter Dateipfad")

        seen.add(path)

        if status not in allowed:
            raise ValueError(f"Unbekannter Dateistatus: {status}")

        if status in {"CONFLICT", "FAILED", "UNKNOWN", "SKIPPED"}:
            blocked = True

        decisions.append({
            "path": path,
            "precheck_status": status,
            "action": (
                "SKIP_IDENTICAL" if status == "UNCHANGED"
                else "UPLOAD_CANDIDATE" if status == "UPLOAD_REQUIRED"
                else "BLOCK"
            ),
        })

    # Bei einem einzigen problematischen Ergebnis
    # wird kein Upload-Kandidat freigegeben.
    if blocked:
        for decision in decisions:
            if decision["action"] == "UPLOAD_CANDIDATE":
                decision["action"] = "BLOCK"

    return {
        "mode": "RESUME_PLAN",
        "status": "BLOCKED" if blocked else "READY",
        "file_count": file_count,
        "decisions": decisions,
    }
