"""Review-only page-text captions versus DocLayout-YOLO regions.

All PDF text and detector boxes remain unchanged. No figure/table is accepted,
suppressed, merged, indexed, or written to Nextcloud or PostgreSQL.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re

import pymupdf

from experiments.pdf_table_region_review import layout_regions_in_pdf

# A numbered *caption*, not arbitrary mention of "Table 5" in a paragraph.
# Supports ordinary / en-dash / em-dash numbering; no hardware-specific terms.
_CAPTION = re.compile(
    r"^\s*(?P<kind>Table|Figure|Fig\.)\s+"
    r"(?P<number>\d+(?:[-.\u2013\u2014]\d+)*)"
    r"\s*[.:\u2013\u2014]?\s+(?P<description>\S.*)$",
    re.IGNORECASE,
)


def extract_caption_candidates(page):
    """One candidate per matching visual text line, including its PDF bbox.

    This intentionally does not guess multi-line continuation, caption
    semantics, or group texts from different line blocks.
    """
    found = []
    for bi, block in enumerate(page.get_text("dict").get("blocks", [])):
        if block.get("type", 0) != 0:
            continue
        for li, line in enumerate(block.get("lines", [])):
            spans = [s for s in line.get("spans", []) if s.get("text")]
            if not spans:
                continue
            exact = "".join(s["text"] for s in spans)
            parsed = _CAPTION.match(exact)
            if not parsed:
                continue
            bbox = [
                round(min(float(s["bbox"][0]) for s in spans), 3),
                round(min(float(s["bbox"][1]) for s in spans), 3),
                round(max(float(s["bbox"][2]) for s in spans), 3),
                round(max(float(s["bbox"][3]) for s in spans), 3),
            ]
            kind = parsed.group("kind").casefold()
            found.append({
                "caption_id": f"block-{bi}-line-{li}",
                "kind": "table" if kind == "table" else "figure",
                "number": parsed.group("number"),
                "text": exact,  # verbatim, no normalized overwrite
                "bbox_pt": bbox,
                "source_block_index": bi,
                "source_line_index": li,
                "status": "CANDIDATE_ONLY",
                "approved": False,
            })
    return found


def _horizontal_overlap(a, b):
    width = min(a[2] - a[0], b[2] - b[0])
    return (max(0., min(a[2], b[2]) - max(a[0], b[0])) / width
            if width > 0 else 0.)


def match_captions(captions, regions, *, max_gap_pt=40,
                   min_horizontal_overlap=0.25):
    """Associate nearby regions with the correct class; never force a winner.

    Region indices are original DocLayout detector indices, including
    captions and non-table regions, so references remain stable.
    """
    if max_gap_pt < 0 or not 0 < min_horizontal_overlap <= 1:
        raise ValueError("Invalid thresholds")
    matches = []
    for caption in captions:
        box = caption["bbox_pt"]
        if not (box[0] < box[2] and box[1] < box[3]):
            raise ValueError("Invalid caption rectangle")
        choices = []
        for index, region in enumerate(regions):
            if region["class_name"] != caption["kind"]:
                continue
            rb = region["bbox_pdf_points"]
            # The caption should precede the region vertically. Figure captions
            # BELOW the figure remain unresolved for this first experiment.
            gap = rb[1] - box[3]
            overlap = _horizontal_overlap(box, rb)
            if 0 <= gap <= max_gap_pt and overlap >= min_horizontal_overlap:
                choices.append({
                    "detector_region_index": region.get("source_detection_index", index),
                    "vertical_gap_pt": round(gap, 3),
                    "horizontal_overlap_ratio": round(overlap, 4),
                    "detector_confidence": region.get("confidence"),
                })
        choices.sort(key=lambda x: (x["vertical_gap_pt"], x["detector_region_index"]))
        matches.append({
            "caption_id": caption["caption_id"],
            "text": caption["text"],
            "kind": caption["kind"],
            "candidate_regions": choices,
            "status": ("ONE_CANDIDATE" if len(choices) == 1 else
                       "NO_CANDIDATE" if not choices else "MULTIPLE_CANDIDATES"),
            "approved": False,
        })
    # If two captions claim the same detector region, neither is a unique
    # semantic association even if each had only one geometric candidate.
    by_region = {}
    for match in matches:
        if match["status"] == "ONE_CANDIDATE":
            key = match["candidate_regions"][0]["detector_region_index"]
            by_region.setdefault(key, []).append(match)
    for claimants in by_region.values():
        if len(claimants) > 1:
            for match in claimants:
                match["status"] = "SHARED_REGION_CONFLICT"
    return {
        "approved": False,
        "caption_matches": matches,
        "limitations": [
            "Only single visual lines beginning with numbered English Table/Figure captions.",
            "Only preceding captions with nearby same-class regions are matched.",
            "One caption may describe multiple physical blocks; multiple hits remain ambiguous.",
            "Positions and detector confidence cannot establish semantic correctness.",
            "Source PDF, original page text, spans and outline elements are untouched.",
        ],
    }


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
    parser.add_argument("--page", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    inputs = [args.outline_json, args.layout_json, args.image]
    if args.pdf is not None:
        inputs.append(args.pdf)
    if args.out.resolve() in {p.resolve() for p in inputs}:
        parser.error("Output must not overwrite inputs")
    outline = json.loads(args.outline_json.read_text(encoding="utf-8"))
    layout = json.loads(args.layout_json.read_text(encoding="utf-8"))
    if layout.get("source_image") != args.image.name:
        parser.error("Layout source_image does not match provided PNG")
    if not 1 <= args.page <= len(outline["pages"]):
        parser.error("Invalid 1-based page number")
    page_metadata = outline["pages"][args.page - 1]
    if page_metadata["page_number"] != args.page or page_metadata["rotation"] != 0:
        parser.error("Page metadata differs or page is rotated")
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
        raise ValueError("PDF SHA256 differs from outline source")
    image = pymupdf.Pixmap(str(args.image))
    image_width, image_height = image.width, image.height
    del image
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        if document.page_count != len(outline["pages"]):
            raise ValueError("PDF page count mismatch")
        page = document[args.page-1]
        if page.rotation or abs(page.rect.width-page_metadata["width_pt"]) > .1 or (
            abs(page.rect.height-page_metadata["height_pt"]) > .1
        ):
            raise ValueError("Page geometry differs from outline")
        candidates = extract_caption_candidates(page)
    regions = layout_regions_in_pdf(
        layout, image_width, image_height, page_metadata
    )
    report = match_captions(candidates, regions)
    report.update({
        "page_number": args.page,
        "document_sha256": digest,
        "source_image": args.image.name,
        "detector_model": layout.get("model"),
        "caption_candidates": candidates,
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"Seite {args.page}: {len(candidates)} Caption-Kandidaten")
    for m in report["caption_matches"]:
        print(m["kind"], m["status"], m["text"].strip(),
              "| Detektoren:", [c["detector_region_index"]
                               for c in m["candidate_regions"]])
    print("Keine Freigabe; Review-JSON:", args.out)


if __name__ == "__main__":
    main()
