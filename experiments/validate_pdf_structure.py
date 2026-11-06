"""Validate universal PDF structure v0.1, without modifying data.

JSON Schema structural checks require optional 'jsonschema' package.
Cross-reference and geometry checks use only the standard library.
The report is a validation *diagnostic*, not approval of content accuracy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "schemas" / "pdf_document_structure_v0.1.schema.json"


def validate_structure(data: dict) -> list[str]:
    """Cross-record checks beyond JSON Schema, fail closed on broken links."""
    errors = []
    pages = data.get("pages", [])
    doc = data.get("document", {})
    page_map = {p["page_number"]: p for p in pages}
    if len(page_map) != len(pages):
        errors.append("Duplicate page_number")
    if set(page_map) != set(range(1, doc.get("page_count", 0) + 1)):
        errors.append("Pages must enumerate every PDF page exactly once")

    spans = data.get("source_spans", [])
    elements = data.get("elements", [])
    span_map = {s["span_id"]: s for s in spans}
    element_map = {e["element_id"]: e for e in elements}
    if len(span_map) != len(spans):
        errors.append("Duplicate span_id")
    if len(element_map) != len(elements):
        errors.append("Duplicate element_id")

    def check_box(rect, page_num, context):
        page = page_map.get(page_num)
        if page is None:
            errors.append(f"{context}: missing page {page_num}")
            return
        if len(rect) != 4:
            errors.append(f"{context}: invalid bbox length")
            return
        x0, y0, x1, y1 = rect
        if not (0 <= x0 < x1 <= page["width_pt"] and
                0 <= y0 < y1 <= page["height_pt"]):
            errors.append(f"{context}: bbox outside page")

    for s in spans:
        check_box(s["bbox_pt"], s["page_number"], f"span {s['span_id']}")
    for e in elements:
        eid = e["element_id"]
        check_box(e["bbox_pt"], e["page_number"], f"element {eid}")
        parent = e["parent_id"]
        if parent is not None:
            if parent not in element_map:
                errors.append(f"element {eid}: missing parent {parent}")
            elif parent == eid:
                errors.append(f"element {eid}: self-parent")
            elif element_map[parent]["element_type"] != "heading":
                errors.append(f"element {eid}: parent must be heading")
        for sid in e["source_span_ids"]:
            if sid not in span_map:
                errors.append(f"element {eid}: missing source span {sid}")
            elif span_map[sid]["page_number"] != e["page_number"]:
                errors.append(f"element {eid}: source span {sid} on another page")
        review = e["review"]
        if review["status"] in ("confirmed", "rejected") and not review.get("reviewer"):
            errors.append(f"element {eid}: decision lacks reviewer")
    for eid in element_map:
        visited = set()
        current = eid
        while current in element_map:
            if current in visited:
                errors.append(f"element {eid}: parent cycle")
                break
            visited.add(current)
            parent = element_map[current]["parent_id"]
            if parent is None:
                break
            current = parent
    for relation in data.get("relationships", []):
        for key in ("from_id", "to_id"):
            if relation[key] not in element_map:
                errors.append(f"relationship: unknown {key} {relation[key]}")
    quality = data.get("quality", {})
    if quality.get("review_status") == "reviewed":
        if any(e["review"]["status"] in ("proposed", "unclear") for e in elements):
            errors.append("quality.review_status reviewed, but elements are pending")
    # This flag asserts a separate, performed verification. This tool does
    # not set it; structural validity alone does not prove text losslessness.
    return errors


def validate(data: dict, *, require_jsonschema: bool = True) -> list[str]:
    errors = []
    try:
        import jsonschema
    except ImportError:
        if require_jsonschema:
            raise RuntimeError("Install optional validator: python -m pip install jsonschema")
    else:
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        for error in sorted(validator.iter_errors(data), key=lambda e: str(e.path)):
            errors.append(f"{'/'.join(str(p) for p in error.path) or '$'}: {error.message}")
    if errors:
        return errors
    return validate_structure(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_json", type=Path)
    args = parser.parse_args()
    data = json.loads(args.document_json.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        for error in errors:
            print("ERROR:", error)
        raise SystemExit(1)
    print("Schema and cross-references valid. No content or review approval implied.")


if __name__ == "__main__":
    main()
