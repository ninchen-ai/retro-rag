"""Composition decisions: separate immutable files, no silent write."""
import copy
from pathlib import Path
import tempfile
import unittest

from experiments.pdf_table_composition_v02 import propose_composition
from experiments.pdf_table_composition_review_v02 import (
    current_decision, preview, commit,
)
from experiments.pdf_structure_v02 import canonical_sha256
from test_pdf_table_composition_v02 import fixture


class CompositionDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "composition-reviews"
        self.ledger.mkdir()
        self.data, logical, regions = fixture()
        self.original = copy.deepcopy(self.data)
        self.proposal = propose_composition(
            self.data, logical_id=logical, source_region_ids=regions
        )
        self.args = {
            "status": "confirmed", "reviewer": "nina",
            "reason": "Two blocks are one continued table",
        }

    def test_preview_is_read_only(self):
        record = preview(self.data, self.proposal, self.ledger, **self.args)
        self.assertEqual(record["status"], "confirmed")
        self.assertEqual(list(self.ledger.glob("*.json")), [])
        self.assertEqual(self.data, self.original)

    def test_explicit_commit_creates_single_decision(self):
        result = commit(
            self.data, self.proposal, self.ledger,
            expected_proposal_sha256=canonical_sha256(self.proposal),
            **self.args,
        )
        self.assertEqual(
            current_decision(self.data, self.proposal, self.ledger),
            result,
        )
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)
        self.assertEqual(self.data, self.original)

    def test_no_commit_without_matching_proposal_fingerprint(self):
        with self.assertRaisesRegex(ValueError, "changed"):
            commit(self.data, self.proposal, self.ledger,
                   expected_proposal_sha256="f" * 64, **self.args)
        self.assertFalse(list(self.ledger.glob("*.json")))

    def test_duplicate_and_stale_decisions_rejected(self):
        first = commit(
            self.data, self.proposal, self.ledger,
            expected_proposal_sha256=canonical_sha256(self.proposal),
            **self.args,
        )
        with self.assertRaisesRegex(ValueError, "Stale"):
            commit(self.data, self.proposal, self.ledger,
                   expected_proposal_sha256=canonical_sha256(self.proposal),
                   **self.args)
        with self.assertRaisesRegex(ValueError, "Already"):
            preview(self.data, self.proposal, self.ledger,
                    expected_current=first["decision_id"], **self.args)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)

    def test_new_verdict_chains_original(self):
        first = commit(
            self.data, self.proposal, self.ledger,
            expected_proposal_sha256=canonical_sha256(self.proposal),
            **self.args,
        )
        second = commit(
            self.data, self.proposal, self.ledger,
            expected_proposal_sha256=canonical_sha256(self.proposal),
            expected_current=first["decision_id"],
            status="rejected", reviewer="nina", reason="Further check failed",
        )
        self.assertEqual(second["previous_decision_id"],
                         first["decision_id"])
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 2)

    def test_altered_proposal_rejected(self):
        invalid = copy.deepcopy(self.proposal)
        invalid["preview_rows"][-1]["cells"][0] = "forged"
        with self.assertRaisesRegex(ValueError, "altered"):
            preview(self.data, invalid, self.ledger, **self.args)


if __name__ == "__main__":
    unittest.main()
