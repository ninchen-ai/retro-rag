"""Unit tests: reference evaluation never scores provisional labels."""
import unittest

from experiments.evaluate_layout_reference import evaluate


class ReferenceEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.reference = {
            "schema_version": 1,
            "pages": [
                {"pdf_page": 38, "candidates": [
                    {"text": "True heading", "expected_kind": "section_heading", "reviewed": True},
                    {"text": "Drawing label", "expected_kind": "figure_label", "reviewed": True},
                ]},
                {"pdf_page": 40, "candidates": [
                    {"text": "Unconfirmed", "expected_kind": "figure_label", "reviewed": False},
                ]},
            ],
        }
        self.report = {
            "pdf_page": 38,
            "heading_candidates": [
                {"heading": "True heading", "location_status": "LOCATED",
                 "review_reason": "NO_NEARBY_FIGURE_DETECTED"},
                {"heading": "Drawing label", "location_status": "LOCATED",
                 "review_reason": "POSSIBLY_FIGURE_ASSOCIATED"},
            ],
        }

    def test_scoring_excludes_unreviewed(self):
        result = evaluate(self.reference, [self.report])
        self.assertEqual(result["reviewed_annotations_scored"], 2)
        self.assertEqual(result["matches"], 2)
        self.assertEqual(result["unreviewed_excluded"], 1)
        self.assertFalse(result["approved"])

    def test_missing_report_is_not_counted_as_mismatch(self):
        result = evaluate(self.reference, [])
        self.assertEqual(result["reviewed_annotations_scored"], 0)
        self.assertEqual(result["missing_or_ambiguous"], 2)

    def test_duplicate_pages_fail_closed(self):
        with self.assertRaises(ValueError):
            evaluate(self.reference, [self.report, self.report])

    def test_ambiguous_locations_do_not_count(self):
        self.report["heading_candidates"][1]["location_status"] = "AMBIGUOUS_OR_UNMATCHED"
        result = evaluate(self.reference, [self.report])
        self.assertEqual(result["reviewed_annotations_scored"], 1)
        self.assertEqual(result["missing_or_ambiguous"], 1)


if __name__ == "__main__":
    unittest.main()
