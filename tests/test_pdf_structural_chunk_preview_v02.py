"""No-loss PDF v0.2 chunk preview bridge; source and review data untouched."""
import copy
import json
from pathlib import Path
import unittest

from experiments.pdf_structure_v02 import upgrade_v01
from experiments.pdf_structural_chunk_preview_v02 import preview

BASE = Path(__file__).resolve().parents[1] / (
    "experiments/fixtures/pdf_document_structure_v0.1_example.json"
)


def fixture():
    base = json.loads(BASE.read_text(encoding="utf-8"))
    assert base["pages"]
    page = base["pages"][0]
    page["text"] = "Title\n1 Introduction\nFirst paragraph.\n1.1 Details\nMore content.\n"
    base["elements"] = [
        {
            "element_id": "test-heading-1",
            "element_type": "heading",
            "page_number": page["page_number"],
            "bbox_pt": [10, 10, 150, 20],
            "title_or_text": "1 Introduction",
            "source_span_ids": [],
            "parent_id": None,
            "provenance": [{"method": "pdf_outline", "evidence": "test anchor"}],
            "review": {"status": "proposed"},
        },
        {
            "element_id": "test-heading-2",
            "element_type": "heading",
            "page_number": page["page_number"],
            "bbox_pt": [10, 30, 150, 40],
            "title_or_text": "1.1 Details",
            "source_span_ids": [],
            "parent_id": "test-heading-1",
            "provenance": [{"method": "pdf_outline", "evidence": "test anchor"}],
            "review": {"status": "proposed"},
        },
    ]
    return upgrade_v01(base)


class PdfStructuralPreviewTests(unittest.TestCase):
    def setUp(self):
        self.v02 = fixture()
        self.original = copy.deepcopy(self.v02)

    def test_no_selected_headings_keeps_every_character(self):
        result = preview(self.v02, max_chars=9)
        for page in self.v02["source_v01"]["pages"]:
            got = "".join(x["content"] for x in result["chunks"]
                          if x["page_number"] == page["page_number"])
            self.assertEqual(got, page["text"])
        self.assertTrue(result["quality"]["lossless_page_text_reconstruction"])
        self.assertFalse(result["quality"]["tables_integrated"])
        self.assertEqual(self.v02, self.original)

    def test_explicit_headings_split_same_page_and_keep_hierarchy(self):
        result = preview(
            self.v02,
            selected_heading_ids=["test-heading-1", "test-heading-2"],
            max_chars=100,
        )
        page_chunks = [x for x in result["chunks"] if x["page_number"] == 1]
        self.assertEqual(page_chunks[0]["heading_id"], None)
        self.assertEqual(page_chunks[1]["heading_path"], ["1 Introduction"])
        self.assertEqual(page_chunks[2]["heading_path"],
                         ["1 Introduction", "1.1 Details"])
        self.assertEqual(
            "".join(x["content"] for x in page_chunks),
            self.v02["source_v01"]["pages"][0]["text"],
        )
        self.assertFalse(result["selected_headings_are_approved"])
        self.assertEqual(self.v02, self.original)

    def test_unknown_anchor_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            preview(self.v02, selected_heading_ids=["not-real"])

    def test_duplicate_anchor_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            preview(self.v02, selected_heading_ids=["test-heading-1"] * 2)

    def test_ambiguous_exact_match_fails_closed(self):
        self.v02["source_v01"]["pages"][0]["text"] += "1 Introduction\n"
        from experiments.pdf_structure_v02 import canonical_sha256
        self.v02["source_v01_sha256"] = canonical_sha256(self.v02["source_v01"])
        with self.assertRaisesRegex(ValueError, "matched 2"):
            preview(self.v02, selected_heading_ids=["test-heading-1"])

    def test_no_text_match_does_not_fake_boundary(self):
        self.v02["source_v01"]["elements"][0]["title_or_text"] = "Not a line"
        from experiments.pdf_structure_v02 import canonical_sha256
        self.v02["source_v01_sha256"] = canonical_sha256(self.v02["source_v01"])
        with self.assertRaisesRegex(ValueError, "matched 0"):
            preview(self.v02, selected_heading_ids=["test-heading-1"])

    def test_rejected_heading_cannot_be_selected(self):
        self.v02["source_v01"]["elements"][0]["review"] = {
            "status": "rejected",
            "reviewer": "test-reviewer",
            "reason": "Rejected heading in test fixture",
        }
        from experiments.pdf_structure_v02 import canonical_sha256
        self.v02["source_v01_sha256"] = canonical_sha256(self.v02["source_v01"])
        with self.assertRaisesRegex(ValueError, "Rejected"):
            preview(self.v02, selected_heading_ids=["test-heading-1"])

    def test_incomplete_review_metadata_is_rejected(self):
        self.v02["source_v01"]["elements"][0]["review"]["status"] = "rejected"
        from experiments.pdf_structure_v02 import canonical_sha256
        self.v02["source_v01_sha256"] = canonical_sha256(self.v02["source_v01"])
        with self.assertRaisesRegex(ValueError, "decision lacks reviewer"):
            preview(self.v02, selected_heading_ids=["test-heading-1"])

    def test_invalid_snapshot_is_rejected(self):
        self.v02["source_v01_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Invalid v0.2"):
            preview(self.v02)

    def test_empty_whitespace_page_not_discarded(self):
        page = self.v02["source_v01"]["pages"][1]
        page["text"] = " \n\t\n"
        from experiments.pdf_structure_v02 import canonical_sha256
        self.v02["source_v01_sha256"] = canonical_sha256(self.v02["source_v01"])
        result = preview(self.v02, max_chars=4)
        self.assertEqual("".join(c["content"] for c in result["chunks"]
                                 if c["page_number"] == page["page_number"]),
                         " \n\t\n")


if __name__ == "__main__":
    unittest.main()
