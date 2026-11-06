"""Review-only import manifest: decisions, text preservation, dedup guard."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.pdf_import_manifest_v02 import (
    build_manifest, heading_alignment_audit,
)
from experiments.pdf_table_composition_v02 import propose_composition
from experiments.pdf_table_composition_review_v02 import commit
from experiments.pdf_structure_v02 import canonical_sha256
from test_pdf_table_composition_v02 import fixture


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.main_ledger = Path(self.tmp.name) / "reviews"
        self.comp_ledger = Path(self.tmp.name) / "compositions"
        self.main_ledger.mkdir()
        self.comp_ledger.mkdir()
        self.v02, logical, regions = fixture()
        self.proposal = propose_composition(
            self.v02, logical_id=logical, source_region_ids=regions
        )
        self.original = copy.deepcopy(self.v02)

    def build(self):
        return build_manifest(
            self.v02, review_ledger_dir=self.main_ledger,
            composition_proposal=self.proposal,
            composition_ledger_dir=self.comp_ledger, max_chars=30,
        )

    def test_without_confirmed_composition_stays_blocked(self):
        manifest = self.build()
        self.assertFalse(manifest["import_approved"])
        self.assertFalse(manifest["db_writes"])
        self.assertFalse(manifest["embedding_calls"])
        self.assertTrue(manifest["text_reconstruction_verified"])
        self.assertEqual(manifest["table_composition_decision_status"], "proposed")
        self.assertIn(
            "COMPOSITION_NOT_CONFIRMED",
            {b["code"] for b in manifest["blockers"]},
        )
        self.assertEqual(self.v02, self.original)
        self.assertEqual(list(self.main_ledger.glob("*.json")), [])
        self.assertEqual(list(self.comp_ledger.glob("*.json")), [])

    def test_confirmed_composition_does_not_approve_import_or_logical(self):
        committed = commit(
            self.v02, self.proposal, self.comp_ledger,
            status="confirmed", reviewer="nina", reason="Verified visually",
            expected_proposal_sha256=canonical_sha256(self.proposal),
        )
        manifest = self.build()
        self.assertEqual(manifest["table_composition_decision_status"], "confirmed")
        table = next(x for x in manifest["entries"]
                     if x["unit_type"] == "logical_table_preview")
        self.assertEqual(table["composition_decision_id"], committed["decision_id"])
        self.assertEqual(table["logical_element_status"], "proposed")
        self.assertEqual(table["header_cells"], ["Address", "IDSEL"])
        self.assertEqual(table["data_rows"], [
            ["00000", "0001"], ["00111", "1000"],
            ["01000", "00010000"], ["1xxxx", "00000000"],
        ])
        self.assertEqual(table["rows_with_provenance"][-1]["row_index"], 2)
        self.assertEqual(
            table["index_disposition"], "blocked_possible_table_duplication"
        )
        self.assertIn("LOGICAL_TABLE_NOT_CONFIRMED",
                      {b["code"] for b in manifest["blockers"]})
        self.assertFalse(manifest["import_approved"])
        self.assertEqual(self.v02, self.original)

    def test_table_page_text_is_preserved_but_not_indexable(self):
        manifest = self.build()
        pno = self.proposal["page_number"]
        texts = [c for c in manifest["entries"]
                 if c["unit_type"] == "source_page_text"]
        self.assertEqual(
            "".join(x["content"] for x in texts if x["page_number"] == pno),
            self.v02["source_v01"]["pages"][pno - 1]["text"],
        )
        self.assertTrue(all(
            x["index_disposition"] == "blocked_possible_table_duplication"
            for x in texts if x["page_number"] == pno
        ))
        self.assertTrue(all(
            x["index_disposition"] == "not_approved"
            for x in texts if x["page_number"] != pno
        ))

    def test_wrong_source_pdf_fails_closed(self):
        bad = copy.deepcopy(self.v02)
        bad["source_v01_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            build_manifest(
                bad, review_ledger_dir=self.main_ledger,
                composition_proposal=self.proposal,
                composition_ledger_dir=self.comp_ledger,
            )

    def test_tampered_composition_fails_closed(self):
        bad = copy.deepcopy(self.proposal)
        bad["preview_rows"][1]["cells"][1] = "forged"
        with self.assertRaisesRegex(ValueError, "altered"):
            build_manifest(
                self.v02, review_ledger_dir=self.main_ledger,
                composition_proposal=bad,
                composition_ledger_dir=self.comp_ledger,
            )

    def test_outline_audit_never_approves(self):
        audit = heading_alignment_audit(self.v02)
        self.assertEqual(
            audit["headings_total"],
            len([e for e in self.v02["source_v01"]["elements"]
                 if e["element_type"] == "heading"]),
        )
        self.assertFalse(audit["any_boundaries_approved"])
        self.assertEqual(self.v02, self.original)


if __name__ == "__main__":
    unittest.main()
