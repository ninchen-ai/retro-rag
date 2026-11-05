"""Read-only quality report tests: checks and issue provenance."""
import json
import unittest
import pymupdf

from scripts.pdf_quality_report import build_quality_report, format_quality_json


class QualityReportTests(unittest.TestCase):
    def test_numbered_report_is_never_approved(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "1 Introduction and Overview", fontsize=18, fontname="hebo")
        page.insert_text((54, 120), "1.1 Overview", fontsize=14, fontname="hebo")
        page = doc.new_page()
        page.insert_text((54, 80), "2 New Features", fontsize=18, fontname="hebo")
        raw = doc.tobytes()
        doc.close()
        report = build_quality_report(raw, "fixture.pdf")
        self.assertFalse(report["approved"])
        self.assertTrue(report["lossless"])
        self.assertEqual(report["missing_parent_sections"], [])
        self.assertEqual(report["heading_candidates"], 3)
        self.assertEqual(json.loads(format_quality_json(report))["filename"], "fixture.pdf")

    def test_optional_layout_evidence_preserves_existing_issues(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "1 Introduction and Overview", fontsize=18, fontname="hebo")
        raw = doc.tobytes()
        doc.close()
        before = build_quality_report(raw, "fixture.pdf")
        evidence = {
            "pdf_page": 1,
            "approved": False,
            "heading_candidates": [{
                "heading": "1 Introduction and Overview",
                "status": "REVIEW_REQUIRED",
                "review_reason": "POSSIBLY_FIGURE_ASSOCIATED",
                "nearby_regions": [{"class_name": "figure", "vertical_gap_pt": 14.9}],
            }],
        }
        after = build_quality_report(raw, "fixture.pdf", layout_review=evidence)
        self.assertEqual(before["issues"], after["issues"])
        self.assertEqual(before["chunk_count"], after["chunk_count"])
        self.assertEqual(before["lossless"], after["lossless"])
        self.assertNotIn("layout_review", before)
        self.assertFalse(after["layout_review"]["approved"])
        self.assertEqual(after["layout_review"]["heading_candidates"][0]["review_reason"],
                         "POSSIBLY_FIGURE_ASSOCIATED")

    def test_approved_layout_evidence_is_rejected(self):
        doc = pymupdf.open()
        doc.new_page()
        raw = doc.tobytes()
        doc.close()
        with self.assertRaises(ValueError):
            build_quality_report(raw, "fixture.pdf", layout_review={
                "approved": True, "pdf_page": 1, "heading_candidates": []
            })

    def test_missing_parent_is_reported(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "1 Introduction and Overview", fontsize=18, fontname="hebo")
        page.insert_text((54, 120), "1.2.1 Hardware Requirements", fontsize=14, fontname="hebo")
        raw = doc.tobytes()
        doc.close()
        report = build_quality_report(raw, "missing-parent.pdf")
        self.assertEqual(report["missing_parent_sections"], ["1.2"])
        self.assertTrue(report["lossless"])


if __name__ == "__main__":
    unittest.main()
