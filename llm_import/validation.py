"""Gemeinsame deterministische Feld- und Quellenvalidierung."""

import re


def normalize_evidence(text: str) -> str:
    return " ".join(
        text.strip().strip('"\'„“«»').split()
    ).casefold()


def empty_value(definition: dict):
    return [] if definition["type"] == "list" else None


def value_is_valid(value, definition: dict) -> bool:
    typ = definition["type"]

    if value is None:
        return bool(definition.get("nullable", False))

    if typ == "string":
        return isinstance(value, str) and bool(value.strip())

    if typ == "integer":
        return type(value) is int and value >= 0

    if typ == "boolean":
        return type(value) is bool

    if typ == "list":
        return (
            isinstance(value, list)
            and all(
                isinstance(x, str) and x.strip()
                for x in value
            )
        )

    return False


def verify_value(name: str, value, evidence: str) -> str | None:
    """Konservative Prüfungen; keine vollständige Faktenvalidierung."""

    if isinstance(value, int) and not isinstance(value, bool):
        if not re.search(rf"(?<!\d){value}(?!\d)", evidence):
            return f"{name}: Zahl {value} nicht im Beleg"

    if isinstance(value, str):
        if name in ("interface", "dimensions_mm") and "_" in value:
            return f"{name}: Wert unzulässig normalisiert"

    if name == "vram_mib" and value is not None:
        if not re.search(
            r"\bMiB\b",
            evidence,
            flags=re.IGNORECASE,
        ):
            return (
                "vram_mib: Quellbeleg nennt MiB "
                "nicht eindeutig (MB ≠ MiB)"
            )

    return None

def verify_api_support_evidence(
    values: list,
    evidence: list,
    source: str,
) -> bool:
    """Prüft API-Namen und Versionen gegen einzelne Quellenbelege."""

    if not isinstance(values, list) or not values:
        return False

    if not isinstance(evidence, list):
        return False

    if len(values) != len(evidence):
        return False

    normalized_source = normalize_evidence(source)

    for value, snippet in zip(values, evidence):
        if not isinstance(value, str) or not value.strip():
            return False

        if not isinstance(snippet, str) or not snippet.strip():
            return False

        normalized_snippet = normalize_evidence(snippet)

        if normalized_snippet not in normalized_source:
            return False

        match = re.fullmatch(
            r"(DirectX|OpenGL)\s+(\d+(?:\.\d+)*)",
            value,
            flags=re.IGNORECASE,
        )

        if not match:
            return False

        api_name, version = match.groups()

        if not re.search(
            rf"\b{re.escape(api_name)}\b",
            snippet,
            flags=re.IGNORECASE,
        ):
            return False

        if not re.search(
            rf"(?<![\d.]){re.escape(version)}(?![\d.])",
            snippet,
        ):
            return False

    return True

def verify_gpu_field_evidence(
    field: str,
    value,
    snippet: str,
    source: str,
) -> bool:
    """Prüft ausgewählte GPU-Felder gegen ihre Originalbelege."""

    if not isinstance(snippet, str) or not snippet.strip():
        return False

    if normalize_evidence(snippet) not in normalize_evidence(source):
        return False

    snippet = snippet.strip().strip('"')

    if field == "core_clock_mhz":
        if type(value) is not int or value < 0:
            return False

        match = re.fullmatch(
            r"Core Clocks?\s*:\s*(\d+)\s*MHz",
            snippet,
            flags=re.IGNORECASE,
        )

        return bool(match and int(match.group(1)) == value)

    if field == "memory_type":
        if not isinstance(value, str) or not value.strip():
            return False

        match = re.fullmatch(
            r"Memory Type\s*:\s*(.+)",
            snippet,
            flags=re.IGNORECASE,
        )

        return bool(
            match
            and normalize_evidence(match.group(1))
            == normalize_evidence(value)
        )

    if field == "hdcp_support":
        if type(value) is not bool:
            return False

        match = re.fullmatch(
            r"HDCP Support\s*:\s*(Yes|No|Y|N)",
            snippet,
            flags=re.IGNORECASE,
        )

        if not match:
            return False

        positive = match.group(1).casefold() in {"yes", "y"}
        return positive is value

    if field == "memory_clock_mhz":
        if type(value) is not int or value < 0:
            return False

        match = re.fullmatch(
            r"Memory Speed\s*:\s*(\d+)\s*MHz",
            snippet,
            flags=re.IGNORECASE,
        )

        return bool(match and int(match.group(1)) == value)

    if field == "memory_bus_width_bit":
        if type(value) is not int or value <= 0:
            return False

        match = re.fullmatch(
            r"Memory Bus\s*:\s*(\d+)\s*(?:bit|bits)",
            snippet,
            flags=re.IGNORECASE,
        )

        return bool(match and int(match.group(1)) == value)

    if field == "interface":
        if not isinstance(value, str) or not value.strip():
            return False

        match = re.fullmatch(
            r"Interface\s*:\s*(.+)",
            snippet,
            flags=re.IGNORECASE,
        )

        return bool(
            match
            and normalize_evidence(match.group(1))
            == normalize_evidence(value)
        )

    if field == "dimensions_mm":
        if not isinstance(value, str):
            return False

        pattern = (
            r"Card Dimensions?\s*:\s*"
            r"(\d+)\s*[x×*]\s*"
            r"(\d+)\s*[x×*]\s*"
            r"(\d+)\s*mm"
        )

        match = re.fullmatch(
            pattern,
            snippet,
            flags=re.IGNORECASE,
        )

        if not match:
            return False

        normalized_value = re.fullmatch(
            r"(\d+)\s*[x×*]\s*(\d+)\s*[x×*]\s*(\d+)\s*mm",
            value.strip(),
            flags=re.IGNORECASE,
        )

        return bool(
            normalized_value
            and match.groups() == normalized_value.groups()
        )

    if field in {"gpu_manufacturer", "gpu_chip"}:
        if not isinstance(value, str) or not value.strip():
            return False

        match = re.fullmatch(
            r"Graphics Processing Unit\s*:\s*"
            r"(NVIDIA|AMD|ATI|Intel)\s+(.+)",
            snippet,
            flags=re.IGNORECASE,
        )

        if not match:
            return False

        manufacturer, chip = match.groups()

        expected = (
            manufacturer
            if field == "gpu_manufacturer"
            else chip
        )

        return normalize_evidence(value) == normalize_evidence(expected)

    return False

GPU_SEMANTICALLY_VERIFIED_FIELDS = frozenset({
    "gpu_manufacturer",
    "gpu_chip",
    "core_clock_mhz",
    "memory_clock_mhz",
    "memory_bus_width_bit",
    "memory_type",
    "hdcp_support",
    "interface",
    "dimensions_mm",
    "api_support",
})


def classify_gpu_field_coverage(
    specs: dict,
) -> dict[str, str]:
    """Ermittelt die semantische Prüfabdeckung finaler GPU-Felder."""

    coverage = {}

    for field, value in specs.items():
        if value is None or value == []:
            coverage[field] = "MISSING"
        elif field in GPU_SEMANTICALLY_VERIFIED_FIELDS:
            coverage[field] = "VERIFICATION_AVAILABLE"
        else:
            coverage[field] = "UNVERIFIED"

    return coverage