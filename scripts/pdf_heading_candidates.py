"""Conservative, read-only heading candidate discovery for PDFs without bookmarks.

Candidates are NOT automatically committed as chapter assignments. Printed
contents pages, running headers and tables require validation first.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

import pymupdf

# Main chapter lines found in typical technical manuals (e.g. "3 AGP3.0 ...").
_MAIN = re.compile(r"^(?P<number>[1-9][0-9]?)\s+(?P<title>[A-Za-z][^\n]{5,120})$")
_SUB = re.compile(r"^(?P<number>[1-9][0-9]?(?:\.[0-9]+){1,3})\s+(?P<title>[A-Za-z][^\n]{3,120})$")
_LEADERS = re.compile(r"(?:\.{3,}|…{2,})\s*\d*\s*$")
_LIST_OR_TABLE = re.compile(r"^(?:Table|Figure|List of|Contents|Revision|Page)\b", re.I)


@dataclass(frozen=True)
class HeadingCandidate:
    pdf_page: int
    level: int
    heading: str
    evidence: str
    confidence: str  # 'candidate': human review required


def detect_heading_lines(text: str, page_number: int, *, max_lines: int = 14) -> list[HeadingCandidate]:
    """Find plausible headings near the start of a PDF page.

    Does not guess internal headings, especially numbered lists and TOC entries.
    This is intentionally conservative: false negatives are preferable.
    """
    if page_number < 1:
        raise ValueError("PDF pages are 1-based")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates: list[HeadingCandidate] = []
    for index, line in enumerate(lines[:max_lines]):
        if _LEADERS.search(line) or _LIST_OR_TABLE.match(line):
            continue
        # Text extracted from multi-column tables frequently contains wide gaps.
        if re.search(r"\s{2,}", line):
            continue
        match = _SUB.fullmatch(line) or _MAIN.fullmatch(line)
        if match is None:
            continue
        title = match.group("title").strip()
        number = match.group("number")
        # Restrict to headings with a letter-based title; still only a candidate.
        if len(title.split()) < 2 or len(title) > 100:
            continue
        if title.endswith((".", ";", ":")):
            continue
        level = 1 if "." not in number else number.count(".") + 1
        # Chapter numbers in these engineering specifications are small;
        # e.g. "66 MHz Clock" is not chapter 66.
        if level == 1 and (int(number) > 20 or len(title) > 75):
            continue
        # Register fields often begin with an integer and an all-caps field label.
        # They are not section titles, even when extracted without column gaps.
        if level == 1 and re.match(r"^[A-Z][A-Z0-9_]{1,15}:", title):
            continue
        candidates.append(HeadingCandidate(
            pdf_page=page_number,
            level=level,
            heading=f"{number} {title}",
            evidence=f"line {index + 1} of first {max_lines} nonblank lines",
            confidence="candidate",
        ))
    return candidates


def filter_main_chapter_sequence(candidates: list[HeadingCandidate]) -> list[HeadingCandidate]:
    """Retain only ascending, consecutive main chapters across PDF pages.

    Does not certify subsection candidates; human review remains necessary.
    """
    next_main = 1
    accepted: list[HeadingCandidate] = []
    for item in candidates:
        if item.level == 1:
            number = int(item.heading.split(" ", 1)[0])
            if number != next_main:
                continue
            next_main += 1
        accepted.append(item)
    return accepted


def scan_document(raw: bytes, *, max_lines: int = 14) -> list[HeadingCandidate]:
    """Report potential headings from the original PDF, without DB writes."""
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDF")
        found: list[HeadingCandidate] = []
        for page_number, page in enumerate(doc, start=1):
            found.extend(detect_heading_lines(
                page.get_text("text", sort=True),
                page_number,
                max_lines=max_lines,
            ))
        return filter_main_chapter_sequence(found)
