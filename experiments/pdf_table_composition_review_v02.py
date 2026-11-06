"""Review ledger for derived table-composition proposals; never alters v0.2.

Separate directory from physical/logical v0.2 review ledger: existing
inspect_ledger() must never encounter these different records.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import uuid

from experiments.pdf_table_composition_v02 import validate_proposal

REVIEW_STATES = {"confirmed", "rejected"}


def current_decision(v02, proposal, directory):
    validated = validate_proposal(v02, proposal)
    directory = Path(directory)
    if not directory.exists():
        return None
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Composition ledger must be a real directory")
    records = []
    for path in directory.iterdir():
        if path.name == ".review.lock":
            continue
        if not path.is_file() or path.is_symlink() or path.suffix != ".json":
            raise ValueError(f"Unexpected composition ledger file: {path.name}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ValueError(f"Invalid composition review JSON: {path.name}") from exc
        if not isinstance(record, dict) or record.get("decision_id") + ".json" != path.name:
            raise ValueError("Composition review ID/filename mismatch")
        if record.get("proposal_id") != validated["proposal_id"]:
            raise ValueError("Unexpected proposal in composition ledger")
        if record.get("proposal_sha256") != validated["proposal_sha256"] if "proposal_sha256" in validated else False:
            raise ValueError("Unexpected proposal digest")
        required = {
            "decision_id", "proposal_id", "proposal_sha256", "status",
            "reviewer", "reason", "decided_at", "previous_decision_id",
        }
        if set(record) != required:
            raise ValueError("Unexpected review record fields")
        from experiments.pdf_structure_v02 import canonical_sha256
        if record["proposal_sha256"] != canonical_sha256(validated):
            raise ValueError("Composition proposal changed")
        if record["status"] not in REVIEW_STATES or not record["reviewer"] or not record["reason"]:
            raise ValueError("Invalid composition review")
        if not isinstance(record["reviewer"], str) or not isinstance(record["reason"], str):
            raise ValueError("Invalid reviewer/reason")
        try:
            if datetime.fromisoformat(record["decided_at"].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("Timezone required")
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("Invalid composition decision date") from exc
        if record["previous_decision_id"] is not None and not isinstance(record["previous_decision_id"], str):
            raise ValueError("Invalid predecessor")
        records.append(record)
    ids = [r["decision_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate composition decisions")
    if not records:
        return None
    roots = [r for r in records if r["previous_decision_id"] is None]
    if len(roots) != 1:
        raise ValueError("Broken composition review chain")
    seen = set()
    cursor = roots[0]
    while True:
        ident = cursor["decision_id"]
        if ident in seen:
            raise ValueError("Composition review cycle")
        seen.add(ident)
        children = [r for r in records if r["previous_decision_id"] == ident]
        if len(children) > 1:
            raise ValueError("Forked composition review chain")
        if not children:
            break
        cursor = children[0]
    if len(seen) != len(records):
        raise ValueError("Disconnected composition review records")
    return cursor


def preview(v02, proposal, directory, *, status, reviewer, reason,
            expected_current=None):
    validated = validate_proposal(v02, proposal)
    if status not in REVIEW_STATES:
        raise ValueError("Status must be confirmed or rejected")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Reviewer required")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Reason required")
    if len(reviewer) > 120 or len(reason) > 1000:
        raise ValueError("Reviewer or reason too long")
    head = current_decision(v02, validated, directory)
    last = head["decision_id"] if head else None
    if expected_current != last:
        raise ValueError(f"Stale composition review; current: {last}")
    if head and head["status"] == status:
        raise ValueError("Already in requested state")
    from experiments.pdf_structure_v02 import canonical_sha256
    return {
        "decision_id": str(uuid.uuid4()),
        "proposal_id": validated["proposal_id"],
        "proposal_sha256": canonical_sha256(validated),
        "status": status,
        "reviewer": reviewer.strip(),
        "reason": reason.strip(),
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "previous_decision_id": last,
    }


def commit(v02, proposal, directory, *, status, reviewer, reason,
           expected_current=None, expected_proposal_sha256=None):
    """One append per explicit action; rechecks version and linear history under flock."""
    from experiments.pdf_structure_v02 import canonical_sha256
    validated = validate_proposal(v02, proposal)
    if expected_proposal_sha256 != canonical_sha256(validated):
        raise ValueError("Composition changed since review preview")
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Composition ledger directory must exist")
    lockfile = directory / ".review.lock"
    if lockfile.is_symlink():
        raise ValueError("Ledger lock must not be a symlink")
    with lockfile.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        record = preview(
            v02, validated, directory, status=status, reviewer=reviewer,
            reason=reason, expected_current=expected_current,
        )
        destination = directory / (record["decision_id"] + ".json")
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        current_decision(v02, validated, directory)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-json", required=True, type=Path)
    parser.add_argument("--proposal-json", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--status", required=True, choices=sorted(REVIEW_STATES))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--expected-current")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from experiments.pdf_structure_v02 import canonical_sha256
    v02 = json.loads(args.v02_json.read_text(encoding="utf-8"))
    proposal = json.loads(args.proposal_json.read_text(encoding="utf-8"))
    arguments = {
        "status": args.status, "reviewer": args.reviewer, "reason": args.reason,
        "expected_current": args.expected_current,
    }
    if args.apply:
        arguments["expected_proposal_sha256"] = canonical_sha256(
            validate_proposal(v02, proposal)
        )
        result = commit(v02, proposal, args.ledger_dir, **arguments)
        print("Explicit composition decision saved")
    else:
        result = preview(v02, proposal, args.ledger_dir, **arguments)
        print("DRY RUN: no composition decision written")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
