"""Document-wide v0.2 merge tests: preserve original and fail closed."""
import copy
import json
from pathlib import Path
import unittest

from experiments.pdf_structure_v02 import (
    canonical_sha256, upgrade_v01, validate_v02,
)
from experiments.pdf_structure_v02_assemble import assemble
from experiments.pdf_structure_v02_merge import merge_v02
from tests.test_pdf_structure_v02 import synthetic_reports

EXAMPLE = (
    Path(__file__).resolve().parents[1] /
    "experiments/fixtures/pdf_document_structure_v0.1_example.json"
)


def base_structure():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def one_page(base, page_number):
    layout, quality, captions, conflicts = copy.deepcopy(
        synthetic_reports(base)
    )
    name = f"page{page_number}.png"
    layout["source_image"] = name
    quality["source_image"] = name
    quality["page_number"] = page_number
    captions["source_image"] = name
    captions["page_number"] = page_number
    conflicts["source_image"] = name
    conflicts["page_number"] = page_number
    return assemble(base, layout, quality, captions, conflicts)


class PdfStructureV02MergeTests(unittest.TestCase):
    def setUp(self):
        base = base_structure()
        self.a = one_page(base, 1)
        self.b = one_page(base, 2)

    def test_two_pages_keep_original_and_both_raw_matrices(self):
        originals = copy.deepcopy((self.a, self.b))
        result = merge_v02([self.a, self.b])
        self.assertEqual((self.a, self.b), originals)
        self.assertEqual(result["source_v01"], self.a["source_v01"])
        self.assertEqual(result["source_v01_sha256"],
                         canonical_sha256(self.a["source_v01"]))
        self.assertEqual(validate_v02(result), [])
        self.assertEqual(len(result["physical_regions"]), 2 * len(
            self.a["physical_regions"]))
        matrices = [r["raw_cells"] for r in result["physical_regions"]
                    if "raw_cells" in r]
        self.assertEqual(len(matrices), 4)
        self.assertIsNone(matrices[0][0][1])
        self.assertIsNone(matrices[2][0][1])
        self.assertTrue(all(x["review"]["status"] == "proposed"
                            for x in result["relationships_v02"]))

    def test_merge_order_independent(self):
        self.assertEqual(
            merge_v02([self.a, self.b]),
            merge_v02([self.b, self.a]),
        )

    def test_duplicate_page_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Duplicate page"):
            merge_v02([self.a, copy.deepcopy(self.a)])

    def test_different_source_snapshot_refused(self):
        other_base = base_structure()
        other_base["pages"][0]["text"] = "Another snapshot"
        other = one_page(other_base, 2)
        with self.assertRaisesRegex(ValueError, "different v0.1"):
            merge_v02([self.a, other])

    def test_other_source_pdf_hash_refused(self):
        other_base = base_structure()
        other_base["document"]["sha256"] = "b" * 64
        other = one_page(other_base, 2)
        with self.assertRaisesRegex(ValueError, "different v0.1"):
            merge_v02([self.a, other])

    def test_duplicate_ids_across_pages_refused(self):
        other = copy.deepcopy(self.b)
        other["physical_regions"][0]["region_id"] = (
            self.a["physical_regions"][0]["region_id"]
        )
        # Inputs remain individually valid; merged IDs must be disjoint.
        self.assertEqual(validate_v02(other), [])
        with self.assertRaisesRegex(ValueError, "Duplicate ID"):
            merge_v02([self.a, other])

    def test_edited_original_snapshot_caught(self):
        other = copy.deepcopy(self.b)
        other["source_v01"]["pages"][0]["text"] = "tampered"
        with self.assertRaisesRegex(ValueError, "invalid"):
            merge_v02([self.a, other])

    def test_wrong_processing_run_page_refused(self):
        other = copy.deepcopy(self.b)
        other["processing_runs"][0]["parameters"]["page"] = 1
        with self.assertRaisesRegex(ValueError, "exactly one page"):
            merge_v02([self.a, other])

    def test_wrong_region_page_refused(self):
        other = copy.deepcopy(self.b)
        other["physical_regions"][0]["page_number"] = 1
        self.assertEqual(validate_v02(other), [])
        with self.assertRaisesRegex(ValueError, "Region page"):
            merge_v02([self.a, other])

    def test_no_reports_refused(self):
        with self.assertRaises(ValueError):
            merge_v02([])

    def test_blank_upgrade_is_not_page_report(self):
        blank = upgrade_v01(base_structure())
        with self.assertRaisesRegex(ValueError, "no page-scoped"):
            merge_v02([blank])

    def test_decision_preserved_without_mutating_proposal(self):
        other = copy.deepcopy(self.b)
        other["review_decisions"].append({
            "decision_id": "review-p2",
            "target_id": other["logical_elements"][0]["logical_id"],
            "status": "confirmed",
            "reviewer": "test reviewer",
            "reason": "Checked against original",
            "decided_at": "2026-11-06T11:00:00+01:00",
            "document_sha256": other["source_v01"]["document"]["sha256"],
        })
        merged = merge_v02([self.a, other])
        self.assertEqual(len(merged["review_decisions"]), 1)
        self.assertTrue(all(item["review"]["status"] == "proposed"
                            for item in merged["logical_elements"]))


if __name__ == "__main__":
    unittest.main()
