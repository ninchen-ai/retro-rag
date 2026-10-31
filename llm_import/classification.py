"""Prüfung der Hardwareklassifikation vor der Extraktion."""


def validate_classification(
    classification: dict,
    source: str,
) -> list[dict]:
    """Gibt strukturierte Fehler zurück, ohne Quelldaten zu verändern."""

    findings = []

    category = classification.get("category")
    manufacturer = classification.get("manufacturer")
    model = classification.get("model")

    if category != "grafikkarte":
        findings.append({
            "code": "UNSUPPORTED_CATEGORY",
            "severity": "error",
            "field": "category",
            "message": (
                "Die automatische Extraktion unterstützt "
                "derzeit nur grafikkarte."
            ),
        })

    for field, value in (
        ("manufacturer", manufacturer),
        ("model", model),
    ):
        if not isinstance(value, str) or not value.strip():
            findings.append({
                "code": "MISSING_IDENTITY",
                "severity": "error",
                "field": field,
                "message": f"{field} fehlt oder ist ungültig.",
            })

        elif value.casefold() not in source.casefold():
            findings.append({
                "code": "IDENTITY_NOT_IN_SOURCE",
                "severity": "error",
                "field": field,
                "message": (
                    f"{field} ist im Quelldokument "
                    "nicht wörtlich belegbar."
                ),
            })

    return findings