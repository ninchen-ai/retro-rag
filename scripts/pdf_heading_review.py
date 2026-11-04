"""Read-only, multi-style PDF heading review.

Combines existing scanners without promoting any candidate to a verified
chunk anchor. Structural audit of decimal-numbered documents is optional and
not meaningful for unnumbered sections.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from scripts.pdf_heading_candidates import HeadingCandidate
from scripts.pdf_layout_headings import scan_layout_document
from scripts.pdf_heading_styles import scan_alternative_styles

_DOTTED = re.compile(r"^([1-9][0-9]?)\.\s+")
_SEPARATED = re.compile(r"^Chapter\s+([1-9][0-9]?):\s+", re.I)
_NUMBERED = re.compile(r"^([1-9][0-9]?(?:\.\d+){0,3})\s+")
_MEASUREMENT_ROW = re.compile(r"^\d+(?:\.\d+)?\s+(?:ns|ps|ms|mhz|khz|mv|v)\s+\d+$", re.I)


@dataclass(frozen=True)
class ReviewHeading:
    pdf_page: int
    level: int
    heading: str
    source: str
    section_number: str | None
    status: str  # REVIEW REQUIRED for every candidate


@dataclass(frozen=True)
class ReviewReport:
    style: str
    headings: tuple[ReviewHeading, ...]
    warnings: tuple[str, ...]


def _main_numbers(items: list[HeadingCandidate], style: str) -> list[int]:
    values: list[int] = []
    for candidate in items:
        if candidate.level != 1:
            continue
        if style == "dotted":
            m = _DOTTED.match(candidate.heading)
        elif style == "separated":
            m = _SEPARATED.match(candidate.heading)
        else:
            m = _NUMBERED.match(candidate.heading)
        if m:
            values.append(int(m.group(1)))
    return values


def _consecutive(numbers: list[int]) -> bool:
    return bool(numbers) and numbers == list(range(1, len(numbers) + 1))


def build_heading_review(raw: bytes) -> ReviewReport:
    """Produce review metadata, never an automatically verified chapter map."""
    numbered = scan_layout_document(raw)
    alternate = scan_alternative_styles(raw)
    dotted = [h for h in alternate if h.evidence.startswith("dotted chapter")]
    separated = [h for h in alternate if h.evidence.startswith("separated chapter")]
    warnings: list[str] = []

    # Prefer a coherent main-heading numbering scheme over raw hit count.
    if _consecutive(_main_numbers(separated, "separated")):
        style = "separated"
        chosen = [h for h in alternate if h.evidence.startswith(("separated chapter", "unnumbered bold section"))]
    elif _consecutive(_main_numbers(dotted, "dotted")):
        style = "dotted"
        chosen = dotted + [h for h in numbered if h.level > 1]
    elif _consecutive(_main_numbers(numbered, "numbered")):
        style = "numbered"
        chosen = numbered
    else:
        style = "unresolved"
        chosen = numbered + alternate
        warnings.append("No coherent consecutive main-chapter numbering found")

    # Retain source + evidence, do not merge same-page candidate titles blindly.
    unique: dict[tuple[int, int, str], ReviewHeading] = {}
    for c in chosen:
        # Engineering timing tables sometimes resemble section numbers.
        if _MEASUREMENT_ROW.fullmatch(c.heading):
            continue
        m = _NUMBERED.match(c.heading)
        if style == "dotted" and c.level == 1:
            m = _DOTTED.match(c.heading)
        if style == "separated" and c.level == 1:
            m = _SEPARATED.match(c.heading)
        section_number = m.group(1) if m else None
        source = c.evidence.split(";", 1)[0]
        item = ReviewHeading(c.pdf_page, c.level, c.heading, source, section_number, "REVIEW REQUIRED")
        unique[(item.pdf_page, item.level, item.heading)] = item

    result = tuple(unique.values())
    # Numeric auditing deliberately not run for unnumbered headings, which
    # have no section numbers and may have repeated titles.
    if not result:
        warnings.append("No headings detected; use page-only chunking until reviewed")
    return ReviewReport(style, result, tuple(warnings))
