"""Read-only, fail-closed merge of disjoint-page v0.2 PDF review reports.

Each input is a complete v0.2 document containing the SAME v0.1
snapshot and observations from exactly one PDF page. Input reports,
source cells and review decisions are never rewritten, and nothing
is approved or sent to Nextcloud/PostgreSQL.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from experiments.pdf_structure_v02 import canonical_sha256, validate_v02

_COLLECTIONS = (
    ("physical_regions", "region_id"),
    ("logical_elements", "logical_id"),
    ("relationships_v02", "relation_id"),
    ("review_decisions", "decision_id"),
    ("processing_runs", "run_id"),
)


def _page_of_report(report):
    """Require explicit page provenance even for reports without regions."""
    pages = set()
    runs = report["processing_runs"]
    if not runs:
        raise ValueError("Input has no page-scoped processing runs")
    for run in runs:
        page = run["parameters"].get("page")
        if type(page) is not int or page < 1:
            raise ValueError(f"Missing/invalid page provenance in run {run['run_id']}")
        pages.add(page)
    if len(pages) != 1:
        raise ValueError("One input must contain observations from exactly one page")
    page = next(iter(pages))
    if page > len(report["source_v01"]["pages"]):
        raise ValueError(f"Page {page} does not exist in source snapshot")
    if any(region["page_number"] != page
           for region in report["physical_regions"]):
        raise ValueError("Region page differs from processing-run page")
    return page


def merge_v02(reports):
    """Return a deep-copied union, rejecting duplicates and source differences.

    Merge is intentionally not idempotent: repeated input is an error, not an
    invitation to silently override or deduplicate observations.
    """
    if not reports:
        raise ValueError("Provide at least one v0.2 report")
    for index, report in enumerate(reports):
        problems = validate_v02(report)
        if problems:
            raise ValueError(
                f"Input {index + 1} invalid: " + "; ".join(problems[:5])
            )

    first = reports[0]
    source_hash = first["source_v01_sha256"]
    source_identity = canonical_sha256(first["source_v01"])
    doc_sha = first["source_v01"]["document"]["sha256"]
    pages_seen = set()
    for index, report in enumerate(reports, 1):
        if (report["source_v01_sha256"] != source_hash
                or canonical_sha256(report["source_v01"]) != source_identity
                or report["source_v01"]["document"]["sha256"] != doc_sha):
            raise ValueError(
                f"Input {index}: different v0.1 source snapshot or PDF version"
            )
        page = _page_of_report(report)
        if page in pages_seen:
            raise ValueError(f"Duplicate page {page}; merge refuses to overwrite")
        pages_seen.add(page)

    # Canonical order independent of CLI input ordering, including decision
    # and run order; IDs from their original reports are NOT rewritten.
    ordered = sorted(reports, key=_page_of_report)
    result = copy.deepcopy(first)
    for collection, _ in _COLLECTIONS:
        result[collection] = []
    result["quality_v02"] = copy.deepcopy(first["quality_v02"])
    result["quality_v02"]["notes"] = [
        "Read-only merge of disjoint-page v0.2 review observations.",
        "No semantic approval, logical table reconstruction or RAG ingestion.",
    ]
    ids = {
        element["element_id"] for element in result["source_v01"]["elements"]
    }
    for report in ordered:
        for collection, id_key in _COLLECTIONS:
            for item in report[collection]:
                ident = item[id_key]
                if ident in ids:
                    raise ValueError(f"Duplicate ID across merged inputs: {ident}")
                ids.add(ident)
                result[collection].append(copy.deepcopy(item))

    problems = validate_v02(result)
    if problems:
        raise ValueError("Merged v0.2 invalid: " + "; ".join(problems[:10]))
    if result["source_v01_sha256"] != source_hash:
        raise ValueError("Original source fingerprint changed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True, type=Path,
                        help="One independently assembled v0.2 JSON per PDF page")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    destinations = [p.resolve() for p in args.inputs]
    if args.out.resolve() in destinations:
        parser.error("Output must not overwrite any input")
    if len(set(destinations)) != len(destinations):
        parser.error("Same input path specified more than once")
    reports = [json.loads(path.read_text(encoding="utf-8"))
               for path in args.inputs]
    merged = merge_v02(reports)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("v0.2 merge valid: input pages", len(reports))
    print("physical_regions:", len(merged["physical_regions"]),
          "| logical_elements:", len(merged["logical_elements"]),
          "| relationships:", len(merged["relationships_v02"]))
    print("Original v0.1 SHA-256:", merged["source_v01_sha256"])
    print("Unapproved read-only merge:", args.out)


if __name__ == "__main__":
    main()
