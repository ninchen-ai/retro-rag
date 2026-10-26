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
    # GPU-Hersteller und Chipbezeichnung trennen
    gpu_line = re.search(
        r"(?im)^Graphics Processing Unit:\s*"
        r"(NVIDIA|AMD|ATI|Intel)\s+(.+?)\s*$",
        source
    )

    if gpu_line:
        vendor = gpu_line.group(1)
        chip = gpu_line.group(2).strip()
        original = gpu_line.group(0).strip()

        if specs.get("gpu_manufacturer") in (None, vendor):
            if specs.get("gpu_chip") in (
                None, chip, f"{vendor} {chip}"
            ):
                specs["gpu_manufacturer"] = vendor
                specs["gpu_chip"] = chip

                evidence["gpu_manufacturer"] = {
                    "value": vendor,
                    "evidence": original,
                    "origin": "deterministic"
                }
                evidence["gpu_chip"] = {
                    "value": chip,
                    "evidence": original,
                    "origin": "deterministic"
                }
            else:
                issues.append(
                    "GPU-Chip widerspricht dem Quelltext"
                )
        else:
            issues.append(
                "GPU-Hersteller widerspricht dem Quelltext"
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
