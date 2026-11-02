"""Entscheidungslogik für sichere Wiederaufnahme von Review-Uploads."""

import hashlib
from llm_import.nextcloud_review import read_review_file


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
