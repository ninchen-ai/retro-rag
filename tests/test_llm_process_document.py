import hashlib
import unittest
from unittest.mock import patch

from scripts import import_llm
from llm_import.review import ReviewReport


class TestProcessDocument(unittest.TestCase):

    def test_unsupported_category_returns_review(self):
        source_bytes = b"Intel Core 2 Duo E8400"

        classification = {
            "category": "cpu",
            "manufacturer": "Intel",
            "model": "E8400",
        }

        with patch.object(
            import_llm,
            "call_ollama",
            return_value=(classification, {}),
        ) as mock_ollama:

            result = import_llm.process_document(
                source_bytes=source_bytes,
                filename="cpu.txt",
                model="qwen3.5:4b",
                ollama_url="http://127.0.0.1:11434/api/chat",
            )

        self.assertEqual(result["review"]["status"], "REVIEW")
        self.assertIsNone(result["markdown"])
        self.assertEqual(mock_ollama.call_count, 1)

        self.assertEqual(
            result["source"]["sha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )

        self.assertIn(
            "UNSUPPORTED_CATEGORY",
            [
                finding["code"]
                for finding in result["review"]["findings"]
            ],
        )

    def test_valid_gpu_returns_structured_result(self):
        source_bytes = b"MSI GeForce 210"

        classification = {
            "category": "grafikkarte",
            "manufacturer": "MSI",
            "model": "GeForce 210",
        }

        gpu_result = (
            {"gpu_chip": "GeForce 210"},  # specs
            [],                          # issues
            {
                "gpu_chip": {
                    "value": "GeForce 210",
                    "evidence": "MSI GeForce 210",
                }
            },
            [],                          # validation_issues
            [],                          # source_findings
            ReviewReport(),              # legacy review
            "---\ncategory: grafikkarte\n---",
            {},                          # extraction metrics
        )

        with (
            patch.object(
                import_llm,
                "classify_document",
                return_value=(classification, {}, []),
            ),
            patch.object(
                import_llm,
                "extract_gpu_document",
                return_value=gpu_result,
            ) as mock_extract,
            patch.object(
                import_llm,
                "evaluate_final_review",
                return_value=ReviewReport(),
            ),
        ):
            result = import_llm.process_document(
                source_bytes=source_bytes,
                filename="geforce-210.txt",
                model="qwen3.5:4b",
                ollama_url="http://127.0.0.1:11434/api/chat",
            )

        self.assertEqual(result["review"]["status"], "VALIDATED")
        self.assertIsNotNone(result["markdown"])
        self.assertEqual(
            result["classification"]["model"],
            "GeForce 210",
        )
        self.assertEqual(
            result["source"]["sha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )
        mock_extract.assert_called_once()

    def test_gpu_diagnostics_do_not_reach_stdout(self):
        import contextlib
        import io

        classification = {
            "category": "grafikkarte",
            "manufacturer": "MSI",
            "model": "GeForce 210",
        }

        def fake_extract(**kwargs):
            # Diagnose über die neue Schnittstelle sammeln.
            kwargs["diagnostics"].append("INTERNE GPU-DIAGNOSE")

            return (
                {"gpu_chip": "GeForce 210"},
                [],
                {},
                [],
                [],
                ReviewReport(),
                "# GPU-Entwurf",
                {},
            )

        output = io.StringIO()

        with (
            patch.object(
                import_llm,
                "classify_document",
                return_value=(classification, {}, []),
            ),
            patch.object(
                import_llm,
                "extract_gpu_document",
                side_effect=fake_extract,
            ),
            patch.object(
                import_llm,
                "evaluate_final_review",
                return_value=ReviewReport(),
            ),
            contextlib.redirect_stdout(output),
        ):
            result = import_llm.process_document(
                source_bytes=b"MSI GeForce 210",
                filename="gpu.txt",
                model="qwen3.5:4b",
                ollama_url="http://127.0.0.1:11434/api/chat",
            )

        # Keine Konsolenausgabe aus process_document().
        self.assertEqual(output.getvalue(), "")

        # Diagnosemeldung muss im Ergebnisobjekt vorhanden sein.
        self.assertEqual(
            result["diagnostics"],
            ["INTERNE GPU-DIAGNOSE"],
        )

        self.assertEqual(
            result["review"]["status"],
            "VALIDATED",
        )

    def test_print_import_report(self):
        import contextlib
        import io

        result = {
            "classification": {
                "category": "grafikkarte",
                "manufacturer": "MSI",
                "model": "GeForce 210",
            },
            "markdown": "---\ncategory: grafikkarte\n---",
            "review": {
                "status": "VALIDATED",
                "findings": [],
            },
            "coverage": {
                "gpu_chip": "VERIFICATION_AVAILABLE",
            },
            "evidence": {},
        }

        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            import_llm.print_import_report(result)

        text = output.getvalue()

        self.assertIn(
            "===== MARKDOWN-ENTWURF (nicht gespeichert) =====",
            text,
        )
        self.assertIn(
            "===== ZENTRALER REVIEW-BERICHT =====",
            text,
        )
        self.assertIn("STATUS: VALIDATED", text)

if __name__ == "__main__":
    unittest.main()