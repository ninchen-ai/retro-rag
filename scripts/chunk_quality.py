
"""Konservative Qualitätsklassifikation für PDF-Chunks."""

import re


INDEX_HEADINGS = {
    "index",
    "contents",
    "table of contents",
}


def classify_chunk(content):
    """Gibt content, index oder footer zurück."""

    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip()
    ]

    if not lines:
        return "footer"

    # Der PDF-Importer stellt eine Quellenzeile voran.
    # Beispiel: cusl2c-104 | PDF-Seite 43
    body_lines = lines[1:] if (
        "PDF-Seite" in lines[0]
        and "|" in lines[0]
    ) else lines

    if not body_lines:
        return "footer"

    body = "\n".join(body_lines)

    # Eine reine Handbuch-Fußzeile, z. B.
    # ASUS CUSL2-C User's Manual 43
    if (
        len(body) <= 120
        and len(body_lines) <= 2
        and re.search(
            r"user[’']s manual\s+\d+\s*$",
            body,
            flags=re.IGNORECASE,
        )
    ):
        return "footer"

    # Nur Überschriften unmittelbar am Textanfang
    # als Index/Inhaltsverzeichnis erkennen.
    for line in body_lines[:3]:
        heading = re.sub(
            r"[\s:.\-]+$", "", line
        ).casefold()

        if heading in INDEX_HEADINGS:
            return "index"

    return "content"


QUALITY_FACTORS = {
    "content": 1.0,
    "index": 0.65,
    "footer": 0.0,
}
