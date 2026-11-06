"""Auditable, review-first v0.2 decisions in separate immutable JSON files.

The source v0.2 report is always read-only. There is no automatic
approval, network access, PostgreSQL access or Nextcloud access.
Only an explicit --apply action writes a new standalone decision file.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import uuid

from experiments.pdf_structure_v02 import canonical_sha256, validate_v02

_DECISIONS = {"confirmed", "rejected"}
_GROUPS = (
    ("physical_regions", "region_id"),
    ("logical_elements", "logical_id"),
    ("relationships_v02", "relation_id"),
)
_ID_RE = re.compile(r"^[a-z0-9-]{36}$")


def targets(v02):
    """Reviewable objects only; never review processing runs by accident."""
    found = {}
    for group, id_key in _GROUPS:
        for record in v02[group]:
            key = record[id_key]
            found[key] = record
    return found


def _source_identity(v02):
    return {
        "document_sha256": v02["source_v01"]["document"]["sha256"],
        "source_v01_sha256": v02["source_v01_sha256"],
    }


def _decision_base(v02, target_id):
    entries = targets(v02)
    if target_id not in entries:
        raise ValueError(f"Unknown review target: {target_id}")
    return {
        **_source_identity(v02),
        "target_id": target_id,
        "target_sha256": canonical_sha256(entries[target_id]),
    }


def _all_records(folder):
    """Read and validate every record; corrupted files block all writes."""
    if not folder.exists():
        return []
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Ledger path must be a real directory")
    records = []
    for path in sorted(folder.iterdir()):
        if path.name == ".review.lock":
            continue
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            raise ValueError(f"Unexpected ledger entry: {path.name}")
        if not _ID_RE.fullmatch(path.stem):
            raise ValueError(f"Invalid decision file name: {path.name}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Unparseable decision {path.name}: {exc}") from exc
        if record.get("decision_id") != path.stem:
            raise ValueError(f"Decision ID / filename mismatch: {path.name}")
        records.append(record)
    return records


def inspect_ledger(v02, ledger_dir):
    """Check all records and per-target linear audit chains without mutation."""
    errors = validate_v02(v02)
    if errors:
        raise ValueError("Invalid source v0.2: " + "; ".join(errors[:6]))
    source = _source_identity(v02)
    reviewables = targets(v02)
    records = _all_records(Path(ledger_dir))
    by_id = {}
    by_target = {}
    required = {
        "decision_id", "target_id", "target_sha256",
        "document_sha256", "source_v01_sha256",
        "status", "reviewer", "decided_at", "reason", "previous_decision_id",
    }
    for record in records:
        if not isinstance(record, dict) or set(record) != required:
            raise ValueError("Unexpected/missing fields in decision record")
        did = record["decision_id"]
        if did in by_id:
            raise ValueError(f"Duplicate decision ID: {did}")
        by_id[did] = record
        tid = record["target_id"]
        if tid not in reviewables:
            raise ValueError(f"Unknown review target: {tid}")
        for key, value in source.items():
            if record[key] != value:
                raise ValueError(f"Document version mismatch: {did}")
        if record["target_sha256"] != canonical_sha256(reviewables[tid]):
            raise ValueError(f"Target content changed: {tid}")
        if record["status"] not in _DECISIONS:
            raise ValueError(f"Invalid decision status: {did}")
        if not isinstance(record["reviewer"], str) or not record["reviewer"].strip():
            raise ValueError(f"Missing reviewer: {did}")
        if not isinstance(record["reason"], str) or not record["reason"].strip():
            raise ValueError(f"Missing reason: {did}")
        try:
            when = datetime.fromisoformat(record["decided_at"].replace("Z", "+00:00"))
            if when.tzinfo is None:
                raise ValueError("Naive timestamp")
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid decision timestamp: {did}") from exc
        previous = record["previous_decision_id"]
        if previous is not None and (
            not isinstance(previous, str) or not _ID_RE.fullmatch(previous)
        ):
            raise ValueError(f"Invalid predecessor format: {did}")
        by_target.setdefault(tid, []).append(record)

    current = {}
    for tid, chain in by_target.items():
        beginnings = [r for r in chain if r["previous_decision_id"] is None]
        if len(beginnings) != 1:
            raise ValueError(f"Missing/duplicate chain root: {tid}")
        seen = set()
        pointer = beginnings[0]
        while pointer is not None:
            did = pointer["decision_id"]
            if did in seen:
                raise ValueError(f"Decision chain cycle: {tid}")
            seen.add(did)
            successors = [r for r in chain if r["previous_decision_id"] == did]
            if len(successors) > 1:
                raise ValueError(f"Forked decision chain: {tid}")
            if successors:
                if datetime.fromisoformat(successors[0]["decided_at"].replace(
                    "Z", "+00:00"
                )) < datetime.fromisoformat(pointer["decided_at"].replace(
                    "Z", "+00:00"
                )):
                    raise ValueError(f"Backward decision timestamp: {tid}")
            pointer = successors[0] if successors else None
        if len(seen) != len(chain):
            raise ValueError(f"Disconnected decisions: {tid}")
        head = next(r for r in chain
                    if not any(x["previous_decision_id"] == r["decision_id"]
                               for x in chain))
        current[tid] = head
    return current


def propose(v02, folder, *, target_id, status, reviewer, reason,
            expected_current=None, now=None, decision_id=None):
    """Pure proposal; optimistic concurrency requires explicit expected head."""
    if status not in _DECISIONS:
        raise ValueError("Only explicit confirmed/rejected decisions accepted")
    if not reviewer or not reviewer.strip() or not reason or not reason.strip():
        raise ValueError("Reviewer and justification required")
    current = inspect_ledger(v02, folder)
    head = current.get(target_id)
    existing = head["decision_id"] if head else None
    if existing != expected_current:
        raise ValueError(
            f"Stale review state for {target_id}; current decision: {existing!r}"
        )
    if head and head["status"] == status:
        raise ValueError("Already in that state; unnecessary duplicate decision")
    timestamp = now or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    unique_id = decision_id or str(uuid.uuid4())
    if not _ID_RE.fullmatch(unique_id):
        raise ValueError("Decision ID must be a UUID")
    return {
        "decision_id": unique_id,
        **_decision_base(v02, target_id),
        "status": status,
        "reviewer": reviewer.strip(),
        "decided_at": timestamp,
        "reason": reason.strip(),
        "previous_decision_id": existing,
    }


def apply(v02, folder, *, target_id, status, reviewer, reason,
          expected_current=None):
    """Atomic, fail-closed append under an exclusive Linux flock."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Ledger directory must not be symlink")
    lock_path = folder / ".review.lock"
    if lock_path.is_symlink():
        raise ValueError("Lock file must not be symlink")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        record = propose(
            v02, folder, target_id=target_id, status=status,
            reviewer=reviewer, reason=reason,
            expected_current=expected_current,
        )
        filename = folder / (record["decision_id"] + ".json")
        encoded = (json.dumps(record, ensure_ascii=False, indent=2) + "\n"
                   ).encode("utf-8")
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            inspect_ledger(v02, folder)  # verify final chain
        except BaseException:
            # Never remove the decision on post-write verification failure:
            # it is an auditable record and needs investigation.
            raise
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-json", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--status", required=True, choices=sorted(_DECISIONS))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--expected-current", default=None,
                        help="Explicit predecessor ID for changing a decision")
    parser.add_argument("--apply", action="store_true",
                        help="Explicitly write one immutable decision JSON")
    args = parser.parse_args()
    if args.ledger_dir.resolve() == args.v02_json.resolve():
        parser.error("Ledger cannot replace the source report")
    v02 = json.loads(args.v02_json.read_text(encoding="utf-8"))
    keys = dict(target_id=args.target_id, status=args.status,
                reviewer=args.reviewer, reason=args.reason,
                expected_current=args.expected_current)
    if args.apply:
        result = apply(v02, args.ledger_dir, **keys)
        print("Recorded explicit review:", result["decision_id"])
    else:
        result = propose(v02, args.ledger_dir, **keys)
        print("DRY RUN; no decision file written. Add --apply to commit.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Source v0.2 remains unchanged; no Nextcloud/DB writes.")


if __name__ == "__main__":
    main()
