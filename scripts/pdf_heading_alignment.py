"""Read-only alignment of reviewed PDF heading proposals to original text lines.

The layout-derived title is *metadata*; original extracted PDF characters
remain unchanged. Ambiguous or unmatched anchors must be reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from collections.abc import Sequence
import re

import pymupdf

from scripts.pdf_heading_review import ReviewHeading

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class HeadingAlignment:
    pdf_page: int
    heading: str
    source: str
    status: str  # MATCHED / AMBIGUOUS / UNMATCHED
    start_line: int | None  # 0-based, in get_text('text', sort=True)
    line_count: int
    extracted_text: str | None


def _normalized(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().casefold()


def _targets(candidate: ReviewHeading) -> tuple[str, ...]:
    """Return permitted raw-text forms, without dropping technical symbols."""
    title = _normalized(candidate.heading)
    targets = [title]
    # A separated visual title, e.g. 'Chapter 1: AGP Electrical Design...'
    # can occur as two consecutive raw lines.
    if candidate.source.startswith("separated chapter"):
        label, separator, remainder = candidate.heading.partition(": ")
        if separator:
            targets.append(_normalized(label + " " + remainder))
    return tuple(dict.fromkeys(targets))


def align_page_headings(text: str, headings: Sequence[ReviewHeading]) -> list[HeadingAlignment]:
    """Locate each candidate in one original page's text.

    Only exact normalized one-line or adjacent two-line matches are accepted.
    This is deliberately a conservative diagnostic, not a fuzzy matcher.
    """
    lines = text.splitlines(keepends=True)
    stripped = [line.strip() for line in lines]
    result: list[HeadingAlignment] = []
    for heading in headings:
        targets = _targets(heading)
        occurrences: list[tuple[int, int]] = []
        for i in range(len(lines)):
            one = _normalized(stripped[i])
            if one in targets:
                occurrences.append((i, 1))
            if i + 1 < len(lines) and stripped[i] and stripped[i + 1]:
                two = _normalized(stripped[i] + " " + stripped[i + 1])
                # Avoid a second identical hit spanning a blank line.
                if two in targets:
                    occurrences.append((i, 2))
        occurrences = list(dict.fromkeys(occurrences))
        if len(occurrences) == 1:
            i, count = occurrences[0]
            result.append(HeadingAlignment(
                heading.pdf_page, heading.heading, heading.source, "MATCHED",
                i, count, "".join(lines[i:i + count]),
            ))
        else:
            status = "UNMATCHED" if not occurrences else "AMBIGUOUS"
            result.append(HeadingAlignment(
                heading.pdf_page, heading.heading, heading.source,
                status, None, 0, None,
            ))
    return result


def align_document_headings(raw: bytes, headings: Sequence[ReviewHeading]) -> list[HeadingAlignment]:
    """Match reviewed heading candidates against original per-page extraction."""
    by_page: dict[int, list[ReviewHeading]] = defaultdict(list)
    for heading in headings:
        by_page[heading.pdf_page].append(heading)
    result: list[HeadingAlignment] = []
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDF cannot be analyzed")
        invalid = [number for number in by_page if number < 1 or number > len(doc)]
        if invalid:
            raise ValueError(f"Invalid PDF page: {invalid}")
        for number in sorted(by_page):
            text = doc[number - 1].get_text("text", sort=True)
            result.extend(align_page_headings(text, by_page[number]))
    return result
