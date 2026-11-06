"""Regression tests for separate, explicit, immutable PDF review decisions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.pdf_review_decisions_v02 import (
    apply, inspect_ledger, propose,
)
from experiments.pdf_structure_v02_assemble import assemble
from test_pdf_structure_v02 import synthetic_reports

EXAMPLE = (Path(__file__).resolve().parents[1]
           / "experiments/fixtures/pdf_document_structure_v0.1_example.json")


def source_report():
    base = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return assemble(base, *synthetic_reports(base))


class ReviewDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "review-ledger"
        self.v02 = source_report()
        self.original = copy.deepcopy(self.v02)
        self.target_id = self.v02["logical_elements"][0]["logical_id"]
        self.kwargs = dict(
            target_id=self.target_id, status="confirmed",
            reviewer="human-reviewer", reason="Compared with original PDF",
        )

    def test_dry_run_makes_no_files(self):
        proposal = propose(self.v02, self.folder, **self.kwargs)
        self.assertEqual(proposal["status"], "confirmed")
        self.assertFalse(self.folder.exists())
        self.assertEqual(self.v02, self.original)

    def test_explicit_apply_creates_individual_json(self):
        decision = apply(self.v02, self.folder, **self.kwargs)
        path = self.folder / (decision["decision_id"] + ".json")
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), decision)
        self.assertEqual(inspect_ledger(self.v02, self.folder)[self.target_id], decision)
        self.assertEqual(self.v02, self.original)
        self.assertEqual(self.v02["review_decisions"], [])

    def test_second_same_status_is_rejected(self):
        first = apply(self.v02, self.folder, **self.kwargs)
        with self.assertRaisesRegex(ValueError, "Stale"):
            apply(self.v02, self.folder, **self.kwargs)
        with self.assertRaisesRegex(ValueError, "Already"):
            apply(self.v02, self.folder, expected_current=first["decision_id"],
                  **self.kwargs)
        self.assertEqual(len(list(self.folder.glob("*.json"))), 1)

    def test_status_change_requires_predecessor(self):
        first = apply(self.v02, self.folder, **self.kwargs)
        with self.assertRaisesRegex(ValueError, "Stale"):
            apply(self.v02, self.folder, target_id=self.target_id,
                  status="rejected", reviewer="human",
                  reason="second review changed verdict")
        newer = apply(self.v02, self.folder, target_id=self.target_id,
                      status="rejected", reviewer="human",
                      reason="second review changed verdict",
                      expected_current=first["decision_id"])
        self.assertEqual(newer["previous_decision_id"], first["decision_id"])
        self.assertEqual(len(list(self.folder.glob("*.json"))), 2)

    def test_missing_reviewer_or_reason_rejected(self):
        with self.assertRaisesRegex(ValueError, "Reviewer"):
            propose(self.v02, self.folder, **{**self.kwargs, "reason": ""})

    def test_unknown_target_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown review target"):
            propose(self.v02, self.folder,
                    **{**self.kwargs, "target_id": "unknown"})

    def test_wrong_document_version_fails_closed(self):
        apply(self.v02, self.folder, **self.kwargs)
        changed = copy.deepcopy(self.v02)
        changed["source_v01"]["document"]["sha256"] = "b" * 64
        # Re-sign just to test the document-version mismatch; run hashes
        # would still be rejected by the v0.2 validator, as intended.
        from experiments.pdf_structure_v02 import canonical_sha256
        changed["source_v01_sha256"] = canonical_sha256(changed["source_v01"])
        with self.assertRaises(ValueError):
            inspect_ledger(changed, self.folder)

    def test_modified_target_fails_closed(self):
        apply(self.v02, self.folder, **self.kwargs)
        changed = copy.deepcopy(self.v02)
        changed["logical_elements"][0]["label"] = "different"
        with self.assertRaisesRegex(ValueError, "Target content changed"):
            inspect_ledger(changed, self.folder)

    def test_corrupted_record_fails_closed(self):
        decision = apply(self.v02, self.folder, **self.kwargs)
        path = self.folder / (decision["decision_id"] + ".json")
        path.write_text("not-json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unparseable"):
            inspect_ledger(self.v02, self.folder)

    def test_duplicate_roots_refused(self):
        first = apply(self.v02, self.folder, **self.kwargs)
        second = copy.deepcopy(first)
        second["decision_id"] = "bb000000-0000-4000-8000-000000000001"
        (self.folder / (second["decision_id"] + ".json")).write_text(
            json.dumps(second), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "root"):
            inspect_ledger(self.v02, self.folder)

    def test_different_targets_can_be_reviewed_independently(self):
        apply(self.v02, self.folder, **self.kwargs)
        another = self.v02["physical_regions"][0]["region_id"]
        apply(self.v02, self.folder, target_id=another, status="rejected",
              reviewer="human", reason="Detector class is wrong")
        self.assertEqual(len(inspect_ledger(self.v02, self.folder)), 2)

    def test_review_is_not_written_to_v02_json(self):
        apply(self.v02, self.folder, **self.kwargs)
        self.assertEqual(self.v02, self.original)
        self.assertEqual(self.v02["logical_elements"][0]["review"]["status"], "proposed")


if __name__ == "__main__":
    unittest.main()
