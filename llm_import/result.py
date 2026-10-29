"""Strukturiertes Ergebnis der LLM-Dokumentverarbeitung."""

import hashlib
from dataclasses import asdict
from pathlib import Path


def build_import_result(
    *,
    source_path: Path,
    source_bytes: bytes,
    model: str,
    classification: dict,
    markdown: str,
    review,
    evidence: dict,
) -> dict:
    """Erstellt ein JSON-kompatibles Importergebnis ohne Schreibzugriff."""

    return {
        "schema_version": "1.0",
        "source": {
            "filename": source_path.name,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
        },
        "model": model,
        "classification": dict(classification),
        "review": {
            "status": review.status,
            "findings": [
                asdict(finding)
                for finding in review.findings
            ],
        },
        "evidence": evidence,
        "markdown": markdown,
    }