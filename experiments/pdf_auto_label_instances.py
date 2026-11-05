"""Reference-independent PDF text instances near detected figure regions.

Use PyMuPDF *span* coordinates as the primary source, not a list of known
labels. A repeated drawn text span may be retained once for geometry when
its normalized text and bounding rectangle strongly overlap; original PDF
text and chunk output are NEVER modified.

This is only a read-only *proposal*, not a confirmed figure label.
"""
from __future__ import annotations

from collections import defaultdict
import re

from experiments.pdf_label_instances import intersection_over_union
from experiments.pdf_layout_joint_review import figure_proximity

_WHITESPACE = re.compile(r"\s+")


def normalize(text):
    return _WHITESPACE.sub(" ", text).strip().casefold()


def collect_span_instances(page, regions, *, overlap_threshold=0.5):
    """Extract geometric proposals from source PDF spans without a lexicon.

    Only report spans with an actual spatial relation to a detected figure.
    Do not classify headings, modify text, or remove source occurrences.
    """
    if not 0 < overlap_threshold < 1:
        raise ValueError("overlap_threshold must be between 0 and 1")
    groups = defaultdict(list)
    for block in page.get_text("dict")["blocks"]:
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                rect = [float(x) for x in span["bbox"]]
                nearby = figure_proximity(rect, regions, threshold_pt=0)
                # Labels embedded in drawings: only actual rectangle overlap.
                overlapping = [
                    item for item in nearby
                    if item["relation"] == "OVERLAPS_REGION"
                    and item["class_name"] == "figure"
                ]
                if not overlapping:
                    continue
                groups[normalize(text)].append({
                    "text": text,
                    "bbox_pdf_points": [round(x, 1) for x in rect],
                    "font": span.get("font", ""),
                    "size_pt": round(float(span.get("size", 0)), 1),
                    "nearby_regions": overlapping,
                })

    instances = []
    for key, hits in groups.items():
        hits.sort(key=lambda h: (h["bbox_pdf_points"][1], h["bbox_pdf_points"][0]))
        distinct = []
        for hit in hits:
            duplicate = next((
                prior for prior in distinct
                if intersection_over_union(
                    prior["bbox_pdf_points"], hit["bbox_pdf_points"]
                ) >= overlap_threshold
            ), None)
            if duplicate is None:
                distinct.append({**hit, "duplicate_draws": 0})
            else:
                duplicate["duplicate_draws"] += 1
        for occurrence, hit in enumerate(distinct, 1):
            instances.append({
                **hit,
                "occurrence": occurrence,
                "status": "REVIEW_REQUIRED",
                "source": "PDF_SPAN_FIGURE_OVERLAP",
                "review_reason": "POSSIBLY_FIGURE_ASSOCIATED",
                "approved": False,
            })
    return sorted(instances, key=lambda d: (
        d["bbox_pdf_points"][1], d["bbox_pdf_points"][0], d["text"]
    ))
