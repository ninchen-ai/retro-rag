"""Evaluate proposed PDF span groups against a provisional/confirmed reference.

This checks whether a detector proposed a merge, NOT whether merged text is
linguistically correct. Only reviewer-confirmed annotations are scored.
Provisional annotations are displayed but excluded from verified metrics.

No external dependencies, no writes, no change to the PDF pipeline.

Example:
 python -m experiments.evaluate_span_groups \
   --report /tmp/retro-doclayout/page40/group_review.json \
   --report /tmp/retro-doclayout/page41/group_review.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REFERENCE = Path(__file__).parent / "fixtures" / "agpdg11a_span_group_reference_v1.json"
DECISIONS = {"merge", "keep_separate", "unclear"}


def _key(page, text, source_texts):
    return (page, text, tuple(source_texts))


def evaluate(reference: dict, reports: list[dict]) -> dict:
    """Reconcile exact source-span sequences, keeping unreviewed separate."""
    indexed = {}
    for report in reports:
        page = report["pdf_page"]
        if page in indexed:
            raise ValueError(f"Duplicate report for page {page}")
        indexed[page] = report

    rows = []
    seen = set()
    reviewed_total = 0
    reviewed_scored = 0
    reviewed_matches = 0
    unreviewed = 0

    for item in reference["cases"]:
        decision = item["expected_decision"]
        if decision not in DECISIONS:
            raise ValueError(f"Unexpected decision: {decision}")
        key = _key(item["pdf_page"], item["proposed_text"], item["source_texts"])
        if key in seen:
            raise ValueError(f"Duplicate reference case: {key}")
        seen.add(key)

        page = indexed.get(item["pdf_page"])
        found = []
        if page is not None:
            for proposal in page.get("span_group_proposals", []):
                proposal_key = _key(
                    item["pdf_page"],
                    proposal["proposed_text"],
                    [s["text"] for s in proposal["source_spans"]],
                )
                if proposal_key == key:
                    found.append(proposal)
        status = "PROPOSED" if len(found) == 1 else (
            "NOT_PROPOSED" if not found else "AMBIGUOUS"
        )
        if item.get("reviewed") is True:
            reviewed_total += 1
            if status != "AMBIGUOUS" and decision != "unclear":
                reviewed_scored += 1
                predicted_merge = status == "PROPOSED"
                if predicted_merge == (decision == "merge"):
                    reviewed_matches += 1
        else:
            unreviewed += 1
        rows.append({
            "pdf_page": item["pdf_page"],
            "proposed_text": item["proposed_text"],
            "source_texts": item["source_texts"],
            "expected_decision": decision,
            "reviewed": item.get("reviewed") is True,
            "detection": status,
        })

    return {
        "metric": "group proposal agreement, not semantic correctness",
        "approved": False,
        "reference_version": reference["schema_version"],
        "reviewed_cases": reviewed_total,
        "reviewed_scored": reviewed_scored,
        "reviewed_matches": reviewed_matches,
        "reviewed_mismatches": reviewed_scored - reviewed_matches,
        "provisional_cases_excluded": unreviewed,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--report", type=Path, action="append", required=True)
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    print(json.dumps(evaluate(reference, reports), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
