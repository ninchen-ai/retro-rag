"""Erkennt explizite Speicherkapazitäten einzelner Modellvarianten."""

import re


def extract_variant_memory(source: str, models: list[str]) -> dict[str, int | None]:
    """Erkennt eindeutige MB-Angaben direkt vor einer Modellbezeichnung."""

    results = {}

    for model in models:
        pattern = re.compile(
            rf"(?<!\w)(\d+)\s*MB\s*\(\s*{re.escape(model)}\s*\)",
            re.IGNORECASE,
        )

        values = {
            int(match.group(1))
            for match in pattern.finditer(source)
        }

        results[model] = next(iter(values)) if len(values) == 1 else None

    return results

def inspect_variant_memory(
    source: str,
    models: list[str],
) -> dict[str, dict]:
    """Bewertet explizite MB-Zuordnungen je Hardwaremodell."""

    results = {}

    for model in models:
        pattern = re.compile(
            rf"(?<!\w)(\d+)\s*MB\s*\(\s*{re.escape(model)}\s*\)",
            re.IGNORECASE,
        )

        matches = list(pattern.finditer(source))
        values = sorted({
            int(match.group(1))
            for match in matches
        })

        if not values:
            status = "UNKNOWN"
            value = None
        elif len(values) == 1:
            status = "VERIFIED"
            value = values[0]
        else:
            status = "CONFLICT"
            value = None

        results[model] = {
            "status": status,
            "value_mb": value,
            "candidates_mb": values,
            "evidence": [
                match.group(0)
                for match in matches
            ],
        }

    return results