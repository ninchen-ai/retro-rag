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
