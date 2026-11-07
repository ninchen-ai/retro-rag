"""Format-independent, fail-closed proposed import contract.

Pure standard-library validation/normalization; no Nextcloud, PDF parser,
embedding client, PostgreSQL, or disk writes. A validated manifest is NOT an
authorization to ingest. Actual authorization requires a separately audited
review process tied to the exact source and unit hashes.
"""
from __future__ import annotations

import hashlib
import json
import re

SHA256 = re.compile(r"^[a-f0-9]{64}$")
KINDS = frozenset({"pdf", "markdown", "other"})
UNIT_KINDS = frozenset({"text", "table", "figure", "metadata"})
STATES = frozenset({"proposed", "confirmed", "rejected", "unclear"})
MAX_UNITS = 100000


def fingerprint(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def validate_contract(manifest):
    """Return all basic structural/semantic errors without mutating input."""
    errors = []
    if not isinstance(manifest, dict):
        return ["Manifest must be an object"]
    required = {"contract_version", "document", "units", "review", "indexing"}
    if set(manifest) != required:
        errors.append("Manifest keys must be exactly: " + ", ".join(sorted(required)))
        return errors
    if manifest["contract_version"] != "0.1":
        errors.append("Unknown contract version")
    doc = manifest["document"]
    if not isinstance(doc, dict):
        errors.append("document must be an object")
        return errors
    doc_fields = {"source_system", "source_id", "source_uri", "source_sha256",
                  "format", "document_kind", "title"}
    if set(doc) != doc_fields:
        errors.append("Invalid document fields")
        return errors
    for field in ("source_system", "source_id", "source_uri", "document_kind", "title"):
        if not isinstance(doc[field], str) or not doc[field].strip():
            errors.append(f"Invalid document.{field}")
    if not isinstance(doc["source_sha256"], str) or not SHA256.fullmatch(doc["source_sha256"]):
        errors.append("Invalid document.source_sha256")
    if doc["format"] not in KINDS:
        errors.append("Unsupported document format")
    units = manifest["units"]
    if not isinstance(units, list) or len(units) > MAX_UNITS:
        errors.append("units must be a bounded array")
        return errors
    used_ids = set()
    for i, unit in enumerate(units):
        prefix = f"units[{i}]"
        if not isinstance(unit, dict):
            errors.append(f"{prefix} must be object")
            continue
        fields = {"unit_id", "unit_kind", "content", "content_sha256", "source",
                  "review_status", "index_disposition", "metadata"}
        if set(unit) != fields:
            errors.append(f"{prefix}: invalid fields")
            continue
        uid = unit["unit_id"]
        if not isinstance(uid, str) or not uid.strip() or uid in used_ids:
            errors.append(f"{prefix}: blank/duplicate unit_id")
        else:
            used_ids.add(uid)
        if unit["unit_kind"] not in UNIT_KINDS:
            errors.append(f"{prefix}: unsupported unit_kind")
        if not isinstance(unit["content"], str) or not unit["content"].strip():
            errors.append(f"{prefix}: missing content")
        elif unit["content_sha256"] != hashlib.sha256(
            unit["content"].encode("utf-8")
        ).hexdigest():
            errors.append(f"{prefix}: content SHA-256 mismatch")
        source = unit["source"]
        if not isinstance(source, dict) or set(source) != {"page_start", "page_end", "source_refs"}:
            errors.append(f"{prefix}: invalid source locator")
        else:
            a, b, refs = source["page_start"], source["page_end"], source["source_refs"]
            if (a is None) != (b is None):
                errors.append(f"{prefix}: incomplete page range")
            elif a is not None and (
                type(a) is not int or type(b) is not int or a < 1 or b < a
            ):
                errors.append(f"{prefix}: invalid page range")
            if not isinstance(refs, list) or any(
                not isinstance(ref, str) or not ref.strip() for ref in refs
            ) or len(set(refs)) != len(refs):
                errors.append(f"{prefix}: invalid source refs")
        if unit["review_status"] not in STATES:
            errors.append(f"{prefix}: invalid review status")
        if unit["index_disposition"] != "blocked":
            errors.append(f"{prefix}: proposed contract must block indexing")
        if not isinstance(unit["metadata"], dict):
            errors.append(f"{prefix}: metadata must be object")
        elif not unit["metadata"].get("source_profile"):
            errors.append(f"{prefix}: missing source profile")
    review = manifest["review"]
    if not isinstance(review, dict) or set(review) != {"status", "decision_refs"}:
        errors.append("Invalid review fields")
    elif review["status"] != "unreviewed" or review["decision_refs"] != []:
        errors.append("Contract is a proposal, not a recorded approval")
    indexing = manifest["indexing"]
    if not isinstance(indexing, dict) or set(indexing) != {
        "allowed", "reason", "overlap_resolved"
    }:
        errors.append("Invalid indexing fields")
    elif (indexing["allowed"] is not False or
          indexing["overlap_resolved"] is not False or
          not isinstance(indexing["reason"], str) or not indexing["reason"].strip()):
        errors.append("Indexing must be explicitly blocked")
    return errors


def propose_contract(document, units, *, reason="Review and deduplication pending"):
    """Create a new immutable-in-practice JSON proposal, rejecting invalid inputs."""
    result = {
        "contract_version": "0.1",
        "document": dict(document),
        "units": [],
        "review": {"status": "unreviewed", "decision_refs": []},
        "indexing": {
            "allowed": False, "reason": reason, "overlap_resolved": False,
        },
    }
    for unit in units:
        content = unit["content"]
        result["units"].append({
            "unit_id": unit["unit_id"],
            "unit_kind": unit["unit_kind"],
            "content": content,
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "source": {
                "page_start": unit.get("page_start"),
                "page_end": unit.get("page_end"),
                "source_refs": list(unit.get("source_refs", [])),
            },
            "review_status": "proposed",
            "index_disposition": "blocked",
            "metadata": dict(unit["metadata"]),
        })
    errors = validate_contract(result)
    if errors:
        raise ValueError("Invalid proposed import contract: " + "; ".join(errors[:10]))
    return result
