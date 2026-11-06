"""Read-only match of outline table-label anchors to layout table rectangles.

Separate experiment report: never modifies schema v0.1 elements, PDFs, DB, or
Nextcloud. All matches are UNAPPROVED and geometrical, not table-content OCR.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymupdf

from experiments.pdf_layout_joint_review import pixel_box_to_pdf


def _overlap_fraction(a, b):
    horizontal = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    return horizontal / max(0.001, min(a[2] - a[0], b[2] - b[0]))


def associate_table_anchors(outline, regions, *, page_number, max_gap_pt=35,
                            min_horizontal_overlap=0.3):
    """Conservative one-to-one suggestions, preserving ambiguous candidates."""
    if not 0 < min_horizontal_overlap <= 1 or max_gap_pt < 0:
        raise ValueError("Invalid geometric thresholds")
    if not 1 <= page_number <= len(outline["pages"]):
        raise ValueError("Page out of range")
    anchors = [
        e for e in outline["elements"]
        if e["element_type"] == "table" and e["page_number"] == page_number
        and e["review"]["status"] == "proposed"
        and "locator=NEAR_TARGET" in e["provenance"][0]["evidence"]
    ]
    # An outline 'table' bbox only covers its title, not its cells.
    tables = [r for r in regions if r["class_name"] == "table"]
    matches = []
    for anchor in anchors:
        ax0, ay0, ax1, ay1 = anchor["bbox_pt"]
        options = []
        for idx, table in enumerate(tables):
            bx0, by0, bx1, by1 = table["bbox_pdf_points"]
            gap = by0 - ay1
            fraction = _overlap_fraction(anchor["bbox_pt"], table["bbox_pdf_points"])
            if 0 <= gap <= max_gap_pt and fraction >= min_horizontal_overlap:
                options.append({
                    "region_index": idx,
                    "gap_pt": round(gap, 2),
                    "horizontal_overlap_ratio": round(fraction, 3),
                })
        # No arbitrary winner when multiple regions fit the same anchor.
        matches.append({
            "element_id": anchor["element_id"],
            "title": anchor["title_or_text"],
            "candidate_regions": options,
            "status": "ONE_CANDIDATE" if len(options) == 1 else (
                "NO_CANDIDATE" if not options else "MULTIPLE_CANDIDATES"
            ),
            "approved": False,
        })
    # Even a unique candidate cannot be committed if another title
    # claims the same table region.
    owners = {}
    for match in matches:
        if match["status"] == "ONE_CANDIDATE":
            idx = match["candidate_regions"][0]["region_index"]
            owners.setdefault(idx, []).append(match)
    for claimants in owners.values():
        if len(claimants) > 1:
            for match in claimants:
                match["status"] = "SHARED_REGION_CONFLICT"
    return {
        "page_number": page_number,
        "approved": False,
        "table_regions": tables,
        "anchor_matches": matches,
        "unmatched_or_conflicting": sum(
            row["status"] != "ONE_CANDIDATE" for row in matches
        ),
        "notes": [
            "Geometry only. No extracted cell values or semantic approval.",
            "Table region bbox and outline title-anchor bbox have different semantics.",
        ],
    }


def layout_regions_in_pdf(layout, image_width, image_height, page):
    """Convert detector coordinates for the same unrotated PDF page."""
    if page["rotation"] != 0:
        raise ValueError("Rotated pages are not yet supported")
    width, height = page["width_pt"], page["height_pt"]
    detections = layout["detections"]
    output = []
    for index, detection in enumerate(detections):
        bbox = pixel_box_to_pdf(
            detection["bbox_pixels"], width, height,
            image_width, image_height
        )
        output.append({
            "source_detection_index": index,
            "class_name": detection["class_name"],
            "bbox_pdf_points": [round(v, 3) for v in bbox],
            "confidence": detection.get("confidence"),
        })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outline-json", required=True, type=Path)
    parser.add_argument("--layout-json", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path,
                        help="Exact unannotated PNG used for layout detection")
    parser.add_argument("--page", type=int, required=True, help="1-based PDF page")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    if args.out.resolve() in {
        args.outline_json.resolve(), args.layout_json.resolve(), args.image.resolve()
    }:
        parser.error("Output must not replace input data")
    outline = json.loads(args.outline_json.read_text(encoding="utf-8"))
    layout = json.loads(args.layout_json.read_text(encoding="utf-8"))
    if not 1 <= args.page <= len(outline["pages"]):
        parser.error("Invalid PDF page")
    if layout.get("source_image") != args.image.name:
        parser.error("Layout JSON source_image does not match PNG name")
    pix = pymupdf.Pixmap(str(args.image))
    width, height = pix.width, pix.height
    del pix
    regions = layout_regions_in_pdf(
        layout, width, height, outline["pages"][args.page - 1]
    )
    report = associate_table_anchors(outline, regions, page_number=args.page)
    report["document_sha256"] = outline["document"]["sha256"]
    report["source_image"] = args.image.name
    report["image_size_pixels"] = [width, height]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PDF-Seite {args.page} | Tabellenregionen {len(report['table_regions'])} "
          f"| Tabellenanker {len(report['anchor_matches'])}")
    for match in report["anchor_matches"]:
        print(match["status"], match["title"],
              match["candidate_regions"])
    print("Review erforderlich; keine Änderungen an Quellen oder Schema.")
    print("Bericht:", args.out)


if __name__ == "__main__":
    main()
