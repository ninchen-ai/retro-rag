"""Read-only preselection of PDF test pages from PyMuPDF tables, with optional outline context.

No DocLayout-YOLO inference; chooses review candidates, not validated associations.
No changes to PDFs, Nextcloud, structure JSON, database, or embeddings.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

import pymupdf

from experiments.pdf_table_quality_review import inspect_cells


def shortlist(outline, page_tables, *, max_pages=5, min_rows=2,
              min_cols=2, mode="all"):
    """Prioritize diverse table shapes even without table bookmarks.

    mode=all evaluates any supplied page with PyMuPDF tables; mode=outline
    restricts to pages with proposed table bookmarks (legacy behavior).
    page_tables maps 1-based page -> raw PyMuPDF table reports.
    Same-page appearance is not proof of correspondence.
    """
    if max_pages < 1 or min_rows < 1 or min_cols < 1:
        raise ValueError("Thresholds must be positive")
    if mode not in ("all", "outline"):
        raise ValueError("mode must be all or outline")
    anchors_by_page = defaultdict(list)
    for element in outline["elements"]:
        if element["element_type"] != "table":
            continue
        if element["review"]["status"] != "proposed":
            continue
        anchors_by_page[element["page_number"]].append({
            "element_id": element["element_id"],
            "title": element["title_or_text"],
            "bbox_pt": element["bbox_pt"],
        })
    candidates = []
    pages = sorted(page_tables) if mode == "all" else sorted(anchors_by_page)
    for page_number in pages:
        anchors = anchors_by_page.get(page_number, [])
        tables = page_tables.get(page_number, [])
        usable = [t for t in tables
                  if t["rows"] >= min_rows and t["columns"] >= min_cols]
        if not usable:
            continue
        shapes = sorted({(t["rows"], t["columns"]) for t in usable})
        candidates.append({
            "page_number": page_number,
            "context_status": ("HAS_TABLE_BOOKMARK" if anchors else "NO_TABLE_BOOKMARK"),
            "outline_table_anchors": anchors,
            "pymupdf_table_count": len(tables),
            "eligible_table_count": len(usable),
            "shapes": [{"rows": rows, "columns": cols} for rows, cols in shapes],
            "table_summaries": [{
                "bbox_pt": t["bbox_pt"],
                "rows": t["rows"],
                "columns": t["columns"],
                "cell_warnings": inspect_cells(
                    t["cells"], t["rows"], t["columns"]
                ),
            } for t in usable],
            "approved": False,
            "status": "CANDIDATE_ONLY_NOT_MATCHED",
        })
    # Prefer heterogeneous layouts (column variety, multi-table pages);
    # deterministic tie-breaker in document page order.
    candidates.sort(key=lambda p: (
        -len({s["columns"] for s in p["shapes"]}),
        -p["eligible_table_count"],
        -max(s["columns"] for s in p["shapes"]),
        p["page_number"],
    ))
    return {
        "approved": False,
        "total_candidate_pages": len(candidates),
        "selected_pages": candidates[:max_pages],
        "selection_basis": ("pymupdf_shapes_with_optional_outline_context"
                            if mode == "all" else "outline_table_pages_and_pymupdf_shapes"),
        "limitations": [
            "Same-page presence is not correspondence; DocLayout-YOLO is not run.",
            "Rows, columns and cell warnings are only structural observations.",
            "Text and visuals have not been manually validated.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--nextcloud-path")
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--outline-json", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--mode", choices=("all", "outline"), default="all",
                        help="all: scan every PDF page; outline: only table-bookmarked pages")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.outline_json]
    if args.pdf:
        inputs.append(args.pdf)
    if args.out.resolve() in {p.resolve() for p in inputs}:
        parser.error("Output must not overwrite an input")

    outline = json.loads(args.outline_json.read_text(encoding="utf-8"))
    if args.pdf:
        raw = args.pdf.read_bytes()
    else:
        from scripts.import_pdf import get_webdav
        password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass(
            "Nextcloud-App-Passwort: "
        )
        raw, _, _ = get_webdav(
            args.nextcloud_url, args.nextcloud_user, password,
            args.nextcloud_path
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != outline["document"]["sha256"]:
        raise ValueError("Source SHA-256 does not match outline JSON")

    outline_pages = sorted({
        e["page_number"] for e in outline["elements"]
        if e["element_type"] == "table"
        and e["review"]["status"] == "proposed"
    })
    page_tables = {}
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        if pdf.page_count != len(outline["pages"]):
            raise ValueError("Page count mismatch")
        target_pages = (range(1, pdf.page_count + 1)
                        if args.mode == "all" else outline_pages)
        scanned = 0
        for page_number in target_pages:
            scanned += 1
            if not 1 <= page_number <= pdf.page_count:
                raise ValueError(f"Bad outline page {page_number}")
            page = pdf[page_number-1]
            if page.rotation:
                continue
            reports = []
            for table in page.find_tables().tables:
                reports.append({
                    "bbox_pt": [round(float(x), 3) for x in table.bbox],
                    "rows": table.row_count,
                    "columns": table.col_count,
                    "cells": table.extract(),
                })
            page_tables[page_number] = reports

    report = shortlist(outline, page_tables, max_pages=args.max_pages,
                       mode=args.mode)
    report["source_sha256"] = digest
    report["scanned_outline_table_pages"] = len(outline_pages)
    report["scanned_pages"] = scanned
    report["mode"] = args.mode
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print("Seiten mit vorgeschlagenen Tabellen-Lesezeichen:", len(outline_pages))
    print("Tatsächlich geprüfte PDF-Seiten:", scanned)
    print("Kandidatenseiten:", report["total_candidate_pages"])
    for item in report["selected_pages"]:
        shapes = ", ".join(f"{s['rows']}x{s['columns']}" for s in item["shapes"])
        print(f"  PDF-Seite {item['page_number']}: {shapes} | "
              f"{item['eligible_table_count']} PyMuPDF-Tabellen | "
              f"{len(item['outline_table_anchors'])} Tabellen-Lesezeichen "
              f"| {item['context_status']}")
    print("Nicht freigegebener Kandidatenbericht:", args.out)


if __name__ == "__main__":
    main()
