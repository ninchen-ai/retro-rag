"""Table-quality review: independent geometry and structural checks."""
import copy
import unittest

from experiments.pdf_table_quality_review import (
    bbox_iou, evaluate_tables, inspect_cells,
)


def outline():
    return {
        "pages": [{"page_number": 1}],
        "elements": [{
            "element_id": "outline-00012",
            "element_type": "table",
            "page_number": 1,
            "bbox_pt": [80, 200, 420, 215],
            "title_or_text": "Table 2–3. USBLEGSUP",
            "review": {"status": "proposed"},
            "provenance": [{"evidence": "locator=NEAR_TARGET; review"}],
        }],
    }


def detector(box=None):
    return [{"class_name": "table",
             "bbox_pdf_points": box or [75, 225, 450, 600],
             "confidence": 0.98}]


def extracted(box=None, cells=None):
    return [{
        "bbox_pt": box or [76, 226, 449, 599],
        "rows": 2,
        "columns": 2,
        "cells": cells if cells is not None else [
            ["Bit", "Description"], ["24", "HC OS Owned Semaphore"]
        ],
    }]


class QualityReviewTests(unittest.TestCase):
    def test_iou_same_box_is_one(self):
        self.assertEqual(bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]), 1)

    def test_iou_disjoint_is_zero(self):
        self.assertEqual(bbox_iou([0, 0, 10, 10], [20, 20, 30, 30]), 0)

    def test_iou_rejects_bad_geometry(self):
        with self.assertRaises(ValueError):
            bbox_iou([0, 0, 0, 10], [0, 0, 10, 10])

    def test_ehci_like_caption_links_to_extracted_cells(self):
        data = outline()
        det = detector()
        tables = extracted()
        before = (copy.deepcopy(data), copy.deepcopy(det), copy.deepcopy(tables))
        result = evaluate_tables(data, det, tables, page_number=1)
        self.assertEqual((data, det, tables), before)
        self.assertFalse(result["approved"])
        self.assertEqual(result["detector_to_pymupdf"][0]["status"], "ONE_CANDIDATE")
        self.assertEqual(result["caption_to_extracted_table"][0]["pymupdf_table_index"], 0)
        self.assertEqual(result["pymupdf_tables"][0]["cells"][1][0], "24")
        self.assertEqual(result["pymupdf_tables"][0]["cell_warnings"], [])

    def test_no_overlap_keeps_table_unlinked(self):
        result = evaluate_tables(
            outline(), detector(), extracted([500, 226, 600, 600]), page_number=1
        )
        self.assertEqual(result["detector_to_pymupdf"][0]["status"], "NO_CANDIDATE")
        self.assertIsNone(result["caption_to_extracted_table"][0]["pymupdf_table_index"])

    def test_two_possible_pymupdf_tables_is_ambiguous(self):
        two = extracted()
        two.append(copy.deepcopy(two[0]))
        result = evaluate_tables(outline(), detector(), two, page_number=1)
        self.assertEqual(result["detector_to_pymupdf"][0]["status"], "MULTIPLE_CANDIDATES")

    def test_two_regions_claiming_one_extracted_table_is_conflict(self):
        result = evaluate_tables(
            outline(), detector() + detector(), extracted(), page_number=1
        )
        self.assertTrue(all(x["status"] == "SHARED_EXTRACTED_TABLE_CONFLICT"
                            for x in result["detector_to_pymupdf"]))

    def test_empty_cells_warn_without_dropping(self):
        cells = [["Bit", "Description"], ["24", None]]
        result = evaluate_tables(
            outline(), detector(), extracted(cells=cells), page_number=1
        )
        self.assertIn("EMPTY_CELL_R2_C2",
                      result["pymupdf_tables"][0]["cell_warnings"])
        self.assertIsNone(result["pymupdf_tables"][0]["cells"][1][1])

    def test_ragged_row_warns(self):
        self.assertIn("COL_COUNT_MISMATCH_ROW_2",
                      inspect_cells([["A", "B"], ["A"]], 2, 2))

    def test_no_caption_still_reports_unassigned_table(self):
        source = outline()
        source["elements"] = []
        result = evaluate_tables(source, detector(), extracted(), page_number=1)
        self.assertEqual(result["caption_to_extracted_table"], [])
        self.assertEqual(len(result["pymupdf_tables"]), 1)


if __name__ == "__main__":
    unittest.main()
