"""Deterministische Erkennung von Gigabyte-Modellkandidaten."""

import re


GIGABYTE_GPU_MODEL = re.compile(
    r"\bGV-[A-Z0-9]+(?:-[A-Z0-9]+)*\b",
    re.IGNORECASE,
)


def detect_model_candidates(source: str) -> list[str]:
    """Liefert eindeutige Modellbezeichnungen in Fundreihenfolge."""

    candidates = []
    seen = set()

    for match in GIGABYTE_GPU_MODEL.finditer(source):
        model = match.group(0).upper()

        if model in seen:
            continue

        seen.add(model)
        candidates.append(model)

    return candidates