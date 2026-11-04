"""Read-only JSON quality report for an unapproved PDF chunk preview.

An aligned heading is not a validated heading. Reports guide manual review and
must never be treated as an import approval or written to the production DB.
"""
from __future__ import annotations

from collections import Counter
import json

from scripts.pdf_heading_alignment import align_document_headings
from scripts.pdf_heading_review import build_heading_review
from scripts.pdf_chunk_preview import preview_section_chunks

_FIGURE_HINTS = ("system front", "mother board", "added fan", "fan direction",
                 "internal air flow", "add-in card")


def build_quality_report(raw: bytes, filename: str) -> dict:
    review = build_heading_review(raw)
    aligned = align_document_headings(raw, review.headings)
    preview = preview_section_chunks(raw)
    statuses = Counter(item.status for item in aligned)
    numbers = {h.section_number for h in review.headings if h.section_number}
    missing: set[str] = set()
    if review.style in ("numbered", "dotted"):
        for number in numbers:
            parts = number.split(".")
            for n in range(1, len(parts)):
                parent = ".".join(parts[:n])
                if parent not in numbers:
                    missing.add(parent)

    issues: list[dict] = []
    # Alignments may be returned in page order rather than heading-report
    # order; always match through explicit identity.
    lookup = {(a.pdf_page, a.heading, a.source): a for a in aligned}
    for heading in review.headings:
        aligned_item = lookup.get((heading.pdf_page, heading.heading, heading.source))
        state = aligned_item.status if aligned_item else "MISSING_ALIGNMENT"
        reason = None
        if state in ("UNMATCHED", "AMBIGUOUS", "MISSING_ALIGNMENT"):
            reason = "TEXT_ANCHOR_UNRESOLVED"
        elif state in ("MATCHED_COMPACT", "MATCHED_CHAPTER_ANCHOR"):
            reason = "NON_EXACT_TEXT_ANCHOR"
        elif (review.style == "separated"
              and any(hint in heading.heading.casefold() for hint in _FIGURE_HINTS)):
            reason = "POSSIBLE_FIGURE_LABEL"
        if reason:
            issues.append({
                "pdf_page": heading.pdf_page,
                "heading": heading.heading,
                "reason": reason,
                "alignment": state,
                "review_required": True,
            })
    return {
        "filename": filename,
        "style": review.style,
        "approved": False,
        "lossless": preview.lossless,
        "chunk_count": len(preview.chunks),
        "max_chunk_chars": max((len(c.content) for c in preview.chunks), default=0),
        "heading_candidates": len(review.headings),
        "aligned_anchors_used": preview.matched_headings,
        "alignment_statuses": dict(sorted(statuses.items())),
        "missing_parent_sections": sorted(
            missing, key=lambda s: tuple(map(int, s.split(".")))
        ),
        "skipped_headings": list(preview.skipped_headings),
        "warnings": list(review.warnings),
        "issues": issues,
    }


def format_quality_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
