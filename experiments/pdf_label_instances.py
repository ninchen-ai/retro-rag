"""Locate confirmed label text as physical instances without editing PDF text.

PyMuPDF can return multiple almost-overlapping text boxes for text drawn
twice. Overlaps are candidate duplicates only when the SAME search phrase
has strongly overlapping boxes. Separate occurrences remain distinct.

Reference-label extraction is optional, read-only, and not import approval.
"""
from __future__ import annotations

from collections import Counter

import pymupdf

from experiments.pdf_layout_joint_review import figure_proximity


def intersection_over_union(first, second):
    ax0, ay0, ax1, ay1 = map(float, first)
    bx0, by0, bx1, by1 = map(float, second)
    width = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    height = max(0.0, min(ay1, by1) - max(ay0, by0))
    intersection = width * height
    a_area = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    b_area = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = a_area + b_area - intersection
    return intersection / union if union > 0 else 0.0


def distinct_instances(rectangles, overlap_threshold=0.5):
    """Return (unique boxes, suppressed count), stable in PDF reading order.

    Uses the originally detected bounding rectangle for each retained
    instance, preserving the source geometry. No text deduplication occurs.
    """
    if not (0 < overlap_threshold < 1):
        raise ValueError("overlap_threshold must be between 0 and 1")
    unique = []
    suppressed = 0
    for box in sorted(rectangles, key=lambda r: (r.y0, r.x0)):
        if any(intersection_over_union(box, kept) >= overlap_threshold
               for kept in unique):
            suppressed += 1
            continue
        unique.append(box)
    return unique, suppressed


def extract_reference_label_instances(page, reference_page, regions):
    """Locate only reviewer-confirmed labels; keep all locations provisional."""
    expected = Counter()
    for row in reference_page["candidates"]:
        if row.get("reviewed") is True:
            expected[row["text"]] += 1

    output = []
    for label, count in expected.items():
        raw_hits = page.search_for(label)
        boxes, suppressed = distinct_instances(raw_hits)
        # Do not guess if the number of located physical instances does not
        # match the manually confirmed number. Report the disagreement.
        complete = len(boxes) == count
        for index, box in enumerate(boxes, 1):
            nearby = figure_proximity(tuple(box), regions)
            output.append({
                "heading": label,
                "occurrence": index,
                "location_status": "LOCATED" if complete else "COUNT_MISMATCH",
                "bbox_pdf_points": [round(float(x), 1) for x in box],
                "search_hits": len(raw_hits),
                "duplicate_boxes_suppressed": suppressed,
                "expected_instances": count,
                "located_instances": len(boxes),
                "review_reason": (
                    "POSSIBLY_FIGURE_ASSOCIATED"
                    if nearby else "NO_NEARBY_FIGURE_DETECTED"
                ),
                "nearby_regions": nearby,
                "status": "REVIEW_REQUIRED",
            })
        if not boxes:
            output.append({
                "heading": label,
                "location_status": "UNMATCHED",
                "expected_instances": count,
                "located_instances": 0,
                "status": "REVIEW_REQUIRED",
            })
    return output
