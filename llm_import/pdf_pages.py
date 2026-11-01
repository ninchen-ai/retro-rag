"""Seitenweise Textextraktion aus PDF-Dokumenten."""

import pymupdf


def extract_pdf_pages(
    data: bytes,
    max_bytes: int = 50 * 1024 * 1024,
    max_pages: int = 500,
) -> list[dict]:
    """Extrahiert PDF-Text mit Seitenbezug, ohne Dateien zu speichern."""

    if not data.startswith(b"%PDF-"):
        raise ValueError("Keine gültige PDF-Signatur")

    if len(data) > max_bytes:
        raise ValueError("PDF überschreitet die Größenbegrenzung")

    pages = []

    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        if len(pdf) > max_pages:
            raise ValueError("PDF enthält zu viele Seiten")

        for index, page in enumerate(pdf):
            text = page.get_text("text").strip()

            pages.append(
                {
                    "page": index + 1,
                    "text": text,
                    "characters": len(text),
                }
            )

    return pages