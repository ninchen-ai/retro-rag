"""Read-only PDF Outline -> proposed elements in structure JSON v0.1.

Never approves elements, modifies PDFs, writes Nextcloud, or writes databases.
Text match bounding boxes are *anchors*, not table/figure content regions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote

import pymupdf

from experiments.pdf_base_adapter import build_base_structure
from experiments.validate_pdf_structure import validate

FIGURE = re.compile(r"^(?:figure|fig\.?)\s+\d+(?:[-.]\d+)*(?:\s*[:.]\s*|\s+|$)", re.I)
TABLE = re.compile(r"^table\s+\d+(?:[-.]\d+)*(?:\s*[:.]\s*|\s+|$)", re.I)
NAV = re.compile(
    r"^(?:start|title page|copyright page|contents|table of contents|"
    r"list of figures|figures|list of tables|tables|index|"
    r"front matter|back matter|revision history|acknowledg(?:e)?ments?|"
    r"bibliography|references|glossary)$", re.I
)
ROOT_NUMBER_AT_END = re.compile(r"^(.+?)\s+([1-9]\d?)$")


def classify_outline_title(title: str) -> str:
    """Conservative classification; uncertainty is an ordinary review case."""
    name = title.strip()
    if FIGURE.match(name):
        return "figure"
    if TABLE.match(name):
        return "table"
    if NAV.fullmatch(name):
        return "navigation"
    # Any other valid bookmark is only a heading *candidate*.
    return "heading"


def _variants(title):
    variants = [title]
    match = ROOT_NUMBER_AT_END.fullmatch(title.strip())
    if match:
        variants.append(match.group(2) + " " + match.group(1))
    return variants


def _valid_bbox(rect, page):
    box = [float(v) for v in rect]
    w, h = float(page.cropbox.width), float(page.cropbox.height)
    if not all(math.isfinite(v) for v in box):
        return False
    return 0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h


def _target_ys(page, destination):
    """Raw and flipped target: PyMuPDF destinations vary by PDF conventions.

    Both coordinates are only *hints*. Never assume the one from Intel 875P
    works for all PDFs. Rotated pages are treated as unanchored candidates.
    """
    point = destination.get("to") if isinstance(destination, dict) else None
    if point is None or page.rotation != 0:
        return []
    y = float(point.y)
    if not math.isfinite(y):
        return []
    height = float(page.cropbox.height)
    return [v for v in (y, height-y) if 0 <= v <= height]


def _candidate_anchor(page, title, destination, max_gap_pt=15):
    """Return a text *anchor* with conservative ambiguity handling."""
    variants = _variants(title)
    rects = []
    for variant in variants:
        rects = [r for r in page.search_for(variant) if _valid_bbox(r, page)]
        if rects:
            break

    if not rects:
        return None, "TEXT_NOT_LOCATED", []
    targets = _target_ys(page, destination)
    if targets:
        best = min(rects, key=lambda r: min(abs(r.y0-y) for y in targets))
        delta = min(abs(best.y0-y) for y in targets)
        position_status = "NEAR_TARGET" if delta <= max_gap_pt else "FAR_FROM_TARGET"
    else:
        best = min(rects, key=lambda r: (r.y0, r.x0))
        delta = None
        position_status = "NO_USABLE_TARGET"

    # Join rectangles belonging to the same visual line / split word.
    # Never interpret every rectangle as a separate text occurrence.
    center = (best.y0 + best.y1) / 2
    nearby = [
        r for r in rects
        if abs((r.y0+r.y1)/2 - center) <= max(3.0, (best.y1-best.y0)*0.45)
    ]
    # Multiple *distant vertical lines* with the same searched title are
    # ambiguous; do not silently claim a unique match.
    other_lines = [
        r for r in rects
        if abs((r.y0+r.y1)/2 - center) > max(3.0, (best.y1-best.y0)*0.45)
    ]
    if other_lines:
        position_status = "MULTIPLE_LINES_" + position_status

    rect = [
        min(r.x0 for r in nearby), min(r.y0 for r in nearby),
        max(r.x1 for r in nearby), max(r.y1 for r in nearby)
    ]
    return rect, position_status, (
        [f"rectangles={len(rects)}", f"delta_y_pt={delta:.2f}" if delta is not None else "target=unavailable"]
    )


def _placeholder(page, destination):
    """Clearly provisional 1-pt marker; never a real text or image box."""
    w, h = float(page.cropbox.width), float(page.cropbox.height)
    ys = _target_ys(page, destination)
    y = ys[0] if ys else 0
    x = 0.0
    return [x, min(max(y, 0), h-1), min(1.0, w), min(max(y, 0), h-1)+1.0]


def add_outline_proposals(raw_pdf: bytes, base: dict) -> dict:
    """Add one *proposed* item per valid bookmark; no other content edits."""
    if base["document"]["sha256"] != hashlib.sha256(raw_pdf).hexdigest():
        raise ValueError("Base JSON belongs to another PDF SHA-256")
    result = json.loads(json.dumps(base))
    if result["elements"]:
        raise ValueError("Base JSON already contains elements; refusing to overwrite or merge")
    if result["relationships"]:
        raise ValueError("Base JSON already contains relationships")
    if result["quality"]["review_status"] != "unreviewed":
        raise ValueError("Base JSON is not unreviewed")
    warnings = result["quality"].setdefault("warnings", [])
    counts = Counter()
    heading_stack = []  # (outline_level, element_id), heading only

    with pymupdf.open(stream=raw_pdf, filetype="pdf") as doc:
        if doc.needs_pass or doc.page_count != len(result["pages"]):
            raise ValueError("PDF page count or encryption mismatch")

        for ordinal, (level, title, pdf_page, dest) in enumerate(doc.get_toc(simple=False), start=1):
            if not (1 <= pdf_page <= doc.page_count):
                warnings.append(f"Outline #{ordinal}: invalid target page {pdf_page}; ignored")
                counts["INVALID_PAGE"] += 1
                continue
            if not title.strip():
                warnings.append(f"Outline #{ordinal}: blank title; ignored")
                counts["BLANK_TITLE"] += 1
                continue

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            kind = classify_outline_title(title)
            page = doc[pdf_page - 1]
            bbox, locator, details = _candidate_anchor(page, title, dest)
            if bbox is None:
                bbox = _placeholder(page, dest)
            if not _valid_bbox(bbox, page):
                # Do not drop outline entry: record it as an uncertain
                # navigation marker if geometric anchors are unusable.
                bbox = _placeholder(page, {})
                locator = "INVALID_GEOMETRY"

            parent = heading_stack[-1][1] if heading_stack else None
            item_id = f"outline-{ordinal:05d}"
            # An unmatched figure/table bookmark denotes a reference, not a
            # recognized figure/table *region*. Its rectangle is only an anchor.
            if locator != "NEAR_TARGET":
                review = "unclear"
            else:
                review = "proposed"
            if kind == "navigation":
                parent = None
            entry = {
                "element_id": item_id,
                "element_type": kind,
                "page_number": pdf_page,
                "bbox_pt": [round(float(v), 3) for v in bbox],
                "title_or_text": title,
                "source_span_ids": [],
                "parent_id": parent,
                "provenance": [{
                    "method": "pdf_outline",
                    "evidence": (
                        f"outline_index={ordinal}; level={level}; locator={locator}; "
                        + "; ".join(details)
                        + "; bbox is TITLE ANCHOR, not table/figure extent"
                    ),
                }],
                "review": {"status": review},
            }
            result["elements"].append(entry)
            counts[f"{kind}:{review}"] += 1
            if kind == "heading":
                heading_stack.append((level, item_id))
            if review == "unclear":
                warnings.append(f"Outline #{ordinal} p{pdf_page}: {locator} - {title[:90]}")

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--nextcloud-path")
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--base-json", type=Path, help="Previously extracted v0.1 JSON")
    parser.add_argument("--no-spans", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.pdf:
        if args.pdf.resolve() == args.out.resolve():
            parser.error("Output may not overwrite source PDF")
        raw_pdf = args.pdf.read_bytes()
        source_uri = args.pdf.resolve().as_uri()
        filename = args.pdf.name
    else:
        from scripts.import_pdf import get_webdav
        password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass("Nextcloud-App-Passwort: ")
        raw_pdf, _, _ = get_webdav(
            args.nextcloud_url, args.nextcloud_user, password, args.nextcloud_path
        )
        source_uri = ("nextcloud://" + quote(args.nextcloud_user, safe="") +
                      "/" + quote(args.nextcloud_path, safe="/"))
        filename = args.nextcloud_path.rsplit("/", 1)[-1]
    if args.base_json:
        if args.base_json.resolve() == args.out.resolve():
            parser.error("Output may not overwrite base JSON")
        base = json.loads(args.base_json.read_text(encoding="utf-8"))
    else:
        base = build_base_structure(
            raw_pdf, source_uri=source_uri, filename=filename,
            include_spans=not args.no_spans
        )
    output = add_outline_proposals(raw_pdf, base)
    errors = validate(output)
    if errors:
        raise ValueError("Schema validation failed: " + "; ".join(errors[:10]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = Counter((e["element_type"], e["review"]["status"]) for e in output["elements"])
    print(f"Seiten: {len(output['pages'])} | Lesezeichen-Vorschläge: {len(output['elements'])}")
    for (kind, status), count in sorted(summary.items()):
        print(f"  {kind} / {status}: {count}")
    print(f"Warnungen: {len(output['quality'].get('warnings', []))}")
    print(f"Schema gültig, keine Freigabe. JSON: {args.out}")


if __name__ == "__main__":
    main()
