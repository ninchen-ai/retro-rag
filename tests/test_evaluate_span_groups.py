"""Tests for reviewer-gated span-group evaluation."""
import copy
import unittest

from experiments.evaluate_span_groups import evaluate


class SpanGroupEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.reference = {
            "schema_version": 1,
            "cases": [
                {"pdf_page": 40, "proposed_text": "POWER SUPPLY",
                 "source_texts": ["POWER", "SUPPLY"],
                 "expected_decision": "merge", "reviewed": True},
                {"pdf_page": 41, "proposed_text": "Fan Vent",
                 "source_texts": ["Fan", "Vent"],
                 "expected_decision": "keep_separate", "reviewed": False},
            ],
        }
        self.reports = [
            {"pdf_page": 40, "span_group_proposals": [{
                "proposed_text": "POWER SUPPLY",
                "source_spans": [{"text": "POWER"}, {"text": "SUPPLY"}],
            }]},
            {"pdf_page": 41, "span_group_proposals": [{
                "proposed_text": "Fan Vent",
                "source_spans": [{"text": "Fan"}, {"text": "Vent"}],
            }]},
        ]

    def test_unreviewed_excluded_even_if_proposed(self):
        result = evaluate(self.reference, self.reports)
        self.assertEqual(result["reviewed_scored"], 1)
        self.assertEqual(result["reviewed_matches"], 1)
        self.assertEqual(result["provisional_cases_excluded"], 1)
        self.assertFalse(result["approved"])

    def test_confirmed_wrong_merge_reported_as_mismatch(self):
        reference = copy.deepcopy(self.reference)
        reference["cases"][1]["reviewed"] = True
        result = evaluate(reference, self.reports)
        self.assertEqual(result["reviewed_scored"], 2)
        self.assertEqual(result["reviewed_matches"], 1)
        self.assertEqual(result["reviewed_mismatches"], 1)

    def test_no_merge_can_match_keep_separate(self):
        reference = copy.deepcopy(self.reference)
        reference["cases"][1]["reviewed"] = True
        report = copy.deepcopy(self.reports)
        report[1]["span_group_proposals"] = []
        result = evaluate(reference, report)
        self.assertEqual(result["reviewed_matches"], 2)

    def test_duplicate_report_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(self.reference, [self.reports[0], self.reports[0]])

    def test_duplicate_reference_rejected(self):
        reference = copy.deepcopy(self.reference)
        reference["cases"].append(copy.deepcopy(reference["cases"][0]))
        with self.assertRaises(ValueError):
            evaluate(reference, self.reports)


if __name__ == "__main__":
    unittest.main()
