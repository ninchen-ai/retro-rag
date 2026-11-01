"""Erzeugt nachvollziehbare Textabschnitte aus PDF-Seiten."""


def chunk_pdf_pages(
    pages: list[dict],
    max_chars: int = 6000,
) -> list[dict]:
    """Gruppiert Seiten, ohne Seiteninhalte zu zerschneiden."""

    if max_chars <= 0:
        raise ValueError("max_chars muss positiv sein")

    chunks = []
    current_pages = []
    current_texts = []
    current_length = 0

    def flush():
        nonlocal current_pages, current_texts, current_length

        if not current_pages:
            return

        chunks.append(
            {
                "chunk": len(chunks) + 1,
                "pages": current_pages.copy(),
                "text": "\n\n".join(current_texts),
            }
        )

        current_pages = []
        current_texts = []
        current_length = 0

    for page in pages:
        text = page["text"].strip()

        if not text:
            continue

        page_number = page["page"]

        if len(text) > max_chars:
            raise ValueError(
                f"Seite {page_number} überschreitet "
                f"das Chunk-Limit ({max_chars} Zeichen)"
            )

        separator_length = 2 if current_texts else 0

        if (
            current_pages
            and current_length + separator_length + len(text) > max_chars
        ):
            flush()
            separator_length = 0

        current_pages.append(page_number)
        current_texts.append(text)
        current_length += separator_length + len(text)

    flush()

    return chunks