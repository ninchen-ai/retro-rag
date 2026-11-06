"""Read-only quality review: outline captions, detector tables and PyMuPDF cells.

This is a proposal/report, not a semantic verification or an ingestion step.
No source, database, Nextcloud, or structure JSON writes.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path

import pymupdf

from experiments.pdf_table_region_review import (
    associate_table_anchors, layout_regions_in_pdf,
)


def bbox_iou(first, second):
    """Area intersection / union for axis-aligned PDF point rectangles."""
    if len(first) != 4 or len(second) != 4:
        raise ValueError("Bounding boxes must contain four numbers")
    a = [float(x) for x in first]
    b = [float(x) for x in second]
    if not all(math.isfinite(x) for x in a + b):
        raise ValueError("Nonfinite bounding box")
    if a[0] >= a[2] or a[1] >= a[3] or b[0] >= b[2] or b[1] >= b[3]:
        raise ValueError("Degenerate bounding box")
    intersection = (
        max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    )
    union = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - intersection)
    return intersection / union


def inspect_cells(matrix, expected_rows, expected_cols):
    """Structural warnings only, not proof of exact PDF/OCR transcription."""
    warnings = []
    if expected_rows <= 0 or expected_cols <= 0:
        warnings.append("EMPTY_TABLE_SHAPE")
    if len(matrix) != expected_rows:
        warnings.append("ROW_COUNT_MISMATCH")
    for row_number, row in enumerate(matrix, 1):
        if len(row) != expected_cols:
            warnings.append(f"COL_COUNT_MISMATCH_ROW_{row_number}")
        for column_number, cell in enumerate(row, 1):
            if cell is None or not str(cell).strip():
                warnings.append(f"EMPTY_CELL_R{row_number}_C{column_number}")
    return warnings


def evaluate_tables(outline, regions, pymupdf_tables, *, page_number,
                    min_iou=0.75):
    """Collect independent geometry and extracted-cell observations."""
    if not 0 < min_iou <= 1:
        raise ValueError("min_iou must be in (0, 1]")
    proposal = associate_table_anchors(outline, regions, page_number=page_number)
    detections = proposal["table_regions"]
    extracted = []
    for index, table in enumerate(pymupdf_tables):
        box = list(table["bbox_pt"])
        cells = table["cells"]
        extracted.append({
            "index": index,
            "bbox_pt": box,
            "rows": table["rows"],
            "columns": table["columns"],
            "cells": cells,
            "cell_warnings": inspect_cells(cells, table["rows"], table["columns"]),
        })
    candidates = []
    for di, detection in enumerate(detections):
        options = []
        for pi, table in enumerate(extracted):
            overlap = bbox_iou(detection["bbox_pdf_points"], table["bbox_pt"])
            if overlap >= min_iou:
                options.append({"pymupdf_table_index": pi, "iou": round(overlap, 4)})
        candidates.append({
            "detector_region_index": di,
            "matches": sorted(options, key=lambda x: (-x["iou"], x["pymupdf_table_index"])),
            "status": "ONE_CANDIDATE" if len(options) == 1 else (
                "NO_CANDIDATE" if not options else "MULTIPLE_CANDIDATES"
            ),
        })
    # Do not select a PyMuPDF table claimed by two detector regions.
    claims = {}
    for item in candidates:
        if item["status"] == "ONE_CANDIDATE":
            table_index = item["matches"][0]["pymupdf_table_index"]
            claims.setdefault(table_index, []).append(item)
    for entries in claims.values():
        if len(entries) > 1:
            for item in entries:
                item["status"] = "SHARED_EXTRACTED_TABLE_CONFLICT"
    # Any caption links only through a unique detector -> PyMuPDF match.
    linked = []
    by_detector = {c["detector_region_index"]: c for c in candidates}
    for item in proposal["anchor_matches"]:
        link = {
            "outline_element_id": item["element_id"],
            "outline_title": item["title"],
            "caption_match_status": item["status"],
            "pymupdf_match_status": "UNRESOLVED",
            "pymupdf_table_index": None,
            "approved": False,
        }
        if item["status"] == "ONE_CANDIDATE":
            rid = item["candidate_regions"][0]["region_index"]
            candidate = by_detector[rid]
            link["pymupdf_match_status"] = candidate["status"]
            if candidate["status"] == "ONE_CANDIDATE":
                link["pymupdf_table_index"] = candidate["matches"][0]["pymupdf_table_index"]
        linked.append(link)
    return {
        "page_number": page_number,
        "approved": False,
        "min_iou": min_iou,
        "caption_to_detector": proposal["anchor_matches"],
        "detector_table_regions": detections,
        "pymupdf_tables": extracted,
        "detector_to_pymupdf": candidates,
        "caption_to_extracted_table": linked,
        "quality_limitations": [
            "IoU is geometric agreement, not a calibrated correctness probability.",
            "Rows/cells are unreviewed PyMuPDF extraction, not verified against visible PDF.",
            "Empty cell may be legitimate; nonempty cell may be truncated or misassigned.",
            "No automatic approval, no text replacement and no database writes.",
        ],
    }


def extract_pymupdf_tables(page):
    """Extract the entire tabular matrix while PyMuPDF owns the page."""
    return [
        {
            "bbox_pt": [round(float(x), 3) for x in table.bbox],
            "rows": table.row_count,
            "columns": table.col_count,
            "cells": table.extract(),
        }
        for table in page.find_tables().tables
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--nextcloud-path")
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--outline-json", required=True, type=Path)
    parser.add_argument("--layout-json", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    source_paths = [args.outline_json, args.layout_json, args.image]
    if args.pdf is not None:
        source_paths.append(args.pdf)
    if args.out.resolve() in [p.resolve() for p in source_paths]:
        parser.error("Output must not overwrite an input")
    outline = json.loads(args.outline_json.read_text(encoding="utf-8"))
    layout = json.loads(args.layout_json.read_text(encoding="utf-8"))
    if not 1 <= args.page <= len(outline["pages"]):
        parser.error("PDF page outside outline structure")
    if layout.get("source_image") != args.image.name:
        parser.error("Layout source_image differs from supplied PNG")
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
        raise ValueError("PDF SHA-256 mismatch against outline JSON")

    pix = pymupdf.Pixmap(str(args.image))
    image_width, image_height = pix.width, pix.height
    del pix
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        if pdf.page_count != len(outline["pages"]):
            raise ValueError("PDF page count mismatch")
        page = pdf[args.page - 1]
        page_meta = outline["pages"][args.page - 1]
        if page.rotation or page_meta["rotation"]:
            raise ValueError("Rotated PDF page not supported")
        if abs(page.rect.width - page_meta["width_pt"]) > 0.1 or abs(
            page.rect.height - page_meta["height_pt"]
        ) > 0.1:
            raise ValueError("PDF geometry differs from outline JSON")
        regions = layout_regions_in_pdf(
            layout, image_width, image_height, page_meta
        )
        tables = extract_pymupdf_tables(page)
    report = evaluate_tables(outline, regions, tables, page_number=args.page)
    report.update({
        "document_sha256": digest,
        "source_image": args.image.name,
        "image_size_pixels": [image_width, image_height],
        "detector_model": layout.get("model"),
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"PDF-Seite {args.page}: detector={len(report['detector_table_regions'])}, "
          f"pymupdf={len(report['pymupdf_tables'])}, "
          f"outline={len(report['caption_to_detector'])}")
    for link in report["caption_to_extracted_table"]:
        print(link["outline_title"], "|", link["caption_match_status"],
              "| PyMuPDF:", link["pymupdf_match_status"],
              "| index:", link["pymupdf_table_index"])
    for table in report["pymupdf_tables"]:
        print(f"PyMuPDF-Tabelle {table['index']}: "
              f"{table['rows']}x{table['columns']} "
              f"| Zellwarnungen: {len(table['cell_warnings'])}")
    print(f"Nicht freigegebener Review-Bericht: {args.out}")


if __name__ == "__main__":
    main()
