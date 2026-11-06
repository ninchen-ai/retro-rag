"""Schema-v0.1 tests: provenance, ids, links, bounds and review gating."""
import copy
import json
from pathlib import Path
import unittest

from experiments.validate_pdf_structure import validate, validate_structure

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "experiments" / "fixtures" / "pdf_document_structure_v0.1_example.json"
SCHEMA = ROOT / "schemas" / "pdf_document_structure_v0.1.schema.json"


class PdfStructureTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_example_integrity(self):
        self.assertEqual(validate_structure(self.data), [])
        self.assertFalse(self.data["quality"]["text_integrity_checked"])
        self.assertEqual(self.data["elements"][0]["review"]["status"], "proposed")

    def test_page_gap_rejected(self):
        self.data["pages"].pop()
        self.assertTrue(any("enumerate" in e for e in validate_structure(self.data)))

    def test_unknown_span_rejected(self):
        self.data["elements"][0]["source_span_ids"] = ["missing"]
        self.assertTrue(any("missing source span" in e for e in validate_structure(self.data)))

    def test_bbox_out_of_bounds(self):
        self.data["source_spans"][0]["bbox_pt"] = [50, 60, 999, 75]
        self.assertTrue(any("outside page" in e for e in validate_structure(self.data)))

    def test_parent_cycle(self):
        self.data["elements"].append({
            **copy.deepcopy(self.data["elements"][0]),
            "element_id": "e2", "parent_id": "e1"
        })
        self.data["elements"][0]["parent_id"] = "e2"
        self.assertTrue(any("parent cycle" in e for e in validate_structure(self.data)))

    def test_review_without_reviewer_rejected(self):
        self.data["elements"][0]["review"] = {"status": "confirmed"}
        self.assertTrue(any("lacks reviewer" in e for e in validate_structure(self.data)))

    def test_unreviewed_cannot_claim_reviewed(self):
        self.data["quality"]["review_status"] = "reviewed"
        self.assertTrue(any("pending" in e for e in validate_structure(self.data)))

    def test_schema_is_parseable(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "0.1")

    def test_example_matches_jsonschema_if_installed(self):
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("Optional jsonschema package not installed")
        self.assertEqual(validate(self.data), [])

    def test_jsonschema_rejects_missing_provenance_if_installed(self):
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("Optional jsonschema package not installed")
        del self.data["elements"][0]["provenance"]
        self.assertTrue(validate(self.data))


if __name__ == "__main__":
    unittest.main()
