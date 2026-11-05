"""Tests for read-only geometry integration with detector output."""
import unittest
import pymupdf

from experiments.pdf_layout_joint_review import (
    pixel_box_to_pdf, figure_proximity, locate_heading
)


class JointLayoutReviewTests(unittest.TestCase):
    def test_image_pixels_convert_to_pdf_points(self):
        self.assertEqual(
            pixel_box_to_pdf([0, 0, 612, 792], 612, 792, 612, 792),
            (0.0, 0.0, 612.0, 792.0)
        )
        self.assertEqual(
            pixel_box_to_pdf([0, 0, 1275, 1650], 612, 792, 1275, 1650),
            (0.0, 0.0, 612.0, 792.0)
        )

    def test_invalid_rectangle_rejected(self):
        with self.assertRaises(ValueError):
            pixel_box_to_pdf([0, 0, 9999, 100], 612, 792, 1275, 1650)

    def test_figure_below_candidate_is_review_hint_not_decision(self):
        regions = [{
            "class_name": "figure",
            "confidence": 0.8,
            "bbox_pdf_points": [220, 495, 390, 700]
        }]
        self.assertEqual(
            figure_proximity((120, 465, 220, 483), regions)[0]["vertical_gap_pt"],
            12
        )
        self.assertEqual(
            figure_proximity((120, 80, 400, 100), regions),
            []
        )

    def test_repeated_term_can_be_located_by_exact_visual_line(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "ADD-IN CARD", fontsize=12, fontname="hebo")
        page.insert_text((54, 180), "ADD-IN CARD AND COMPONENTS", fontsize=11)
        # Search matches twice; only first line is exact candidate.
        rect = locate_heading(page, "ADD-IN CARD")
        self.assertIsNotNone(rect)
        self.assertLess(rect.y0, 100)
        doc.close()


if __name__ == "__main__":
    unittest.main()
