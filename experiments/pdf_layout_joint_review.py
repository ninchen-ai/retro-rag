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
    """Suggest possible adjacency; this is NOT a semantic classification."""
    bottom = heading_box[3]
    info = []
    for region in regions:
        if region["class_name"] not in ("figure", "figure_caption"):
            continue
        other = region["bbox_pdf_points"]
        gap = other[1] - bottom
        if -8 <= gap <= threshold_pt:
            info.append({
                "class_name": region["class_name"],
                "vertical_gap_pt": round(gap, 1),
                "confidence": region["confidence"],
            })
    return sorted(info, key=lambda x: abs(x["vertical_gap_pt"]))


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


def joint_review(raw_pdf, png, detections, pdf_page):
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
    return {
        "pdf_page": pdf_page,
        "image": str(png),
        "image_size_pixels": [width, height],
        "approved": False,
        "detector_regions": regions,
        "heading_candidates": candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", help="Local PDF; otherwise read PDF from Nextcloud")
    parser.add_argument("--pdf-path", default=(
        "Retro-Computing/Referenzwissen/Schnittstellen/AGP/agpdg11a.pdf"
    ))
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--page", type=int, default=38)
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
    report = joint_review(raw, image, layout["detections"], args.page)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Page: {args.page}; review candidates: {len(report['heading_candidates'])}")
    for h in report["heading_candidates"]:
        print(h["heading"], "|", h.get("review_reason", h["location_status"]))
        for near in h["nearby_regions"]:
            print("  ", near)
    print(f"Review JSON: {output}")


if __name__ == "__main__":
    main()
