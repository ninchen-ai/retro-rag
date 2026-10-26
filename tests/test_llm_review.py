import unittest

from llm_import.review import ReviewReport, add_legacy_issues


class TestReviewReport(unittest.TestCase):

    def test_info_does_not_require_review(self):
        report = ReviewReport()
        report.add(
            "VALUE_NORMALIZED",
            "info",
            "dimensions_mm",
            "Abmessungen erfolgreich normalisiert",
        )

        self.assertFalse(report.requires_review)
        self.assertEqual(report.status, "VALIDATED")

    def test_warning_requires_review(self):
        report = ReviewReport()
        report.add(
            "UNIT_AMBIGUITY",
            "warning",
            "vram_mib",
            "Quelle nennt MB, Schema erwartet MiB",
        )

        self.assertTrue(report.requires_review)
        self.assertEqual(report.status, "REVIEW")

    def test_conflict_requires_review(self):
        report = ReviewReport()
        report.add(
            "CONFLICTING_VALUES",
            "error",
            "memory_clock_mhz",
            "1000 MHz und 1200 MHz gefunden",
        )

        self.assertTrue(report.requires_review)
        self.assertEqual(report.status, "REVIEW")

    def test_invalid_severity(self):
        report = ReviewReport()

        with self.assertRaises(ValueError):
            report.add("TEST", "critical")

    def test_legacy_warning_requires_review(self):
        report = ReviewReport()

        add_legacy_issues(
            report,
            ["LLM: Speichergröße nicht eindeutig"],
            [],
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(
            report.findings[0].code,
            "LLM_WARNING_UNVERIFIED",
        )

    def test_source_conflict_not_duplicated(self):
        report = ReviewReport()

        finding = {
            "code": "CONFLICTING_VALUES",
            "field": "memory_clock_mhz",
            "values": [1000, 1200],
            "severity": "review",
        }

        report.add(
            code="CONFLICTING_VALUES",
            severity="error",
            field_name="memory_clock_mhz",
        )

        old_message = (
            f"{finding['code']}: "
            f"{finding['field']} – {finding}"
        )

        add_legacy_issues(
            report,
            [old_message],
            [finding],
        )

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.status, "REVIEW")


if __name__ == "__main__":
    unittest.main()
