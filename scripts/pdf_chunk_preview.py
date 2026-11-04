"""Read-only proposed section chunks. NEVER stores or approves detected headings.

Every extractable character from a nonempty PDF page must survive, in order.
The preview attaches *unverified* section context; it is not ingest output.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

import pymupdf

from scripts.pdf_chapter_chunking import PdfChunk, split_preserving_text, DEFAULT_MAX_CHARS
from scripts.pdf_heading_review import build_heading_review
from scripts.pdf_heading_alignment import align_document_headings

USABLE = frozenset({"MATCHED", "MATCHED_COMPACT", "MATCHED_CHAPTER_ANCHOR"})


@dataclass(frozen=True)
class ChunkPreview:
    style: str
    chunks: tuple[PdfChunk, ...]
    empty_pages: tuple[int, ...]
    matched_headings: int
    skipped_headings: tuple[str, ...]
    lossless: bool
    verified: bool = False


def preview_section_chunks(raw: bytes, max_chars: int = DEFAULT_MAX_CHARS) -> ChunkPreview:
    """Generate unapproved, page-preserving chunks from aligned proposals.

    No PDF edits, DB writes, embeddings, or automated approvals.
    Refuse conflicting anchors on the same extracted text line.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    report = build_heading_review(raw)
    aligned = align_document_headings(raw, report.headings)
    by_page = defaultdict(list)
    skipped = []
    for heading, match in zip(report.headings, aligned, strict=True):
        if match.status not in USABLE or match.start_line is None:
            skipped.append(f"page {heading.pdf_page}: {heading.heading} [{match.status}]")
            continue
        by_page[heading.pdf_page].append((match.start_line, heading))
    for page_no, entries in by_page.items():
        indexes = [i for i, _ in entries]
        if len(indexes) != len(set(indexes)):
            raise ValueError(f"Conflicting section anchors on PDF page {page_no}")
        entries.sort(key=lambda item: item[0])

    chunks: list[PdfChunk] = []
    empty: list[int] = []
    hierarchy: list[str] = []
    lossless = True
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDF cannot be previewed")
        for number, page in enumerate(doc, 1):
            text = page.get_text("text", sort=True)
            if not text.strip():
                empty.append(number)
                continue
            lines = text.splitlines(keepends=True)
            anchors = by_page.get(number, [])
            boundaries = [(0, None)] + [(index, h) for index, h in anchors]
            starts = sorted(set(index for index, _ in boundaries))
            section_at = {index: h for index, h in boundaries if h is not None}
            produced: list[str] = []
            for idx, start in enumerate(starts):
                if start in section_at:
                    heading = section_at[start]
                    level = heading.level
                    hierarchy = hierarchy[:level - 1]
                    hierarchy.append(heading.heading)
                end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
                part = "".join(lines[start:end])
                context = " / ".join(hierarchy) if hierarchy else None
                # split_preserving_text intentionally skips whitespace-only input.
                # A lossless preview must retain such regions as well.
                pieces = ([part[i:i + max_chars] for i in range(0, len(part), max_chars)]
                          if part and not part.strip()
                          else split_preserving_text(part, max_chars))
                for piece in pieces:
                    chunks.append(PdfChunk(number, number, context, piece))
                    produced.append(piece)
            if "".join(produced) != text:
                lossless = False
    return ChunkPreview(
        style=report.style,
        chunks=tuple(chunks),
        empty_pages=tuple(empty),
        matched_headings=sum(len(v) for v in by_page.values()),
        skipped_headings=tuple(skipped),
        lossless=lossless,
    )
