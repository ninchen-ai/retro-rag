"""Regressionstests für frühe Klassifikationsabbrüche."""

import io
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from scripts import import_llm


class TestClassificationFlow(unittest.TestCase):

    def run_import(self, classification, source):
        """Führt main() mit einer simulierten Ollama-Antwort aus."""

        with tempfile.TemporaryDirectory() as temp_dir:
            document = Path(temp_dir) / "hardware.txt"
            document.write_text(source, encoding="utf-8")

            ollama_response = (
                classification,
                {"total_duration": 0},
            )

            with (
                patch.object(
                    import_llm,
                    "call_ollama",
                    return_value=ollama_response,
                ) as mock_ollama,
                patch.object(
                    sys,
                    "argv",
                    ["import_llm.py", str(document)],
                ),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                exit_code = import_llm.main()

            return exit_code, mock_ollama.call_count, output.getvalue()

    def test_unsupported_category_stops_extraction(self):
        exit_code, calls, output = self.run_import(
            {
                "category": "cpu",
                "manufacturer": "Intel",
                "model": "E8400",
            },
            "Intel E8400",
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, 1)
        self.assertIn("UNSUPPORTED_CATEGORY", output)

    def test_missing_manufacturer_stops_extraction(self):
        exit_code, calls, output = self.run_import(
            {
                "category": "grafikkarte",
                "manufacturer": "",
                "model": "GeForce 210",
            },
            "NVIDIA GeForce 210",
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, 1)
        self.assertIn("MISSING_IDENTITY", output)

    def test_unverified_model_stops_extraction(self):
        exit_code, calls, output = self.run_import(
            {
                "category": "grafikkarte",
                "manufacturer": "MSI",
                "model": "GeForce 210",
            },
            "MSI Radeon HD 5450",
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, 1)
        self.assertIn("IDENTITY_NOT_IN_SOURCE", output)


if __name__ == "__main__":
    unittest.main()