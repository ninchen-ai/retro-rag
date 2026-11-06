"""Read-only audit manifest combining v0.2 PDF text and reviewed table composition.

This is NOT a pgvector import format or an automatic approval. It reuses
the existing immutable text chunk preview, validates both independent
decision ledgers, and surfaces duplicate-indexing risks without removing
a single source character or interpreting unreviewed relationships.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from experiments.pdf_review_decisions_v02 import inspect_ledger
from experiments.pdf_structural_chunk_preview_v02 import preview as preview_text
from experiments.pdf_table_composition_v02 import validate_proposal
from experiments.pdf_table_composition_review_v02 import current_decision


def build_manifest(
    v02, *, review_ledger_dir, composition_proposal,
    composition_ledger_dir, max_chars=2500,
    selected_heading_ids=(),
):
    """Every decision is read from its own validated ledger.

    Text on a page with a proposed/confirmed table remains fully intact.
    The page's text chunks and the separate table chunk are both marked
    NOT_INDEXABLE_PENDING_DEDUP until a verified content-span exclusion
    plan exists. No text-to-table matching is assumed from coordinates.
    """
    text = preview_text(
        v02, selected_heading_ids=selected_heading_ids, max_chars=max_chars,
    )
    reviews = inspect_ledger(v02, review_ledger_dir)
    table = validate_proposal(v02, composition_proposal)
    decision = current_decision(v02, table, composition_ledger_dir)
    decision_status = decision["status"] if decision else "proposed"
    target = table["logical_id"]
    logical = next(e for e in v02["logical_elements"] if e["logical_id"] == target)
    logical_decision = reviews.get(target)
    logical_status = logical_decision["status"] if logical_decision else "proposed"

    page = table["page_number"]
    page_numbers = {p["page_number"] for p in v02["source_v01"]["pages"]}
    if page not in page_numbers:
        raise ValueError("Composition page is not in original PDF")
    source_ids = set(table["source_region_ids"])
    regions = {
        r["region_id"]: r for r in v02["physical_regions"]
    }
    for rid in source_ids:
        if rid not in regions:
            raise ValueError(f"Composition source region missing: {rid}")
    source_statuses = {
        rid: reviews[rid]["status"] if rid in reviews else "proposed"
        for rid in table["source_region_ids"]
    }
    # Every relationship is still separately proposed until explicitly reviewed.
    relations = [
        {
            "relation_id": rel["relation_id"],
            "relation_type": rel["relation_type"],
            "from_id": rel["from_id"],
            "to_id": rel["to_id"],
            "status": reviews[rel["relation_id"]]["status"]
            if rel["relation_id"] in reviews else "proposed",
        }
        for rel in v02["relationships_v02"]
        if rel["from_id"] == target or rel["to_id"] == target
    ]
    entries = []
    for chunk in text["chunks"]:
        item = copy.deepcopy(chunk)
        item["unit_type"] = "source_page_text"
        item["source_text_integrity"] = "verbatim"
        item["index_disposition"] = (
            "blocked_possible_table_duplication"
            if item["page_number"] == page else "not_approved"
        )
        entries.append(item)

    header = table["preview_rows"][0]["cells"]
    body = [r["cells"] for r in table["preview_rows"][1:]]
    # Keep a structured table rather than formatting and losing provenance.
    table_unit = {
        "unit_id": "table-" + table["proposal_id"],
        "unit_type": "logical_table_preview",
        "logical_id": target,
        "label": logical["label"],
        "page_number": page,
        "composition_status": decision_status,
        "composition_decision_id": decision["decision_id"] if decision else None,
        "logical_element_status": logical_status,
        "source_region_statuses": source_statuses,
        "source_region_ids": table["source_region_ids"],
        "header_cells": copy.deepcopy(header),
        "data_rows": copy.deepcopy(body),
        "rows_with_provenance": copy.deepcopy(table["preview_rows"]),
        "excluded_preview_rows": copy.deepcopy(table["preview_excluded_rows"]),
        "related_review_states": relations,
        "index_disposition": "blocked_possible_table_duplication",
    }
    entries.append(table_unit)
    blockers = [
        {
            "code": "TABLE_TEXT_OVERLAP_UNRESOLVED",
            "page_number": page,
            "description": (
                "Full original page text retained; some text may repeat in "
                "composed table. A reviewed span/character-range exclusion "
                "is required before indexing both."
            ),
        },
    ]
    if decision_status != "confirmed":
        blockers.append({
            "code": "COMPOSITION_NOT_CONFIRMED",
            "status": decision_status,
        })
    if logical_status != "confirmed":
        blockers.append({
            "code": "LOGICAL_TABLE_NOT_CONFIRMED",
            "status": logical_status,
        })
    if any(r["status"] != "confirmed" for r in relations):
        blockers.append({
            "code": "UNREVIEWED_TABLE_RELATIONSHIPS",
            "pending_or_rejected": [
                r["relation_id"] for r in relations
                if r["status"] != "confirmed"
            ],
        })
    # Outline headings in the immutable v0.1 snapshot have proposal states.
    # Selecting them for a preview does not turn them into approved headings.
    if selected_heading_ids:
        blockers.append({
            "code": "HEADING_SELECTION_IS_NOT_APPROVAL",
            "ids": list(selected_heading_ids),
        })
    return {
        "manifest_version": "0.1",
        "document_sha256": text["document_sha256"],
        "source_v01_sha256": text["source_v01_sha256"],
        "text_chunk_count": len(text["chunks"]),
        "table_unit_count": 1,
        "table_page": page,
        "table_composition_decision_status": decision_status,
        "text_reconstruction_verified": text["quality"][
            "lossless_page_text_reconstruction"
        ],
        "import_approved": False,
        "db_writes": False,
        "embedding_calls": False,
        "index_disposition": "blocked_review_and_dedup_required",
        "blockers": blockers,
        "entries": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-json", type=Path, required=True)
    parser.add_argument("--review-ledger-dir", type=Path, required=True)
    parser.add_argument("--composition-json", type=Path, required=True)
    parser.add_argument("--composition-ledger-dir", type=Path, required=True)
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--heading-id", action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    forbidden = {
        args.v02_json.resolve(), args.composition_json.resolve(),
    }
    if args.out.resolve() in forbidden:
        parser.error("Refusing to overwrite source v0.2 or composition JSON")
    v02 = json.loads(args.v02_json.read_text(encoding="utf-8"))
    proposal = json.loads(args.composition_json.read_text(encoding="utf-8"))
    output = build_manifest(
        v02, review_ledger_dir=args.review_ledger_dir,
        composition_proposal=proposal,
        composition_ledger_dir=args.composition_ledger_dir,
        selected_heading_ids=args.heading_id, max_chars=args.max_chars,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Text chunks:", output["text_chunk_count"])
    print("Table composition:", output["table_composition_decision_status"])
    print("Table units:", output["table_unit_count"])
    print("Blockers:", ", ".join(b["code"] for b in output["blockers"]))
    print("READ-ONLY manifest (NOT APPROVED FOR INDEXING):", args.out)


if __name__ == "__main__":
    main()
