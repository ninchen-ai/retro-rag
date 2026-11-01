import re


OUTPUT_PATTERNS = {
    "vga": (
        r"\bVGA\s+Monitor\s+Connector\b",
        r"\bD-Sub\s+connectors?\b",
    ),
    "s-video": (
        r"\bS-Video\s+Output\b",
    ),
}

ALIASES = {
    "vga": "vga",
    "d-sub": "vga",
    "s-video": "s-video",
    "s video": "s-video",
}


def suggest_video_evidence(
    source: str,
    values: list[str],
) -> dict[str, str]:
    """Sucht passende Quellenbelege, ohne Daten zu verändern."""

    suggestions = {}

    if not isinstance(source, str):
        return suggestions

    if not isinstance(values, list):
        return suggestions

    for value in values:
        if not isinstance(value, str):
            continue

        key = ALIASES.get(value.strip().casefold())

        if key not in OUTPUT_PATTERNS:
            continue

        for pattern in OUTPUT_PATTERNS[key]:
            match = re.search(
                pattern,
                source,
                flags=re.IGNORECASE,
            )

            if match:
                # Kontext vor dem Treffer innerhalb derselben Zeile.
                line_start = source.rfind(
                    "\n", 0, match.start()
                ) + 1

                prefix = source[line_start:match.start()]

                # Eine verneinte Anschlussangabe darf nicht
                # als positiver Beleg vorgeschlagen werden.
                if re.search(
                    r"\b(?:no|without)\s*$",
                    prefix,
                    flags=re.IGNORECASE,
                ):
                    continue

                suggestions[value] = match.group(0)
                break

    return suggestions

def diagnose_model_video_outputs(
    source: str,
    target_model: str,
    values: list[str],
) -> dict:
    """Ermittelt alternative Belege ohne Änderung an den Quelldaten."""

    from llm_import.model_context import find_shared_board_layout
    from llm_import.validation import verify_video_outputs_evidence

    context = find_shared_board_layout(source, target_model)

    result = {
        "model": target_model,
        "context_status": context["status"],
        "model_evidence": context["model_evidence"],
        "suggestions": {},
        "valid": False,
    }

    if context["status"] != "SHARED":
        return result

    if not isinstance(values, list) or not values:
        return result

    suggestions = suggest_video_evidence(
        context["section"],
        values,
    )

    evidence = [
        suggestions.get(value, "")
        for value in values
    ]

    result["suggestions"] = suggestions
    result["valid"] = verify_video_outputs_evidence(
        values,
        evidence,
        context["section"],
    )

    return result

def video_suggestion_status(diagnostic: dict) -> str:
    """Bewertet ausschließlich alternative Quellenbelegvorschläge."""

    if (
        diagnostic.get("context_status") == "SHARED"
        and diagnostic.get("valid") is True
        and bool(diagnostic.get("suggestions"))
    ):
        return "EVIDENCE_SUGGESTED"

    return "UNCERTAIN"