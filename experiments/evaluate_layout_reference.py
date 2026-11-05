"""Evaluate geometric review flags against explicitly reviewed AGP labels only.

This measures a *screening hint* (POSSIBLY_FIGURE_ASSOCIATED), not whether
the chunker has correctly classified a document heading. Unreviewed
annotations are excluded. No DB, PDF or Nextcloud writes.

Example:
 python -m experiments.evaluate_layout_reference \
   --report /tmp/retro-doclayout/joint_review.json \
   --report /tmp/retro-doclayout/page40/joint_review.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_REFERENCE = Path(__file__).parent / "fixtures" / "agpdg11a_heading_reference_v1.json"
FIGURE_KINDS = {"figure_label", "figure_caption"}
NEGATIVE_KINDS = {"section_heading", "subheading"}


def evaluate(reference: dict, reports: list[dict]) -> dict:
    """Score only confirmed annotations with a unique corresponding result."""
    indexed = {}
    for report in reports:
        page = report["pdf_page"]
        if page in indexed:
            raise ValueError(f"Duplicate detector report for page {page}")
        indexed[page] = report

    rows = []
    unreviewed = 0
    missing = 0
    for page in reference["pages"]:
        page_no = page["pdf_page"]
        report = indexed.get(page_no)
        by_text = {}
        if report:
            for item in report["heading_candidates"]:
                by_text.setdefault(item["heading"], []).append(item)
        for item in page["candidates"]:
            if not item["reviewed"]:
                unreviewed += 1
                continue
            expected = item["expected_kind"]
            if expected not in FIGURE_KINDS | NEGATIVE_KINDS:
                raise ValueError(f"Unknown reference category {expected}")
            matches = by_text.get(item["text"], [])
            occurrence = item.get("occurrence")
            match = None
            if occurrence is None:
                # A single semantic label must not silently consume one of
                # several distinct physical text occurrences.
                if len(matches) == 1:
                    match = matches[0]
            elif isinstance(occurrence, int) and not isinstance(occurrence, bool) and occurrence > 0:
                # Physical occurrences are indexed in reading order. Reject
                # duplicate or missing positions: an identical detector box
                # must not be used to score two reference instances.
                located = [
                    m for m in matches
                    if m.get("location_status") == "LOCATED"
                    and isinstance(m.get("bbox_pdf_points"), list)
                    and len(m["bbox_pdf_points"]) == 4
                ]
                if len(located) == len(matches) and len(located) >= occurrence:
                    boxes = [tuple(m["bbox_pdf_points"]) for m in located]
                    if len(set(boxes)) == len(boxes):
                        located.sort(key=lambda m: (m["bbox_pdf_points"][1], m["bbox_pdf_points"][0]))
                        match = located[occurrence - 1]
            if match is None or match.get("location_status") != "LOCATED":
                missing += 1
                rows.append({
                    "pdf_page": page_no,
                    "text": item["text"],
                    **({"occurrence": occurrence} if occurrence is not None else {}),
                    "expected_kind": expected,
                    "result": "MISSING_OR_AMBIGUOUS",
                })
                continue
            detected = match.get("review_reason") == "POSSIBLY_FIGURE_ASSOCIATED"
            target = expected in FIGURE_KINDS
            rows.append({
                "pdf_page": page_no,
                "text": item["text"],
                **({"occurrence": occurrence} if occurrence is not None else {}),
                "expected_kind": expected,
                "figure_proximity_flag": detected,
                "expected_figure_association": target,
                "result": "MATCH" if detected == target else "MISMATCH",
            })
    scored = [row for row in rows if row["result"] in ("MATCH", "MISMATCH")]
    matched = sum(row["result"] == "MATCH" for row in scored)
    return {
        "metric": "geometric screening flag, not semantic heading accuracy",
        "reference_version": reference["schema_version"],
        "approved": False,
        "reviewed_annotations_scored": len(scored),
        "matches": matched,
        "mismatches": len(scored) - matched,
        "missing_or_ambiguous": missing,
        "unreviewed_excluded": unreviewed,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--report", type=Path, action="append", required=True)
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    print(json.dumps(evaluate(reference, reports), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
