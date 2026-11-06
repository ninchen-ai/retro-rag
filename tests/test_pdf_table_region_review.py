"""Deterministic tests for geometric outline/table-region review."""
import copy
import unittest

from experiments.pdf_table_region_review import (
    associate_table_anchors, layout_regions_in_pdf,
)


def doc():
    return {
        "pages": [{"page_number": 1, "width_pt": 612.0,
                   "height_pt": 792.0, "rotation": 0}],
        "elements": [{
            "element_id": "outline-1",
            "element_type": "table",
            "page_number": 1,
            "bbox_pt": [80, 200, 420, 215],
            "title_or_text": "Table 2–3. USBLEGSUP",
            "review": {"status": "proposed"},
            "provenance": [{"method": "pdf_outline",
                            "evidence": "locator=NEAR_TARGET; original"}],
        }],
    }


def region(x0=75, y0=225, x1=450, y1=600):
    return {"class_name": "table", "bbox_pdf_points": [x0, y0, x1, y1]}


class TableRegionReviewTests(unittest.TestCase):
    def test_caption_matches_nearby_table_below(self):
        data = doc()
        before = copy.deepcopy(data)
        result = associate_table_anchors(data, [region()], page_number=1)
        self.assertEqual(data, before)
        self.assertEqual(result["anchor_matches"][0]["status"], "ONE_CANDIDATE")
        self.assertEqual(result["anchor_matches"][0]["candidate_regions"][0]["gap_pt"], 10)
        self.assertFalse(result["approved"])
        self.assertFalse(result["anchor_matches"][0]["approved"])

    def test_table_above_label_does_not_match(self):
        result = associate_table_anchors(doc(), [region(y0=100, y1=190)], page_number=1)
        self.assertEqual(result["anchor_matches"][0]["status"], "NO_CANDIDATE")

    def test_distant_table_does_not_match(self):
        result = associate_table_anchors(doc(), [region(y0=275)], page_number=1)
        self.assertEqual(result["anchor_matches"][0]["status"], "NO_CANDIDATE")

    def test_unrelated_column_does_not_match(self):
        result = associate_table_anchors(doc(), [region(x0=500, x1=600)], page_number=1)
        self.assertEqual(result["anchor_matches"][0]["status"], "NO_CANDIDATE")

    def test_multiple_tables_near_same_title_stay_ambiguous(self):
        result = associate_table_anchors(doc(), [
            region(x0=75, x1=245), region(x0=240, x1=460)
        ], page_number=1)
        self.assertEqual(result["anchor_matches"][0]["status"], "MULTIPLE_CANDIDATES")

    def test_same_region_claimed_by_two_titles_is_conflict(self):
        data = doc()
        other = copy.deepcopy(data["elements"][0])
        other["element_id"] = "outline-2"
        other["bbox_pt"] = [90, 202, 380, 216]
        data["elements"].append(other)
        result = associate_table_anchors(data, [region()], page_number=1)
        self.assertEqual([m["status"] for m in result["anchor_matches"]],
                         ["SHARED_REGION_CONFLICT", "SHARED_REGION_CONFLICT"])

    def test_unclear_anchor_not_used_to_claim_region(self):
        data = doc()
        data["elements"][0]["review"]["status"] = "unclear"
        result = associate_table_anchors(data, [region()], page_number=1)
        self.assertEqual(result["anchor_matches"], [])

    def test_pixel_to_pdf_converts_correctly(self):
        layout = {"detections": [{
            "class_name": "table", "bbox_pixels": [150, 450, 900, 1200],
            "confidence": 0.82,
        }]}
        regions = layout_regions_in_pdf(
            layout, 1224, 1584, doc()["pages"][0]
        )
        self.assertEqual(regions[0]["bbox_pdf_points"],
                         [75.0, 225.0, 450.0, 600.0])

    def test_rotated_page_fails_closed(self):
        page = doc()["pages"][0]
        page["rotation"] = 90
        with self.assertRaisesRegex(ValueError, "Rotated"):
            layout_regions_in_pdf({"detections": []}, 1224, 1584, page)


if __name__ == "__main__":
    unittest.main()
