"""Read-only PDF heading proposals derived from visual text layout.

A candidate is not verified: do not feed results directly into the database
or into section anchors without review. Page coordinates are PDF points.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
import re

import pymupdf

from scripts.pdf_heading_candidates import HeadingCandidate

_HEADING = re.compile(r"^(?P<number>[1-9]\d?(?:\.\d+){0,3})\s+(?P<title>[A-Za-z][^\n]{3,120})$")
_LEADERS = re.compile(r"\.{3,}|…{2,}")
_REGISTER = re.compile(r"^[A-Z][A-Z0-9_]{1,15}:")


@dataclass(frozen=True)
class VisualLine:
    text: str
    x: float
    y: float
    size: float
    bold: bool
    pieces: int


def visual_lines(page: pymupdf.Page, *, y_tolerance: float = 2.0) -> list[VisualLine]:
    """Merge same-baseline PDF lines within the same text block.

    Merged text is metadata only and never replaces the original PDF text.
    """
    if y_tolerance < 0:
        raise ValueError("y_tolerance cannot be negative")
    result: list[VisualLine] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type", 0) != 0:
            continue
        rows: list[list[dict]] = []
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s["text"].strip()]
            if not spans:
                continue
            baseline = min(float(s["bbox"][1]) for s in spans)
            row = next((r for r in rows if abs(min(float(s["bbox"][1]) for s in r) - baseline) <= y_tolerance), None)
            if row is None:
                row = []
                rows.append(row)
            row.extend(spans)
        for spans in rows:
            spans.sort(key=lambda s: float(s["bbox"][0]))
            joined = " ".join(s["text"].strip() for s in spans).strip()
            if not joined:
                continue
            result.append(VisualLine(
                text=" ".join(joined.split()),
                x=min(float(s["bbox"][0]) for s in spans),
                y=min(float(s["bbox"][1]) for s in spans),
                size=max(float(s["size"]) for s in spans),
                bold=all("bold" in s["font"].lower() for s in spans),
                pieces=len(spans),
            ))
    return sorted(result, key=lambda r: (r.y, r.x))


def detect_page_layout_headings(page: pymupdf.Page, page_number: int) -> list[HeadingCandidate]:
    """Propose numbered bold headings from any vertical position on a page."""
    if page_number < 1:
        raise ValueError("PDF pages are 1-based")
    text = page.get_text("text", sort=True)
    opening = "\n".join(text.splitlines()[:8]).lower()
    if any(marker in opening for marker in ("table of contents", "list of figures", "list of tables")):
        return []
    lines = visual_lines(page)
    body_sizes = [row.size for row in lines if not row.bold]
    body_size = median(body_sizes) if body_sizes else 0.0
    result: list[HeadingCandidate] = []
    for row in lines:
        match = _HEADING.fullmatch(row.text)
        if not match or _LEADERS.search(row.text):
            continue
        number, title = match.group("number"), match.group("title")
        if len(title) > 90 or title.endswith((".", ";")):
            continue
        # Register-named subsections (e.g. 5.8.4 AGPSTAT: ...) are valid.
        # Only unqualified main-number register labels remain suspicious.
        if "." not in number and _REGISTER.match(title):
            continue
        if not row.bold or (body_size and row.size + 0.25 < body_size):
            continue
        if number.count(".") == 0 and int(number) > 20:
            continue
        result.append(HeadingCandidate(
            pdf_page=page_number,
            level=number.count(".") + 1,
            heading=f"{number} {title}",
            evidence=(f"visual y={row.y:.1f}, x={row.x:.1f}, "
                      f"size={row.size:.1f}pt, bold, pieces={row.pieces}"),
            confidence="candidate",
        ))
    return result


def scan_layout_document(raw: bytes) -> list[HeadingCandidate]:
    """Scan all pages; no DB writes, no automatic heading approval."""
    results: list[HeadingCandidate] = []
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDF cannot be analyzed")
        for number, page in enumerate(doc, 1):
            results.extend(detect_page_layout_headings(page, number))
    return results
