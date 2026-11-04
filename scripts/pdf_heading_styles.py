"""Read-only proposals for non-AGP3-style headings.

Supports '1. Introduction', separated 'Chapter 1' / 'Title', and unnumbered
bold subsections. The original PDF text is never changed. The returned
candidates are unverified and must NOT be used as automatic chunk anchors.
"""
from __future__ import annotations

from collections import Counter
import re

import pymupdf

from scripts.pdf_heading_candidates import HeadingCandidate
from scripts.pdf_layout_headings import visual_lines, VisualLine

_DOTTED_CHAPTER = re.compile(r"^(?P<number>[1-9][0-9]?)\.\s+(?P<title>[A-Za-z].{3,100})$")
_CHAPTER_LABEL = re.compile(r"^Chapter\s+(?P<number>[1-9][0-9]?)$", re.I)
_PAGE_NUMBER = re.compile(r"^\d{1,3}$")
_EXCLUDE = re.compile(
    r"^(?:table of contents|contents|figures|tables|revision|copyright|"
    r"preface$|list of (?:figures|tables)|figure\s+\d|table\s+\d)",
    re.I,
)


def _candidate(page: int, level: int, heading: str, row: VisualLine, evidence: str) -> HeadingCandidate:
    return HeadingCandidate(
        pdf_page=page,
        level=level,
        heading=heading,
        evidence=f"{evidence}; y={row.y:.1f}, size={row.size:.1f}pt",
        confidence="candidate",
    )


def scan_alternative_styles(raw: bytes) -> list[HeadingCandidate]:
    """Collect alternative-format headings, with document-level header filtering.

    Does not infer section numbers for unnumbered headings, and does not
    reinterpret the numbering of existing numbered sections.
    """
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDF cannot be analyzed")
        pages = [visual_lines(page) for page in doc]
        frequency = Counter(
            row.text.casefold()
            for rows in pages
            for row in rows
            if row.bold
        )
        output: list[HeadingCandidate] = []
        chapter_page_starts: set[int] = set()
        for page_number, rows in enumerate(pages, 1):
            if not rows:
                continue
            opening = " ".join(row.text.lower() for row in rows[:5])
            if "table of contents" in opening or "list of figures" in opening or "list of tables" in opening:
                continue
            for i, row in enumerate(rows):
                text = row.text.strip()
                if not row.bold or _PAGE_NUMBER.fullmatch(text):
                    continue
                # Repeated page headers are not section titles.
                if frequency[text.casefold()] >= 3:
                    continue
                match = _DOTTED_CHAPTER.fullmatch(text)
                if match and row.size >= 14:
                    output.append(_candidate(page_number, 1, text, row, "dotted chapter"))
                    chapter_page_starts.add(page_number)
                    continue
                label = _CHAPTER_LABEL.fullmatch(text)
                if label and row.size >= 14:
                    following = [
                        other for other in rows[i + 1:]
                        if other.y > row.y
                        and other.y - row.y <= 65
                        and other.bold
                        and other.size >= 12
                        and not _EXCLUDE.match(other.text)
                    ]
                    if following:
                        title = following[0].text.strip()
                        output.append(_candidate(
                            page_number, 1,
                            f"Chapter {label.group('number')}: {title}",
                            row, "separated chapter label and bold title",
                        ))
                        chapter_page_starts.add(page_number)
                    continue

        # Unnumbered bold sections: only propose when document demonstrably uses
        # separated 'Chapter N' labels, not for numbered AGP-style documents.
        separated = any(c.evidence.startswith("separated chapter") for c in output)
        if separated:
            first_chapter_page = min(
                c.pdf_page for c in output
                if c.evidence.startswith("separated chapter")
            )
            for page_number, rows in enumerate(pages, 1):
                # Preface / chapter previews precede the first actual chapter;
                # they must not become subsection anchors for Chapter 1.
                if page_number < first_chapter_page:
                    continue
                opening = " ".join(row.text.lower() for row in rows[:5])
                if "table of contents" in opening or "list of figures" in opening or "list of tables" in opening:
                    continue
                for row in rows:
                    title = row.text.strip()
                    if (
                        not row.bold or not 11.5 <= row.size <= 15.5
                        or frequency[title.casefold()] >= 3
                        or len(title) < 8 or len(title) > 110
                        or len(title.split()) < 2
                        or _EXCLUDE.match(title)
                        or _PAGE_NUMBER.fullmatch(title)
                        or _CHAPTER_LABEL.fullmatch(title)
                        or re.match(r"^(?:Chapter\\s+\\d+\\s*:|Preface\\s*:)", title, re.I)
                        or re.match(r"^\d+(?:\.\d+)*[.\s]", title)
                        or title.endswith((".", ";", ":"))
                    ):
                        continue
                    if any(
                        c.pdf_page == page_number and title in c.heading
                        for c in output
                    ):
                        continue
                    output.append(_candidate(page_number, 2, title, row, "unnumbered bold section"))
        return sorted(output, key=lambda c: (c.pdf_page, float(re.search(r"y=([\d.]+)", c.evidence).group(1))))
