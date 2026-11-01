import unittest

from llm_import.review_report import render_review_report


class TestReviewReportRendering(unittest.TestCase):

    def test_report_contains_original_and_suggested_evidence(self):
        result = {
            "classification": {
                "manufacturer": "Gigabyte",
                "model": "GV-R92S128T",
            },
            "source": {
                "filename": "manual.pdf",
                "sha256": "abc123",
            },
            "review": {
                "status": "REVIEW",
                "findings": [{
                    "code": "FINAL_EVIDENCE_INVALID",
                    "severity": "error",
                    "field": "video_outputs",
                    "message": "Quellenbeleg ungültig",
                }],
            },
            "evidence": {
                "video_outputs": {
                    "value": ["VGA", "S-Video"],
                    "evidence": "128MB DDR memory",
                },
            },
            "evidence_suggestions": {
                "video_outputs": {
                    "model_context": "SHARED",
                    "model_evidence": (
                        "GV-R92S128T / GV-R92S64T"
                    ),
                    "suggestions": {
                        "VGA": "VGA Monitor Connector",
                        "S-Video": "S-Video Output",
                    },
                    "validation_passed": True,
                    "status": "EVIDENCE_SUGGESTED",
                },
            },
        }

        report = render_review_report(result)

        self.assertIn("Gigabyte GV-R92S128T", report)
        self.assertIn("128MB DDR memory", report)
        self.assertIn("VGA Monitor Connector", report)
        self.assertIn("S-Video Output", report)
        self.assertIn("FINAL_EVIDENCE_INVALID", report)
        self.assertIn("**Entscheidung:** Ausstehend", report)


if __name__ == "__main__":
    unittest.main()