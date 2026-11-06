"""Additive v0.2 PDF structure conversion and cross-reference validation.

Never alters the original v0.1 object, PyMuPDF cell matrices, PDF or DB.
No automatic approvals. This module does not decide semantic correctness.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from experiments.validate_pdf_structure import validate as validate_v01

SCHEMA_FILE = (
    Path(__file__).resolve().parents[1] / "schemas"
    / "pdf_document_structure_v0.2.schema.json"
)


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def upgrade_v01(v01):
    """Produce an independent copy, leaving the original JSON unchanged."""
    problems = validate_v01(v01)
    if problems:
        raise ValueError("Invalid v0.1: " + "; ".join(problems[:5]))
    snapshot = copy.deepcopy(v01)
    return {
        "schema_version": "0.2",
        "source_v01": snapshot,
        "source_v01_sha256": canonical_sha256(snapshot),
        "physical_regions": [],
        "logical_elements": [],
        "relationships_v02": [],
        "review_decisions": [],
        "processing_runs": [],
        "quality_v02": {
            "status": "unreviewed",
            "notes": ["Additive v0.2 structure; no semantic approval or RAG ingestion."],
        },
    }


def validate_v02(data, *, require_jsonschema=True):
    """Validate schema, source snapshot, IDs, geometry, provenance and decisions."""
    errors = []
    if require_jsonschema:
        import jsonschema
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        errors.extend(
            f"{'/'.join(map(str, issue.path)) or '$'}: {issue.message}"
            for issue in validator.iter_errors(data)
        )
        if errors:
            return errors
    else:
        if data.get("schema_version") != "0.2":
            return ["Wrong schema_version"]
        for key in ("source_v01", "source_v01_sha256", "physical_regions",
                    "logical_elements", "relationships_v02",
                    "review_decisions", "processing_runs", "quality_v02"):
            if key not in data:
                errors.append(f"Missing {key}")
        if errors:
            return errors

    base = data["source_v01"]
    errors.extend("source_v01: " + err for err in validate_v01(
        base, require_jsonschema=require_jsonschema
    ))
    if canonical_sha256(base) != data["source_v01_sha256"]:
        errors.append("source_v01_sha256 does not match immutable source snapshot")

    source_sha = base["document"]["sha256"]
    page_map = {p["page_number"]: p for p in base["pages"]}
    spans = {s["span_id"] for s in base["source_spans"]}
    # IDs of v0.1 elements and new v0.2 entities live in same namespace.
    known = {e["element_id"] for e in base["elements"]}
    seen = set(known)
    for group, id_field in (
        ("physical_regions", "region_id"),
        ("logical_elements", "logical_id"),
        ("relationships_v02", "relation_id"),
        ("review_decisions", "decision_id"),
        ("processing_runs", "run_id"),
    ):
        for item in data[group]:
            ident = item[id_field]
            if ident in seen:
                errors.append(f"duplicate ID {ident}")
            seen.add(ident)
            if group in ("physical_regions", "logical_elements"):
                known.add(ident)
            if group == "relationships_v02":
                known.add(ident)

    runs = {r["run_id"]: r for r in data["processing_runs"]}
    for run in data["processing_runs"]:
        if run["source_sha256"] != source_sha:
            errors.append(f"run {run['run_id']}: different source PDF hash")

    for region in data["physical_regions"]:
        rid = region["region_id"]
        page = page_map.get(region["page_number"])
        if page is None:
            errors.append(f"region {rid}: unknown page")
        else:
            box = region["bbox_pt"]
            if not all(isinstance(x, (int, float)) and math.isfinite(x)
                       for x in box):
                errors.append(f"region {rid}: nonfinite bbox")
            elif not (0 <= box[0] < box[2] <= page["width_pt"]
                      and 0 <= box[1] < box[3] <= page["height_pt"]):
                errors.append(f"region {rid}: bbox outside page")
        provenance = region["evidence"]
        run = runs.get(provenance["run_id"])
        if run is None:
            errors.append(f"region {rid}: missing processing run")
        elif provenance["method"] != run["method"]:
            errors.append(f"region {rid}: provenance method differs from run")
        for sid in provenance.get("source_span_ids", []):
            if sid not in spans:
                errors.append(f"region {rid}: unknown source span {sid}")
        if region["review"]["status"] != "proposed":
            errors.append(f"region {rid}: v0.2 import may only propose regions")

    for logical in data["logical_elements"]:
        if logical["review"]["status"] != "proposed":
            errors.append(
                f"logical {logical['logical_id']}: v0.2 import may only propose"
            )

    relation_map = {r["relation_id"]: r for r in data["relationships_v02"]}
    for relation in data["relationships_v02"]:
        rid = relation["relation_id"]
        for field in ("from_id", "to_id"):
            if relation[field] not in known:
                errors.append(f"relation {rid}: unknown {field}")
        if relation["from_id"] == relation["to_id"]:
            errors.append(f"relation {rid}: self-reference")
        if relation["review"]["status"] != "proposed":
            errors.append(f"relation {rid}: no automatic decisions")

    decisions = {d["decision_id"]: d for d in data["review_decisions"]}
    for decision in data["review_decisions"]:
        did = decision["decision_id"]
        if decision["target_id"] not in known:
            errors.append(f"decision {did}: unknown target")
        if decision["document_sha256"] != source_sha:
            errors.append(f"decision {did}: source version mismatch")
        try:
            when = datetime.fromisoformat(
                decision["decided_at"].replace("Z", "+00:00")
            )
            if when.tzinfo is None:
                raise ValueError("not timezone-aware")
        except (ValueError, TypeError):
            errors.append(f"decision {did}: invalid decision timestamp")
        parent = decision.get("supersedes_decision_id")
        if parent:
            if parent not in decisions:
                errors.append(f"decision {did}: unknown predecessor")
            elif decisions[parent]["target_id"] != decision["target_id"]:
                errors.append(f"decision {did}: predecessor targets another ID")
            elif parent == did:
                errors.append(f"decision {did}: self-supersedes")
    for did in decisions:
        visited = set()
        cursor = did
        while cursor in decisions:
            if cursor in visited:
                errors.append(f"decision {did}: supersession cycle")
                break
            visited.add(cursor)
            cursor = decisions[cursor].get("supersedes_decision_id")

    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v01-json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.v01_json.resolve() == args.out.resolve():
        parser.error("Output must not overwrite source JSON")
    v01 = json.loads(args.v01_json.read_text(encoding="utf-8"))
    result = upgrade_v01(v01)
    errors = validate_v02(result)
    if errors:
        raise ValueError("v0.2 invalid: " + "; ".join(errors[:10]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("v0.2 valid; preserved source v0.1 fingerprint:",
          result["source_v01_sha256"])
    print("Review only; no DB or Nextcloud writes:", args.out)


if __name__ == "__main__":
    main()
