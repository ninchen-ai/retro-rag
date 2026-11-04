"""Structural candidate audit is advisory, never auto-approval."""
import unittest

from scripts.pdf_heading_audit import audit_candidates, format_report
from scripts.pdf_heading_candidates import HeadingCandidate


def candidate(page, heading):
    return HeadingCandidate(
        pdf_page=page,
        level=heading.split(" ", 1)[0].count(".") + 1,
        heading=heading,
        evidence="test",
        confidence="candidate",
    )


class HeadingAuditTests(unittest.TestCase):
    def test_healthy_hierarchy_remains_unverified(self):
        result = audit_candidates([
            candidate(11, "1 Introduction and Overview"),
            candidate(12, "1.1 Reference Documents"),
            candidate(16, "2 Description of New Features"),
            candidate(17, "2.1 Signal Interface Differences"),
        ])
        self.assertTrue(all(x.status == "CANDIDATE" for x in result))

    def test_missing_parent_is_review_warning(self):
        result = audit_candidates([
            candidate(11, "1 Introduction and Overview"),
            candidate(14, "1.5.1 Changes to AGP"),
        ])
        self.assertEqual(result[-1].status, "REVIEW")
        self.assertIn("Parent 1.5 not detected", result[-1].reason)

    def test_wrong_main_and_duplicates(self):
        result = audit_candidates([
            candidate(11, "1 Introduction and Overview"),
            candidate(12, "2.1 Unrelated Section Heading"),
            candidate(13, "2.1 Unrelated Section Heading"),
        ])
        self.assertIn("Outside current main chapter 1", result[1].reason)
        self.assertIn("Repeated section number", result[2].reason)

    def test_report_is_tsv(self):
        result = audit_candidates([candidate(11, "1 Introduction and Overview")])
        report = format_report(result)
        self.assertEqual(len(report.strip().splitlines()), 2)
        self.assertIn("pdf_page\tlevel\tsection", report)


if __name__ == "__main__":
    unittest.main()
