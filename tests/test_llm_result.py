import hashlib
import json
import unittest
from pathlib import Path

from llm_import.result import build_import_result
from llm_import.review import ReviewReport


class TestImportResult(unittest.TestCase):

    def test_validated_result(self):
        source_bytes = b"Graphics Processing Unit: NVIDIA GeForce 210"

        report = ReviewReport()

        result = build_import_result(
            source_path=Path("geforce-210.txt"),
            source_bytes=source_bytes,
            model="qwen3.5:4b",
            classification={
                "category": "grafikkarte",
                "manufacturer": "MSI",
                "model": "GeForce 210",
            },
            markdown="# MSI GeForce 210",
            review=report,
            evidence={},
        )

        self.assertEqual(result["review"]["status"], "VALIDATED")
        self.assertEqual(result["source"]["filename"], "geforce-210.txt")
        self.assertEqual(
            result["source"]["sha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )

        # Das Ergebnis muss vollständig JSON-kompatibel sein.
        json.dumps(result)

    def test_review_findings_are_preserved(self):
        report = ReviewReport()
        report.add(
            code="CONFLICTING_VALUES",
            severity="error",
            field_name="core_clock_mhz",
            message="Widersprüchliche GPU-Taktraten",
            details={"candidates": [589, 650]},
        )

        result = build_import_result(
            source_path=Path("conflict.txt"),
            source_bytes=b"test",
            model="qwen3.5:4b",
            classification={"category": "grafikkarte"},
            markdown="# Entwurf",
            review=report,
            evidence={},
        )

        self.assertEqual(result["review"]["status"], "REVIEW")
        self.assertEqual(
            result["review"]["findings"][0]["code"],
            "CONFLICTING_VALUES",
        )
        self.assertEqual(
            result["review"]["findings"][0]["details"]["candidates"],
            [589, 650],
        )


if __name__ == "__main__":
    unittest.main()