"""Deterministische Sicherheitsprüfungen für Hardwarequellen."""

import re
from collections import defaultdict

FIELD_PATTERNS = {
    "core_clock_mhz": (
        r"(?im)^\s*Core Clock:\s*(\d+)\s*MHz\s*$"
    ),
    "memory_clock_mhz": (
        r"(?im)^\s*Memory Speed:\s*(\d+)\s*MHz\s*$"
    ),
    "memory_bus_width_bit": (
        r"(?im)^\s*Memory Bus:\s*(\d+)\s*bits?\s*$"
    ),
    "memory_size_mb": (
        r"(?im)^\s*Memory Size:\s*(\d+)\s*MB\s*$"
    ),
}

SPEC_LABELS = (
    "Graphics Processing Unit",
    "Interface",
    "Core Clock",
    "Memory Speed",
    "Memory Size",
    "Memory Type",
    "Memory Bus",
    "HDCP Support",
    "Card Dimension",
    "DirectX Version Support",
    "OpenGL Version Support",
)


def check_source(source, manufacturer, model):
    findings = []

    # 1. Widersprüchliche Zahlenwerte erkennen
    for field, pattern in FIELD_PATTERNS.items():
        values = re.findall(pattern, source, re.I)

        unique_values = sorted(set(map(int, values)))

        if len(unique_values) > 1:
            findings.append({
                "code": "CONFLICTING_VALUES",
                "field": field,
                "values": unique_values,
                "severity": "review",
            })

    # 2. Hersteller und Modell im Quelltext prüfen
    for field, value in (
        ("manufacturer", manufacturer),
        ("model", model),
    ):
        if (
            not isinstance(value, str)
            or not value.strip()
            or value.casefold() not in source.casefold()
        ):
            findings.append({
                "code": "MODEL_AMBIGUOUS",
                "field": field,
                "severity": "review",
            })

    # 3. Erkennbare technische Felder zählen
    recognized = sum(
        bool(re.search(
            rf"(?im)^\s*{re.escape(label)}\s*:",
            source
        ))
        for label in SPEC_LABELS
    )

    if recognized < 2:
        findings.append({
            "code": "INSUFFICIENT_DATA",
            "recognized_fields": recognized,
            "severity": "review",
        })

    return findings
