"""Review-only geometric conflicts across DocLayout-YOLO and PyMuPDF reports.

Consumes an existing layout_report.json and table-quality-review JSON.
No PDF reads, inference, text changes, auto-merges, or DB/Nextcloud writes.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from experiments.pdf_table_quality_review import bbox_iou


def _fraction_of_smaller(a, b):
    x = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    y = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = min((a[2]-a[0])*(a[3]-a[1]),
               (b[2]-b[0])*(b[3]-b[1]))
    return x*y/area if area > 0 else 0


def _valid_box(box):
    return (
        isinstance(box, (list, tuple)) and len(box) == 4
        and all(isinstance(v, (float, int)) and math.isfinite(v) for v in box)
        and box[0] < box[2] and box[1] < box[3]
    )


def _near_side_by_side(a, b, *, max_gap_pt=12, min_v_overlap=0.75):
    """Conservative parallel blocks: neither overlaps nor contains the other."""
    if bbox_iou(a, b) > 0:
        return None
    vertical = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    v_fraction = vertical / min(a[3]-a[1], b[3]-b[1])
    gap = max(b[0]-a[2], a[0]-b[2])
    if v_fraction >= min_v_overlap and 0 <= gap <= max_gap_pt:
        return {"side_gap_pt": round(gap, 3),
                "vertical_overlap_ratio": round(v_fraction, 4)}
    return None


def review_conflicts(regions, extracted_tables, *, class_iou=0.75,
                     overlap_fraction=0.8, side_gap_pt=12):
    """Return independently reviewable evidence; do not resolve ambiguities.

    Geometry is in the same PDF page point coordinates. Region indices refer
    to *all* detector regions (not filtered table-only indices).
    """
    if not (0 < class_iou <= 1 and 0 < overlap_fraction <= 1 and side_gap_pt >= 0):
        raise ValueError("Bad thresholds")
    for r in regions:
        if not _valid_box(r.get("bbox_pdf_points")):
            raise ValueError("Invalid detector bbox")
    for t in extracted_tables:
        if not _valid_box(t.get("bbox_pt")):
            raise ValueError("Invalid PyMuPDF bbox")

    conflicts = []
    def emit(kind, ids, metrics, reason):
        conflicts.append({
            "code": kind, "detector_region_indices": list(ids),
            "measurements": metrics,
            "reason": reason,
            "status": "REVIEW_REQUIRED", "approved": False,
        })

    for i, a in enumerate(regions):
        for j in range(i + 1, len(regions)):
            b = regions[j]
            box_a, box_b = a["bbox_pdf_points"], b["bbox_pdf_points"]
            labels = {a["class_name"], b["class_name"]}
            if labels == {"figure", "table"}:
                iou = bbox_iou(box_a, box_b)
                if iou >= class_iou:
                    emit("FIGURE_TABLE_CLASS_CONFLICT", (i, j),
                         {"iou": round(iou, 4)},
                         "Overlapping figure/table class predictions")
            if a["class_name"] == b["class_name"] == "table":
                containment = _fraction_of_smaller(box_a, box_b)
                if containment >= overlap_fraction:
                    emit("OVERLAPPING_TABLE_REGIONS", (i, j),
                         {"smaller_region_overlap": round(containment, 4),
                          "iou": round(bbox_iou(box_a, box_b), 4)},
                         "Potential nested or duplicate table detections")
                sides = _near_side_by_side(
                    box_a, box_b, max_gap_pt=side_gap_pt
                )
                if sides:
                    emit("POSSIBLE_MULTIPART_TABLE", (i, j), sides,
                         "Adjacent aligned table areas may share one logical caption")

    # A PyMuPDF table that is largely inside a detected figure, but not
    # within a table-class region of similar area, is a possible figure
    # mistaken for grid data. Emit hint only, never suppress the cells.
    for ti, table in enumerate(extracted_tables):
        b = table["bbox_pt"]
        figures = [
            (ri, _fraction_of_smaller(b, r["bbox_pdf_points"]))
            for ri, r in enumerate(regions)
            if r["class_name"] == "figure"
        ]
        if not figures:
            continue
        ri, overlap = max(figures, key=lambda row: row[1])
        if overlap < overlap_fraction:
            continue
        tables = [
            r for r in regions if r["class_name"] == "table"
            and bbox_iou(b, r["bbox_pdf_points"]) >= class_iou
        ]
        emit("PYMUPDF_TABLE_IN_FIGURE", (ri,),
             {"pymupdf_table_index": ti,
              "figure_overlap_ratio": round(overlap, 4),
              "has_matching_table_detection": bool(tables)},
             "Tabular extraction overlaps a figure; inspect original page")

    return {
        "approved": False,
        "detector_region_count": len(regions),
        "extracted_table_count": len(extracted_tables),
        "review_findings": conflicts,
        "limitations": [
            "Multiple findings may refer to the same geometry; they are not independent errors.",
            "Proximity does not establish one logical table.",
            "No automatic suppression, merging, class selection or review approval.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality-json", type=Path, required=True)
    parser.add_argument("--layout-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() in {args.quality_json.resolve(),
                              args.layout_json.resolve()}:
        parser.error("Output must not overwrite input")
    quality = json.loads(args.quality_json.read_text(encoding="utf-8"))
    layout = json.loads(args.layout_json.read_text(encoding="utf-8"))
    if quality["source_image"] != layout["source_image"]:
        parser.error("Image names differ between quality and layout reports")
    width, height = quality["image_size_pixels"]
    if width <= 0 or height <= 0:
        parser.error("Bad image dimensions")
    # Existing quality-report detector boxes already in PDF coordinates,
    # but only 'table' entries are stored. For all classes convert directly
    # using the SAME PDF page size inferred from source detector/PDF boxes?
    # Require caller-supplied page dimensions to avoid guessing geometry.
    parser.error(
        "Full-class PDF coordinates required. Use --page-width-pt and "
        "--page-height-pt (see updated CLI options)."
    )


if __name__ == "__main__":
    main()
