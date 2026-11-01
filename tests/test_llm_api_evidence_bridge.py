import unittest

from llm_import.review import evaluate_gpu_evidence


class TestApiEvidenceBridge(unittest.TestCase):

    SOURCE = "Supports Direct X 8.1"

    def test_quoted_string_evidence(self):
        report = evaluate_gpu_evidence(
            specs={"api_support": ["Direct X 8.1"]},
            evidence={
                "api_support": {
                    "value": ["Direct X 8.1"],
                    "evidence": '"Supports Direct X 8.1"',
                }
            },
            source=self.SOURCE,
        )

        self.assertFalse(
            any(
                f.code == "FINAL_EVIDENCE_INVALID"
                for f in report.findings
            )
        )

    def test_wrong_version_stays_invalid(self):
        report = evaluate_gpu_evidence(
            specs={"api_support": ["Direct X 9.0"]},
            evidence={
                "api_support": {
                    "value": ["Direct X 9.0"],
                    "evidence": '"Supports Direct X 8.1"',
                }
            },
            source=self.SOURCE,
        )

        self.assertTrue(
            any(
                f.code == "FINAL_EVIDENCE_INVALID"
                for f in report.findings
            )
        )

    def test_missing_second_api_evidence_is_invalid(self):
        report = evaluate_gpu_evidence(
            specs={
                "api_support": ["Direct X 8.1", "OpenGL 1.4"]
            },
            evidence={
                "api_support": {
                    "value": ["Direct X 8.1", "OpenGL 1.4"],
                    "evidence": '"Supports Direct X 8.1"',
                }
            },
            source=self.SOURCE,
        )

        self.assertTrue(
            any(
                f.code == "FINAL_EVIDENCE_INVALID"
                for f in report.findings
            )
        )


if __name__ == "__main__":
    unittest.main()