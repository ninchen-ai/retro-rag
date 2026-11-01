import unittest

from llm_import.review import evaluate_gpu_evidence


SOURCE = (
    "[PDF-Seite 2]\n"
    "Minimum System Requirement\n"
    "• Operating Systems Win® 98/98SE / "
    "Win® 2000 / Win® ME / Win® XP\n"
)

OS_LINE = (
    "Operating Systems Win® 98/98SE / "
    "Win® 2000 / Win® ME / Win® XP"
)


class TestOSReview(unittest.TestCase):

    def test_valid_requirement(self):
        report = evaluate_gpu_evidence(
            specs={
                "minimum_os_requirements": ["Windows XP"],
            },
            evidence={
                "minimum_os_requirements": {
                    "value": ["Windows XP"],
                    "evidence": f'"{OS_LINE}"',
                },
            },
            source=SOURCE,
        )

        self.assertFalse(report.requires_review)

    def test_invalid_requirement(self):
        report = evaluate_gpu_evidence(
            specs={
                "minimum_os_requirements": ["Windows Vista"],
            },
            evidence={
                "minimum_os_requirements": {
                    "value": ["Windows Vista"],
                    "evidence": f'"{OS_LINE}"',
                },
            },
            source=SOURCE,
        )

        self.assertTrue(
            any(
                finding.code == "FINAL_EVIDENCE_INVALID"
                and finding.field == "minimum_os_requirements"
                for finding in report.findings
            )
        )


if __name__ == "__main__":
    unittest.main()