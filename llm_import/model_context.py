import re


def find_shared_board_layout(
    source: str,
    target_model: str,
) -> dict:
    """Sucht einen ausdrücklich gemeinsam beschriebenen Board-Layout-Abschnitt."""

    result = {
        "status": "UNCERTAIN",
        "model_evidence": "",
        "section": "",
    }

    if not isinstance(source, str) or not isinstance(target_model, str):
        return result

    if not target_model.strip():
        return result

    match = re.search(
        r"(?im)^[^\r\n]*1\.2\.\s*Board Layout\s*$",
        source,
    )

    if not match:
        return result

    remaining = source[match.end():]

    # Gemeinsamen Abschnitt an der nächsten PDF-Seite
    # oder einer folgenden nummerierten Kapitelüberschrift beenden.
    boundary = re.search(
        r"(?m)^[ \t]*(?:"
        r"\[PDF-Seite \d+\][ \t]*"
        r"|\d+(?:\.\d+)*\.\s+[^\r\n]+"
        r")$",
        remaining,
    )

    if boundary:
        remaining = remaining[:boundary.start()]

    lines = remaining.splitlines()

    model_line = next(
        (
            line.strip()
            for line in lines[:10]
            if target_model.casefold() in line.casefold()
        ),
        None,
    )

    if model_line is None:
        return result

    # Die erste Modellzeile muss mindestens zwei
    # unterschiedliche Gigabyte-Modellbezeichnungen enthalten.
    models = set(
        re.findall(
            r"\bGV-R92S\d+[A-Z0-9]*\b",
            model_line,
            flags=re.IGNORECASE,
        )
    )

    if len(models) < 2:
        return result

    result["status"] = "SHARED"
    result["model_evidence"] = model_line
    result["section"] = remaining

    return result