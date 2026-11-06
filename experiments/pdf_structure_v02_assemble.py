"""Read-only additive assembly of v0.2 observations from existing page reports.

This is NOT a content approval or a table merger. Every report is checked
against source PDF SHA and page/image identifiers before copy.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from experiments.pdf_structure_v02 import upgrade_v01, validate_v02
from experiments.pdf_table_region_review import layout_regions_in_pdf


def assemble(v01, layout, quality, captions, conflicts):
    doc_hash = v01["document"]["sha256"]
    page_no = quality["page_number"]
    if not 1 <= page_no <= len(v01["pages"]):
        raise ValueError("Bad page")
    page = v01["pages"][page_no - 1]
    if page["page_number"] != page_no or page["rotation"]:
        raise ValueError("Page metadata mismatch / rotated page unsupported")
    image_name = quality["source_image"]
    if any(report.get("source_image") != image_name
           for report in (layout, captions, conflicts)):
        raise ValueError("Report source_image mismatch")
    if any(report.get("document_sha256") != doc_hash
           for report in (quality, captions, conflicts)):
        raise ValueError("Report PDF hash mismatch")
    if captions.get("page_number") != page_no or (
        conflicts.get("page_number") != page_no
    ):
        raise ValueError("Report page mismatch")
    dimensions = quality["image_size_pixels"]
    if not (len(dimensions) == 2 and all(isinstance(x, int) and x > 0
                                          for x in dimensions)):
        raise ValueError("Bad reported image dimensions")
    image_width, image_height = dimensions
    detections = layout_regions_in_pdf(layout, image_width, image_height, page)

    result = upgrade_v01(v01)
    prefix = f"v02-p{page_no}"
    runs = {
        "pymupdf": prefix + "-run-pymupdf",
        "doclayout_yolo": prefix + "-run-layout",
        "pdf_caption": prefix + "-run-caption",
    }
    for method, run_id in runs.items():
        run = {"run_id": run_id, "method": method,
               "source_sha256": doc_hash, "parameters": {"page": page_no}}
        if method == "doclayout_yolo":
            run["model_id"] = layout.get("model") or "unspecified"
            run["parameters"]["image_name"] = image_name
            run["parameters"]["image_size_pixels"] = copy.deepcopy(dimensions)
        result["processing_runs"].append(run)

    # Source detector index is preserved; do not deduplicate overlapping boxes.
    for idx, region in enumerate(detections):
        result["physical_regions"].append({
            "region_id": f"{prefix}-det-{idx}",
            "page_number": page_no,
            "bbox_pt": copy.deepcopy(region["bbox_pdf_points"]),
            "region_kind": (
                region["class_name"] if region["class_name"] in
                ("table", "figure", "caption", "diagram") else "other"
            ),
            "evidence": {
                "method": "doclayout_yolo",
                "run_id": runs["doclayout_yolo"],
                "detector_index": idx,
                **({"model_confidence": region["confidence"]}
                   if region["confidence"] is not None else {}),
            },
            "review": {"status": "proposed"},
        })

    for idx, table in enumerate(quality["pymupdf_tables"]):
        result["physical_regions"].append({
            "region_id": f"{prefix}-pymupdf-{idx}",
            "page_number": page_no,
            "bbox_pt": copy.deepcopy(table["bbox_pt"]),
            "region_kind": "table",
            "raw_cells": copy.deepcopy(table["cells"]),
            "evidence": {
                "method": "pymupdf", "run_id": runs["pymupdf"],
                "pymupdf_table_index": idx,
            },
            "review": {"status": "proposed"},
        })

    cap_indices = {}
    for idx, caption in enumerate(captions["caption_candidates"]):
        cid = f"{prefix}-caption-{idx}"
        cap_indices[caption["caption_id"]] = cid
        result["physical_regions"].append({
            "region_id": cid,
            "page_number": page_no,
            "bbox_pt": copy.deepcopy(caption["bbox_pt"]),
            "region_kind": "caption",
            "evidence": {
                "method": "pdf_caption", "run_id": runs["pdf_caption"],
                "raw_text": caption["text"],
            },
            "review": {"status": "proposed"},
        })
        logical_id = f"{prefix}-logical-{idx}"
        result["logical_elements"].append({
            "logical_id": logical_id,
            "element_kind": caption["kind"],
            "label": caption["text"],
            "review": {"status": "proposed"},
        })
        result["relationships_v02"].append({
            "relation_id": f"{prefix}-rel-caption-{idx}",
            "from_id": logical_id, "to_id": cid,
            "relation_type": "has_caption",
            "review": {"status": "proposed"},
        })

    # A logical caption may link to one or many detector candidates.
    # This is a *proposal* and never a table reconstruction.
    for match in captions["caption_matches"]:
        if match["caption_id"] not in cap_indices:
            raise ValueError("Caption match references missing candidate")
        caption_idx = int(cap_indices[match["caption_id"]].rsplit("-", 1)[-1])
        logical_id = f"{prefix}-logical-{caption_idx}"
        for option_idx, option in enumerate(match["candidate_regions"]):
            det_idx = option["detector_region_index"]
            if not 0 <= det_idx < len(detections):
                raise ValueError("Caption match refers to unknown detector")
            result["relationships_v02"].append({
                "relation_id": f"{prefix}-rel-region-{caption_idx}-{option_idx}",
                "from_id": logical_id, "to_id": f"{prefix}-det-{det_idx}",
                "relation_type": "has_region",
                "review": {"status": "proposed"},
            })

    # Quality report indexes tables within only the class=table detections,
    # not the full detector index space. Do not conflate these namespaces.
    table_detector_indices = [
        i for i, d in enumerate(detections) if d["class_name"] == "table"
    ]
    for item in quality["detector_to_pymupdf"]:
        ti = item["detector_region_index"]
        if not 0 <= ti < len(table_detector_indices):
            raise ValueError("Quality match uses unknown table-region index")
        det_idx = table_detector_indices[ti]
        for option_idx, option in enumerate(item["matches"]):
            py_idx = option["pymupdf_table_index"]
            if not 0 <= py_idx < len(quality["pymupdf_tables"]):
                raise ValueError("Quality match uses unknown PyMuPDF table")
            result["relationships_v02"].append({
                "relation_id": f"{prefix}-rel-extract-{ti}-{option_idx}",
                "from_id": f"{prefix}-det-{det_idx}",
                "to_id": f"{prefix}-pymupdf-{py_idx}",
                "relation_type": "derived_from",
                "review": {"status": "proposed"},
            })

    # Conflict references are original detector region indices.
    for fi, finding in enumerate(conflicts["review_findings"]):
        ids = finding["detector_region_indices"]
        if any(not 0 <= idx < len(detections) for idx in ids):
            raise ValueError("Conflict refers to unknown detector index")
        if len(ids) == 2:
            a, b = ids
            result["relationships_v02"].append({
                "relation_id": f"{prefix}-rel-conflict-{fi}",
                "from_id": f"{prefix}-det-{a}",
                "to_id": f"{prefix}-det-{b}",
                "relation_type": (
                    "possible_same_table"
                    if finding["code"] == "POSSIBLE_MULTIPART_TABLE"
                    else "conflicts_with"
                ),
                "review": {"status": "proposed",
                           "reason": finding["code"]},
            })

    errors = validate_v02(result)
    if errors:
        raise ValueError("Assembled v0.2 failed: " + "; ".join(errors[:10]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v01-json", type=Path, required=True)
    parser.add_argument("--layout-json", type=Path, required=True)
    parser.add_argument("--quality-json", type=Path, required=True)
    parser.add_argument("--caption-json", type=Path, required=True)
    parser.add_argument("--conflict-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sources = (args.v01_json, args.layout_json, args.quality_json,
               args.caption_json, args.conflict_json)
    if args.out.resolve() in {p.resolve() for p in sources}:
        parser.error("Output must not overwrite an input")
    blobs = [
        json.loads(p.read_text(encoding="utf-8")) for p in sources
    ]
    result = assemble(*blobs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print("v0.2 ready; regions:", len(result["physical_regions"]),
          "| logical:", len(result["logical_elements"]),
          "| relations:", len(result["relationships_v02"]))
    print("Unapproved review only:", args.out)


if __name__ == "__main__":
    main()
