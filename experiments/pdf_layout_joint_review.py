"""Read-only joint review: PyMuPDF heading candidates + DocLayout-YOLO regions.

Inputs:
  --image: original unannotated PNG used for layout detection
  --layout-json: DocLayout-YOLO JSON output for the SAME image
  --pdf: local PDF (optional; otherwise WebDAV is read only)

No heading is accepted or rejected automatically. No database writes.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

import pymupdf

from scripts.pdf_heading_review import build_heading_review


def pixel_box_to_pdf(box, page_width, page_height, image_width, image_height):
    """Convert pixel xyxy into PDF page points, validating bounds."""
    if len(box) != 4 or image_width <= 0 or image_height <= 0:
        raise ValueError("Invalid detector rectangle or image dimensions")
    x0, y0, x1, y1 = map(float, box)
    if not (0 <= x0 < x1 <= image_width and 0 <= y0 < y1 <= image_height):
        raise ValueError(f"Detector rectangle outside image: {box}")
    return (
        x0 * page_width / image_width,
        y0 * page_height / image_height,
        x1 * page_width / image_width,
        y1 * page_height / image_height,
    )


def figure_proximity(heading_box, regions, threshold_pt=40.0):
    """Report geometric relationships to figures; never decide semantics.

    Overlap and near-above/below relationships require horizontal overlap.
    When rectangles are separated horizontally, allow a small side gap only
    if their vertical ranges overlap. All distances are PDF points.
    """
    hx0, hy0, hx1, hy1 = map(float, heading_box)
    if not (hx0 < hx1 and hy0 < hy1):
        raise ValueError("Invalid heading rectangle")
    info = []
    for region in regions:
        if region["class_name"] not in ("figure", "figure_caption"):
            continue
        fx0, fy0, fx1, fy1 = map(float, region["bbox_pdf_points"])
        if not (fx0 < fx1 and fy0 < fy1):
            continue
        horizontal_overlap = min(hx1, fx1) - max(hx0, fx0)
        vertical_overlap = min(hy1, fy1) - max(hy0, fy0)
        relation = None
        gap = None

        if horizontal_overlap > 0 and vertical_overlap > 0:
            relation = "OVERLAPS_REGION"
            gap = 0.0
        elif horizontal_overlap > 0 and 0 <= fy0 - hy1 <= threshold_pt:
            relation = "ABOVE_REGION"
            gap = fy0 - hy1
        elif horizontal_overlap > 0 and 0 <= hy0 - fy1 <= threshold_pt:
            relation = "BELOW_REGION"
            gap = hy0 - fy1
        elif vertical_overlap > 0:
            side_gap = fx0 - hx1 if hx1 <= fx0 else hx0 - fx1
            if 0 <= side_gap <= threshold_pt:
                relation = "BESIDE_REGION"
                gap = side_gap

        if relation is not None:
            item = {
                "class_name": region["class_name"],
                "relation": relation,
                "distance_pt": round(gap, 1),
                "confidence": region["confidence"],
            }
            # Backward-compatible for prior below-figure tests/reports.
            if relation == "ABOVE_REGION":
                item["vertical_gap_pt"] = round(gap, 1)
            info.append(item)
    return sorted(info, key=lambda item: (item["distance_pt"], item["class_name"]))


def locate_heading(page, heading):
    """Disambiguate repeated text using an exact visual-line match.

    Fails closed on multiple identical visual lines rather than inventing a
    unique match. The original text is unchanged.
    """
    from scripts.pdf_layout_headings import visual_lines

    matches = page.search_for(heading)
    if len(matches) == 1:
        return matches[0]
    same_lines = [
        line for line in visual_lines(page)
        if line.text.casefold() == heading.casefold()
    ]
    if len(same_lines) != 1 or not matches:
        return None
    line = same_lines[0]
    distances = sorted(
        (abs(box.y0 - line.y) + abs(box.x0 - line.x), box)
        for box in matches
    )
    if len(distances) > 1 and distances[1][0] - distances[0][0] < 2:
        return None
    return distances[0][1]


def joint_review(raw_pdf, png, detections, pdf_page, *, reference_page=None, auto_labels=False):
    """Create review suggestions without changing the extraction or anchors."""
    with pymupdf.open(stream=raw_pdf, filetype="pdf") as pdf:
        if not (1 <= pdf_page <= pdf.page_count):
            raise ValueError("PDF page outside document")
        page = pdf[pdf_page - 1]
        page_width, page_height = page.rect.width, page.rect.height
    pix = pymupdf.Pixmap(str(png))
    width, height = pix.width, pix.height
    del pix
    regions = []
    for d in detections:
        rect = pixel_box_to_pdf(
            d["bbox_pixels"], page_width, page_height, width, height
        )
        regions.append({
            "class_name": d["class_name"],
            "confidence": d["confidence"],
            "bbox_pdf_points": [round(x, 1) for x in rect],
        })
    review = build_heading_review(raw_pdf)
    with pymupdf.open(stream=raw_pdf, filetype="pdf") as pdf:
        page = pdf[pdf_page - 1]
        candidates = []
        for h in review.headings:
            if h.pdf_page != pdf_page:
                continue
            found = page.search_for(h.heading)
            rect = locate_heading(page, h.heading)
            if rect is None:
                candidates.append({
                    "heading": h.heading,
                    "status": "REVIEW_REQUIRED",
                    "location_status": "AMBIGUOUS_OR_UNMATCHED",
                    "found_positions": len(found),
                    "nearby_regions": [],
                })
                continue
            nearby = figure_proximity(
                tuple(rect), regions
            )
            candidates.append({
                "heading": h.heading,
                "status": "REVIEW_REQUIRED",
                "location_status": "LOCATED",
                "bbox_pdf_points": [round(x, 1) for x in rect],
                "nearby_regions": nearby,
                "review_reason": (
                    "POSSIBLY_FIGURE_ASSOCIATED"
                    if nearby else "NO_NEARBY_FIGURE_DETECTED"
                ),
            })
    result = {
        "pdf_page": pdf_page,
        "image": str(png),
        "image_size_pixels": [width, height],
        "approved": False,
        "detector_regions": regions,
        "heading_candidates": candidates,
    }
    if auto_labels:
        from experiments.pdf_auto_label_instances import collect_span_instances
        with pymupdf.open(stream=raw_pdf, filetype="pdf") as pdf:
            result["auto_label_instances"] = collect_span_instances(
                pdf[pdf_page - 1], regions
            )
    if reference_page is not None:
        from experiments.pdf_label_instances import extract_reference_label_instances
        with pymupdf.open(stream=raw_pdf, filetype="pdf") as pdf:
            result["label_instances"] = extract_reference_label_instances(
                pdf[pdf_page - 1], reference_page, regions
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", help="Local PDF; otherwise read PDF from Nextcloud")
    parser.add_argument("--pdf-path", default=(
        "Retro-Computing/Referenzwissen/Schnittstellen/AGP/agpdg11a.pdf"
    ))
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--page", type=int, default=38)
    parser.add_argument("--reference", type=Path, help="Optional confirmed reference JSON for physical label instances")
    parser.add_argument("--auto-labels", action="store_true", help="Find unconfirmed figure-overlapping PDF spans without a reference")
    parser.add_argument("--image", default="/tmp/agpdg11a_page38.png")
    parser.add_argument("--layout-json", default="/tmp/retro-doclayout/layout_report.json")
    parser.add_argument("--out", default="/tmp/retro-doclayout/joint_review.json")
    args = parser.parse_args()
    if args.pdf:
        raw = Path(args.pdf).read_bytes()
    else:
        from scripts.import_pdf import get_webdav
        password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass(
            "Nextcloud-App-Passwort: "
        )
        raw, _, _ = get_webdav(
            args.nextcloud_url, args.nextcloud_user, password, args.pdf_path
        )
    source = Path(args.layout_json)
    layout = json.loads(source.read_text(encoding="utf-8"))
    image = Path(args.image).resolve()
    if not image.is_file():
        parser.error(f"Missing unannotated image: {image}")
    if layout.get("source_image") != image.name:
        parser.error("Layout report source_image differs from supplied image")
    reference_page = None
    if args.reference:
        ref_data = json.loads(args.reference.read_text(encoding="utf-8"))
        if ref_data.get("pdf") not in (None, Path(args.pdf_path).name):
            parser.error("Reference PDF does not match the PDF being analyzed")
        ref_pages = [p for p in ref_data["pages"] if p["pdf_page"] == args.page]
        if len(ref_pages) != 1:
            parser.error(f"Reference has no unique entry for page {args.page}")
        reference_page = ref_pages[0]
    report = joint_review(
        raw, image, layout["detections"], args.page,
        reference_page=reference_page, auto_labels=args.auto_labels
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Page: {args.page}; review candidates: {len(report['heading_candidates'])}")
    for h in report["heading_candidates"]:
        print(h["heading"], "|", h.get("review_reason", h["location_status"]))
        for near in h["nearby_regions"]:
            print("  ", near)
    if args.auto_labels:
        labels = report["auto_label_instances"]
        print(f"Automatic span proposals: {len(labels)}")
        for item in labels:
            print(
                item["text"], "| occurrence", item["occurrence"],
                "| suppressed duplicate draws", item["duplicate_draws"],
                "| bbox", item["bbox_pdf_points"]
            )
    if reference_page is not None:
        print("Physical reference instances:")
        for item in report["label_instances"]:
            print(
                item["heading"], "occurrence", item.get("occurrence", "?"),
                item["location_status"], item.get("review_reason", ""),
                item.get("bbox_pdf_points")
            )
    print(f"Review JSON: {output}")


if __name__ == "__main__":
    main()
