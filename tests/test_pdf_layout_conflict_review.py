"""Regression tests for review-only layout conflicts (Intel 875P patterns)."""
import copy
import unittest

from experiments.pdf_layout_conflict_review import review_conflicts


def d(kind, rect, confidence=0.9):
    return {"class_name": kind, "bbox_pdf_points": rect,
            "confidence": confidence}


def t(rect):
    return {"bbox_pt": rect, "rows": 3, "columns": 2,
            "cells": [["a", "b"]] * 3}


class LayoutConflictReviewTests(unittest.TestCase):
    def test_identical_figure_and_table_are_conflict_not_resolution(self):
        report = review_conflicts([
            d("figure", [100, 100, 400, 300], 0.68),
            d("table", [100, 100, 400, 300], 0.42),
        ], [])
        found = [x for x in report["review_findings"]
                 if x["code"] == "FIGURE_TABLE_CLASS_CONFLICT"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["measurements"]["iou"], 1.0)
        self.assertFalse(found[0]["approved"])

    def test_distant_figure_and_table_are_not_conflict(self):
        report = review_conflicts([
            d("figure", [100, 100, 400, 300]),
            d("table", [100, 400, 400, 550]),
        ], [])
        self.assertEqual(report["review_findings"], [])

    def test_full_table_and_two_halves_both_retained(self):
        regions = [
            d("table", [100, 100, 500, 280]),
            d("table", [100, 100, 290, 280]),
            d("table", [299, 100, 500, 280]),
        ]
        saved = copy.deepcopy(regions)
        report = review_conflicts(regions, [])
        self.assertEqual(regions, saved)
        codes = [x["code"] for x in report["review_findings"]]
        self.assertGreaterEqual(codes.count("OVERLAPPING_TABLE_REGIONS"), 2)
        self.assertIn("POSSIBLE_MULTIPART_TABLE", codes)
        self.assertEqual(report["detector_region_count"], 3)
        self.assertFalse(report["approved"])

    def test_side_by_side_with_far_gap_not_grouped(self):
        regions = [
            d("table", [0, 0, 100, 200]),
            d("table", [150, 0, 250, 200]),
        ]
        report = review_conflicts(regions, [])
        self.assertEqual(report["review_findings"], [])

    def test_misaligned_regions_not_grouped(self):
        regions = [
            d("table", [0, 0, 100, 100]),
            d("table", [105, 80, 205, 180]),
        ]
        report = review_conflicts(regions, [])
        self.assertEqual(report["review_findings"], [])

    def test_pymupdf_table_inside_figure_remains_review(self):
        report = review_conflicts([
            d("figure", [100, 100, 400, 350]),
        ], [t([120, 120, 380, 330])])
        codes = [x["code"] for x in report["review_findings"]]
        self.assertIn("PYMUPDF_TABLE_IN_FIGURE", codes)

    def test_no_auto_approval_when_overlaps_are_high(self):
        report = review_conflicts([
            d("table", [0, 0, 100, 100]),
            d("table", [0, 0, 100, 100]),
        ], [])
        self.assertTrue(all(x["status"] == "REVIEW_REQUIRED"
                            and x["approved"] is False
                            for x in report["review_findings"]))

    def test_invalid_bbox_fails_closed(self):
        with self.assertRaises(ValueError):
            review_conflicts([d("figure", [10, 10, 0, 20])], [])

    def test_different_class_overlapping_slightly_no_conflict(self):
        report = review_conflicts([
            d("figure", [0, 0, 100, 100]),
            d("table", [90, 90, 190, 190]),
        ], [])
        self.assertEqual(report["review_findings"], [])

    def test_empty_inputs_still_valid_unapproved_report(self):
        report = review_conflicts([], [])
        self.assertEqual(report["review_findings"], [])
        self.assertFalse(report["approved"])


if __name__ == "__main__":
    unittest.main()
