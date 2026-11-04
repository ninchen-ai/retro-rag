"""Read-only chapter-aware chunking using explicitly verified PDF heading anchors.

A heading must appear exactly once as a text line on the specified physical
PDF page. Unverified heading candidates are intentionally not accepted.
No DB writes; output preserves the full extractable text for each PDF page.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

import pymupdf

from scripts.pdf_chapter_chunking import (
    DEFAULT_MAX_CHARS,
    PdfChunk,
    split_preserving_text,
)

_NUMBER = re.compile(r"^([1-9][0-9]?(?:\.[0-9]+){0,3})\s+")


def _level(heading: str) -> int:
    match = _NUMBER.match(heading)
    return match.group(1).count(".") + 1 if match else 1


def _segments(text: str, anchors: Sequence[str]) -> list[tuple[str | None, str]]:
    """Split page text just before verified heading lines; never drop text."""
    lines = text.splitlines(keepends=True)
    starts: list[tuple[int, str]] = []
    for heading in anchors:
        matches = [
            i for i, line in enumerate(lines)
            if line.strip() == heading
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Heading must match exactly once on its page: {heading!r}; "
                f"matched {len(matches)} times"
            )
        starts.append((matches[0], heading))
    if len({i for i, _ in starts}) != len(starts):
        raise ValueError("Different headings point to the same text line")
    starts.sort()
    result: list[tuple[str | None, str]] = []
    cursor = 0
    for index, heading in starts:
        if cursor < index:
            result.append((None, "".join(lines[cursor:index])))
        cursor = index
        next_index = next((j for j, _ in starts if j > index), len(lines))
        result.append((heading, "".join(lines[index:next_index])))
        cursor = next_index
    if cursor < len(lines):
        result.append((None, "".join(lines[cursor:])))
    return result


def extract_verified_section_chunks(
    raw: bytes,
    verified_headings: Mapping[int, Sequence[str]],
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[list[PdfChunk], list[int]]:
    """Chunk pages at verified line-anchored section starts.

    Heading context changes at the exact line. Running headers before a heading
    remain in the preceding section. Every extractable character is preserved.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    chunks: list[PdfChunk] = []
    empty_pages: list[int] = []
    hierarchy: list[str] = []
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDF cannot be indexed")
        if any(type(page) is not int or page < 1 or page > len(doc)
               for page in verified_headings):
            raise ValueError("Heading references an invalid physical PDF page")
        for page_number, page in enumerate(doc, 1):
            text = page.get_text("text", sort=True)
            if not text.strip():
                if verified_headings.get(page_number):
                    raise ValueError("Heading assigned to a page without text")
                empty_pages.append(page_number)
                continue
            for heading, content in _segments(
                text, verified_headings.get(page_number, ())
            ):
                if heading is not None:
                    level = _level(heading)
                    hierarchy = hierarchy[:level - 1]
                    hierarchy.append(heading)
                current = " / ".join(hierarchy) if hierarchy else None
                for part in split_preserving_text(content, max_chars):
                    chunks.append(PdfChunk(page_number, page_number, current, part))
    return chunks, empty_pages
