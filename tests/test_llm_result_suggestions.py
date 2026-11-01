import unittest
from pathlib import Path

from llm_import.result import build_import_result
from llm_import.review import ReviewReport


class TestResultSuggestions(unittest.TestCase):

    def test_suggestions_are_separate_from_original_evidence(self):
        evidence = {
            "video_outputs": {
                "value": ["VGA"],
                "evidence": "128MB DDR memory",
            }
        }

        suggestions = {
            "video_outputs": {
                "model_context": "SHARED",
                "suggestions": {
                    "VGA": "VGA Monitor Connector",
                },
                "validation_passed": True,
                "status": "EVIDENCE_SUGGESTED",
            }
        }

        report = ReviewReport()
        report.add(
            code="FINAL_EVIDENCE_INVALID",
            severity="error",
            field_name="video_outputs",
            message="Ungeeigneter Quellenbeleg",
        )

        result = build_import_result(
            source_path=Path("test.pdf"),
            source_bytes=b"test",
            model="qwen3.5:4b",
            classification={
                "category": "grafikkarte",
                "model": "GV-R92S128T",
            },
            markdown="# Entwurf",
            review=report,
            evidence=evidence,
            evidence_suggestions=suggestions,
        )

        self.assertEqual(result["evidence"], evidence)
        self.assertEqual(
            result["evidence_suggestions"],
            suggestions,
        )
        self.assertEqual(result["review"]["status"], "REVIEW")
        self.assertTrue(
            any(
                finding["code"] == "FINAL_EVIDENCE_INVALID"
                for finding in result["review"]["findings"]
            )
        )

    def test_suggestions_are_optional(self):
        result = build_import_result(
            source_path=Path("test.pdf"),
            source_bytes=b"test",
            model="qwen3.5:4b",
            classification={"category": "grafikkarte"},
            markdown="# Entwurf",
            review=ReviewReport(),
            evidence={},
        )

        self.assertEqual(
            result["evidence_suggestions"],
            {},
        )


if __name__ == "__main__":
    unittest.main()