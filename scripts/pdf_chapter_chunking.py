"""Read-only, outline-aware PDF text chunking with page provenance.

No database writes or Ollama calls. A PDF outline/bookmark is a hint:
some pages contain more than one section, and images are not parsed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pymupdf

CHUNKER_VERSION = "pdf-outline-v1"
DEFAULT_MAX_CHARS = 2500


@dataclass(frozen=True)
class PdfChunk:
    page_start: int  # Physical PDF page, 1-based
    page_end: int
    heading: str | None
    content: str  # Exact extracted text, no synthetic title/page prefix


def split_preserving_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split without discarding characters; concatenation restores input."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if not text or not text.strip():
        return []

    parts: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        cut = -1
        for delimiter in ("\n\n", "\n", " "):
            pos = window.rfind(delimiter, max_chars // 2)
            if pos >= 0:
                cut = pos + len(delimiter)
                break
        if cut <= 0:
            cut = max_chars
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        parts.append(remaining)
    return parts


def outline_by_page(toc: Iterable[list], page_count: int) -> dict[int, str]:
    """Map outline page starts to hierarchical headings."""
    result: dict[int, str] = {}
    stack: list[str] = []
    for entry in toc:
        if len(entry) < 3:
            continue
        level, title, page = entry[:3]
        if not isinstance(level, int) or level < 1:
            continue
        if not isinstance(page, int) or not 1 <= page <= page_count:
            continue
        title = str(title).strip()
        if not title:
            continue
        stack = stack[:max(0, level - 1)]
        stack.append(title)
        result[page] = " / ".join(stack)
    return result


def extract_chunks(raw: bytes, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[list[PdfChunk], list[int]]:
    """Extract per-page chunks and list of PDF pages without searchable text.

    Bookmark headings are page-level hints, not verified section boundaries.
    Text stays unmodified, including whitespace at chunk boundaries.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    chunks: list[PdfChunk] = []
    empty_pages: list[int] = []
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("Password-protected PDF cannot be indexed")
        bookmarks = outline_by_page(document.get_toc(), len(document))
        heading: str | None = None
        for page_number, page in enumerate(document, start=1):
            if page_number in bookmarks:
                heading = bookmarks[page_number]
            text = page.get_text("text", sort=True)
            if not text.strip():
                empty_pages.append(page_number)
                continue
            for part in split_preserving_text(text, max_chars=max_chars):
                chunks.append(PdfChunk(page_number, page_number, heading, part))
    return chunks, empty_pages
