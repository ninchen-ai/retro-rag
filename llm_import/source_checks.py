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

MANUAL_FIELD_PATTERNS = {
    "gpu_chip": (
        r"\bPowered by\s+"
        r"(?:NVIDIA|AMD|ATI|Intel)\s+"
        r"[^\r\n]+?\s+"
        r"Graphics Processing Unit\s*\(GPU\)"
    ),
    "interface": (
        r"\bSupports\s+AGP\s+\d+\s*X\b"
    ),
    "api_support": (
        r"\bSupports\s+Direct\s*X\s+"
        r"\d+(?:\.\d+)*\b"
    ),
}

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

    # 3. Unterschiedliche technische Eigenschaften zählen.
    recognized_labels = {
        label
        for label in SPEC_LABELS
        if re.search(
            rf"(?im)^\s*{re.escape(label)}\s*:",
            source,
        )
    }

    recognized_manual_fields = {
        field
        for field, pattern in MANUAL_FIELD_PATTERNS.items()
        if re.search(pattern, source, re.IGNORECASE)
    }

    # Strukturierte Bezeichnungen und Handbuchformulierungen
    # zu fachlichen Feldnamen zusammenführen.
    label_to_field = {
        "Graphics Processing Unit": "gpu_chip",
        "Interface": "interface",
        "Core Clock": "core_clock_mhz",
        "Memory Speed": "memory_clock_mhz",
        "Memory Size": "memory_size_mb",
        "Memory Type": "memory_type",
        "Memory Bus": "memory_bus_width_bit",
        "HDCP Support": "hdcp_support",
        "Card Dimension": "dimensions_mm",
        "DirectX Version Support": "api_support",
        "OpenGL Version Support": "api_support",
    }

    recognized_fields = {
        label_to_field[label]
        for label in recognized_labels
    }

    recognized_fields.update(recognized_manual_fields)

    recognized = len(recognized_fields)

    if recognized < 2:
        findings.append({
            "code": "INSUFFICIENT_DATA",
            "recognized_fields": recognized,
            "severity": "review",
        })

    return findings
