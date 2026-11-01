"""Normalisierung technischer Hardwaredaten."""

import re


def extract_deterministic_gpu_fields(source: str) -> dict:
    """Extrahiert eindeutig bezeichnete GPU-Daten."""

    results = {}

    patterns = {
        "memory_clock_mhz": (
            r"(?im)^Memory Speed:\s*(\d+)\s*MHz\s*$"
        ),
        "dimensions_mm": (
            r"(?im)^Card Dimension:\s*"
            r"(\d+\s*[x×]\s*\d+\s*[x×]\s*\d+\s*mm)\s*$"
        ),
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, source)

        if not match:
            continue

        value = match.group(1).strip()

        if field == "memory_clock_mhz":
            value = int(value)

        results[field] = {
            "value": value,
            "evidence": match.group(0).strip(),
        }

    return results


def normalize_gpu_identity_and_apis(source, specs, evidence, issues):
    """Normalisiert GPU-Identität und Grafik-APIs."""
    # GPU-Identitäten aus strukturierten Datenblättern
    # und natürlich formulierten Handbüchern erkennen.
    gpu_patterns = (
        re.compile(
            r"(?im)^Graphics Processing Unit:\s*"
            r"(NVIDIA|AMD|ATI|Intel)\s+(.+?)\s*$"
        ),
        re.compile(
            r"(?im)\bPowered by\s+"
            r"(NVIDIA|AMD|ATI|Intel)\s+"
            r"([^\r\n]+?)\s+"
            r"Graphics Processing Unit\s*\(GPU\)"
        ),
    )

    identities = {}

    for pattern in gpu_patterns:
        for match in pattern.finditer(source):
            vendor = match.group(1)
            chip = match.group(2).strip()
            original = match.group(0).strip()

            key = (
                vendor.casefold(),
                chip.casefold(),
            )

            identities.setdefault(
                key,
                (vendor, chip, original),
            )

    if len(identities) > 1:
        # Unterschiedliche GPUs im selben Quelldokument.
        # Keine dokumentweite automatische Ergänzung.
        issues.append(
            "GPU_IDENTITY_AMBIGUOUS: "
            "Mehrere unterschiedliche GPU-Identitäten "
            "im Quelldokument erkannt"
        )

    elif len(identities) == 1:
        vendor, chip, original = next(
            iter(identities.values())
        )

        existing_vendor = specs.get("gpu_manufacturer")
        existing_chip = specs.get("gpu_chip")

        vendor_matches = (
            existing_vendor is None
            or existing_vendor.casefold() == vendor.casefold()
        )

        chip_matches = (
            existing_chip is None
            or existing_chip.casefold()
            in {
                chip.casefold(),
                f"{vendor} {chip}".casefold(),
            }
        )

        if vendor_matches and chip_matches:
            specs["gpu_manufacturer"] = vendor
            specs["gpu_chip"] = chip

            evidence["gpu_manufacturer"] = {
                "value": vendor,
                "evidence": original,
                "origin": "deterministic",
            }

            evidence["gpu_chip"] = {
                "value": chip,
                "evidence": original,
                "origin": "deterministic",
            }

        else:
            if not vendor_matches:
                issues.append(
                    "GPU-Hersteller widerspricht dem Quelltext"
                )

            if not chip_matches:
                issues.append(
                    "GPU-Chip widerspricht dem Quelltext"
                )

    # Grafik-APIs aus eindeutigen Quellenzeilen ableiten
    api_patterns = {
        "DirectX": r"(?im)^DirectX Version Support:\s*(\d+(?:\.\d+)*)\s*$",
        "OpenGL": r"(?im)^OpenGL Version Support:\s*(\d+(?:\.\d+)*)\s*$",
    }

    detected_apis = []
    api_evidence = []

    for api, pattern in api_patterns.items():
        match = re.search(pattern, source)
        if match:
            detected_apis.append(f"{api} {match.group(1)}")
            api_evidence.append(match.group(0).strip())

    if detected_apis:
        existing = specs.get("api_support") or []

        # Nur bekannte Darstellungsformen automatisch ersetzen.
        allowed_existing = set(detected_apis + api_evidence)

        if set(existing).issubset(allowed_existing):
            specs["api_support"] = detected_apis
            evidence["api_support"] = {
                "value": detected_apis,
                "evidence": api_evidence,
                "origin": "deterministic"
            }
        else:
            issues.append(
                "api_support: LLM und regelbasierte "
                "Extraktion weichen voneinander ab"
            )
def reconcile_deterministic_value(
    field_name: str,
    current,
    candidate,
    source_evidence: str,
    specs: dict,
    evidence: dict,
    issues: list,
) -> bool:
    """Sperrt ein Feld bei Abweichung zwischen LLM und Quellenprüfung.

    Rückgabe:
        True:  Widerspruch erkannt und Feld gesperrt.
        False: Kein Widerspruch.
    """

    if current == candidate:
        return False

    issues.append(
        f"{field_name}: Widerspruch zwischen LLM "
        f"({current!r}) und Quelle ({candidate!r})"
    )

    specs[field_name] = None

    evidence[field_name] = {
        "value": None,
        "evidence": "",
        "origin": "validation_conflict",
        "candidates": [current, candidate],
        "source_evidence": source_evidence,
    }

    return True