"""PDF physical-label instance tests: near-duplicates vs distinct positions."""
import unittest

import pymupdf

from experiments.pdf_label_instances import (
    distinct_instances, extract_reference_label_instances,
)


class PDFLabelInstanceTests(unittest.TestCase):
    def test_overlaid_boxes_are_collapsed_but_separate_boxes_remain(self):
        boxes = [
            pymupdf.Rect(102.4, 395, 174.8, 414.3),
            pymupdf.Rect(98, 390.5, 170.4, 409.9),
            pymupdf.Rect(206.9, 395.8, 282.4, 412.1),
        ]
        unique, suppressed = distinct_instances(boxes)
        self.assertEqual(len(unique), 2)
        self.assertEqual(suppressed, 1)

    def test_two_distinct_system_front_instances_are_retained(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((100, 100), "System Front", fontname="hebo")
        page.insert_text((350, 100), "System Front", fontname="hebo")
        reference = {"candidates": [
            {"text": "System Front", "occurrence": 1, "reviewed": True},
            {"text": "System Front", "occurrence": 2, "reviewed": True},
        ]}
        result = extract_reference_label_instances(page, reference, [])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(x["location_status"] == "LOCATED" for x in result))
        self.assertNotEqual(result[0]["bbox_pdf_points"], result[1]["bbox_pdf_points"])
        doc.close()

    def test_count_mismatch_cannot_be_scored_as_located(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((100, 100), "Added Fan", fontname="hebo")
        reference = {"candidates": [
            {"text": "Added Fan", "reviewed": True},
            {"text": "Added Fan", "reviewed": True},
        ]}
        result = extract_reference_label_instances(page, reference, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["location_status"], "COUNT_MISMATCH")
        doc.close()


if __name__ == "__main__":
    unittest.main()
