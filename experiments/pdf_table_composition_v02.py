"""Additive, review-first composition proposal for split PDF tables.

No v0.2/PDF/raw-cell mutation, DB writes, or implicit approval. The derived
matrix is only a preview; original matrices remain authoritative evidence.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from experiments.pdf_structure_v02 import canonical_sha256, validate_v02


def _as_matrix(region):
    cells = region.get("raw_cells")
    if not isinstance(cells, list) or not cells or not all(
        isinstance(row, list) and row for row in cells
    ):
        raise ValueError(f"No nonempty raw_cells for {region['region_id']}")
    if any(not all(cell is None or isinstance(cell, str) for cell in row)
           for row in cells):
        raise ValueError("Invalid raw_cells")
    width = len(cells[0])
    if any(len(row) != width for row in cells):
        raise ValueError("Ragged table matrix cannot be composed automatically")
    return cells


def propose_composition(v02, *, logical_id, source_region_ids):
    """Deterministic proposal. Region order is explicit, NEVER inferred silently.

    A repeated header is skipped in the *preview* only, and a fully blank
    row is skipped in the *preview* only. Originals remain bit-for-bit intact.
    The resulting rows each carry precise (source ID, source row) provenance.
    """
    errors = validate_v02(v02)
    if errors:
        raise ValueError("Invalid v0.2: " + "; ".join(errors[:5]))
    if not isinstance(source_region_ids, (tuple, list)) or len(source_region_ids) < 2:
        raise ValueError("At least two source table regions required")
    if len(set(source_region_ids)) != len(source_region_ids):
        raise ValueError("Duplicate source region")
    logicals = {e["logical_id"]: e for e in v02["logical_elements"]}
    logical = logicals.get(logical_id)
    if logical is None or logical["element_kind"] != "table":
        raise ValueError("Target must be a known logical table")
    regions = {r["region_id"]: r for r in v02["physical_regions"]}
    sources = []
    for rid in source_region_ids:
        r = regions.get(rid)
        if r is None or r["region_kind"] != "table":
            raise ValueError(f"Unknown/non-table region: {rid}")
        sources.append(r)
    if len({r["page_number"] for r in sources}) != 1:
        raise ValueError("Cross-page composition not supported yet")
    page = sources[0]["page_number"]
    # Ensure target logical table has a caption reference on the same page.
    caption_ids = {
        rel["to_id"] for rel in v02["relationships_v02"]
        if rel["from_id"] == logical_id and rel["relation_type"] == "has_caption"
    }
    if not any(r["region_id"] in caption_ids and r["page_number"] == page
               for r in v02["physical_regions"]):
        raise ValueError("Table must have an on-page caption relationship")
    matrices = [_as_matrix(r) for r in sources]
    header = matrices[0][0]
    if any(matrix[0] != header for matrix in matrices[1:]):
        raise ValueError("Headers differ; manual review required before composition")
    # Validate proposed geometry: left-to-right adjacent blocks.
    for left, right in zip(sources, sources[1:]):
        a, b = left["bbox_pt"], right["bbox_pt"]
        overlap_y = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        min_height = min(a[3] - a[1], b[3] - b[1])
        if not (a[2] <= b[0] and overlap_y / min_height >= 0.75):
            raise ValueError("Not adjacent horizontal blocks with aligned heights")
    rows = []
    skipped = []
    for source, cells in zip(sources, matrices):
        for index, row in enumerate(cells):
            if index == 0 and source != sources[0]:
                skipped.append({"region_id": source["region_id"], "row_index": index,
                                "reason": "repeated_header"})
                continue
            if all(value is None or not value.strip() for value in row):
                skipped.append({"region_id": source["region_id"], "row_index": index,
                                "reason": "empty_row"})
                continue
            rows.append({
                "cells": copy.deepcopy(row), "region_id": source["region_id"],
                "row_index": index,
            })
    # Record canonical content identities; derived rows never edit inputs.
    return {
        "proposal_version": "0.1",
        "proposal_id": "composition-" + canonical_sha256({
            "document": v02["source_v01"]["document"]["sha256"],
            "logical_id": logical_id, "sources": list(source_region_ids),
            "source_hashes": [canonical_sha256(r) for r in sources],
        })[:24],
        "document_sha256": v02["source_v01"]["document"]["sha256"],
        "source_v01_sha256": v02["source_v01_sha256"],
        "logical_id": logical_id,
        "logical_label": logical["label"],
        "logical_sha256": canonical_sha256(logical),
        "page_number": page,
        "composition": "horizontal_continuation",
        "reading_order": "left_to_right",
        "header_policy": "repeated_header",
        "source_region_ids": list(source_region_ids),
        "source_region_sha256": {
            r["region_id"]: canonical_sha256(r) for r in sources
        },
        "preview_rows": rows,
        "preview_excluded_rows": skipped,
        "review": {"status": "proposed"},
    }


def validate_proposal(v02, proposal):
    """Recreate using exact cited sources; reject tampered derived data."""
    if not isinstance(proposal, dict):
        raise ValueError("Expected proposal object")
    expected = propose_composition(
        v02, logical_id=proposal.get("logical_id"),
        source_region_ids=proposal.get("source_region_ids"),
    )
    if canonical_sha256(expected) != canonical_sha256(proposal):
        raise ValueError("Composition proposal is stale or altered")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-json", type=Path, required=True)
    parser.add_argument("--logical-id", required=True)
    parser.add_argument("--regions", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() == args.v02_json.resolve():
        parser.error("Output cannot overwrite source")
    data = json.loads(args.v02_json.read_text(encoding="utf-8"))
    proposal = propose_composition(
        data, logical_id=args.logical_id, source_region_ids=args.regions
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Table composition proposed (NOT approved):", args.out)
    print("Derived preview rows:", len(proposal["preview_rows"]))
    print("Source raw_cells and v0.2 untouched.")


if __name__ == "__main__":
    main()
