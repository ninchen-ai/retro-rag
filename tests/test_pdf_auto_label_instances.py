"""Tests for reference-independent span proposals and duplicate handling."""
import unittest

import pymupdf

from experiments.pdf_auto_label_instances import collect_span_instances


class AutoLabelTests(unittest.TestCase):
    def setUp(self):
        self.doc = pymupdf.open()
        self.page = self.doc.new_page()
        self.figure = [{
            "class_name": "figure",
            "confidence": 0.95,
            "bbox_pdf_points": [50, 50, 550, 350],
        }]

    def tearDown(self):
        self.doc.close()

    def test_separate_identical_labels_remain_two_instances(self):
        self.page.insert_text((100, 100), "System Front", fontname="hebo")
        self.page.insert_text((350, 100), "System Front", fontname="hebo")
        results = collect_span_instances(self.page, self.figure)
        labels = [r for r in results if r["text"] == "System Front"]
        self.assertEqual(len(labels), 2)
        self.assertEqual([r["occurrence"] for r in labels], [1, 2])
        self.assertTrue(all(r["status"] == "REVIEW_REQUIRED" for r in labels))

    def test_overprinted_label_collapses_to_one_geometry(self):
        self.page.insert_text((100, 100), "Added Fan", fontname="hebo")
        self.page.insert_text((102, 102), "Added Fan", fontname="hebo")
        results = collect_span_instances(self.page, self.figure)
        labels = [r for r in results if r["text"] == "Added Fan"]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["duplicate_draws"], 1)

    def test_external_text_is_not_proposed(self):
        self.page.insert_text((100, 100), "Inside", fontname="hebo")
        self.page.insert_text((100, 500), "Outside", fontname="hebo")
        results = collect_span_instances(self.page, self.figure)
        self.assertEqual([x["text"] for x in results], ["Inside"])

    def test_no_regions_no_proposals(self):
        self.page.insert_text((100, 100), "Test")
        self.assertEqual(collect_span_instances(self.page, []), [])


if __name__ == "__main__":
    unittest.main()
