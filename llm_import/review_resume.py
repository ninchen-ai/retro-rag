
"""Entscheidungslogik für sichere Wiederaufnahme von Review-Uploads."""

import hashlib


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
