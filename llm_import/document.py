"""Textextraktion für lokale Dateien und spätere WebDAV-Downloads."""

import pymupdf


MAX_BYTES = 50 * 1024 * 1024
MAX_CHARS = 18_000


def extract_document_text(data: bytes, filename: str) -> str:
    """Extrahiert Text aus TXT, MD oder PDF ohne Dateisystemzugriff."""

    if len(data) > MAX_BYTES:
        raise ValueError("Datei über 50 MiB")

    suffix = filename.lower().rsplit(".", 1)[-1]

    if suffix in ("txt", "md"):
        text = data.decode("utf-8-sig")

    elif suffix == "pdf":
        parts = []
        has_extractable_text = False

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError(
                    "Passwortgeschützte PDF: Review/OCR nötig"
                )

            for page_number, page in enumerate(doc, 1):
                page_text = page.get_text("text", sort=True)

                if page_text.strip():
                    has_extractable_text = True

                parts.append(
                    f"[PDF-Seite {page_number}]\n{page_text}"
                )

        if not has_extractable_text:
            raise ValueError(
                "Kein Text: Review/OCR erforderlich"
            )

        text = "\n".join(parts)
    else:
        raise ValueError("Nur .pdf, .txt und .md unterstützt")

    if not text.strip():
        raise ValueError("Kein Text: Review/OCR erforderlich")

    if len(text) > MAX_CHARS:
        raise ValueError(
            "Mehr als 18.000 Zeichen: "
            "abschnittsweise Verarbeitung erforderlich"
        )

    return text