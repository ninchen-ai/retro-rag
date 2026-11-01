import unittest
from unittest.mock import patch

from scripts import import_llm


class TestMultiModel(unittest.TestCase):

    def test_two_variants_remain_visible_on_failure(self):
        source = (
            "VGA Card GV-R92S128T / GV-R92S64T\n"
            "128MB(GV-R92S128T)/64MB(GV-R92S64T)"
        )

        with patch.object(
            import_llm,
            "extract_document_text",
            return_value=source,
        ), patch.object(
            import_llm,
            "extract_gpu_document",
            side_effect=RuntimeError("Testfehler"),
        ) as mock_extract:

            result = import_llm.process_multi_model_document(
                source_bytes=b"mock-pdf",
                filename="test.pdf",
                model="qwen3.5:4b",
                ollama_url="http://127.0.0.1:11434",
            )

        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(mock_extract.call_count, 2)

        self.assertEqual(
            [r["classification"]["model"] for r in result["results"]],
            ["GV-R92S128T", "GV-R92S64T"],
        )

        self.assertTrue(
            all(r["review"]["status"] == "REVIEW"
                for r in result["results"])
        )

        self.assertTrue(
            all(r["markdown"] is None
                for r in result["results"])
        )

    def test_two_variants_produce_separate_markdown(self):
        source = (
            "VGA Card GV-R92S128T / GV-R92S64T\n"
            "128MB(GV-R92S128T)/64MB(GV-R92S64T)"
        )

        extracted_targets = []

        def fake_extract_gpu_document(**kwargs):
            target = kwargs["target_model"]
            extracted_targets.append(target)

            markdown = f"# Gigabyte {target}\n"

            return (
                {},          # specs
                [],          # issues
                {},          # evidence
                [],          # validation_issues
                [],          # source_findings
                None,        # review (vom Orchestrator nicht verwendet)
                markdown,
                {},          # extraction_metrics
            )

        with patch.object(
            import_llm,
            "extract_document_text",
            return_value=source,
        ), patch.object(
            import_llm,
            "extract_gpu_document",
            side_effect=fake_extract_gpu_document,
        ), patch.object(
            import_llm,
            "evaluate_final_review",
            return_value={
                "status": "VALIDATED",
                "findings": [],
            },
        ), patch.object(
            import_llm,
            "build_import_result",
            side_effect=lambda **kwargs: {
                "classification": kwargs["classification"],
                "markdown": kwargs["markdown"],
                "review": {
                    "status": "VALIDATED",
                    "findings": [],
                },
                "evidence": kwargs["evidence"],
            },
        ):
            result = import_llm.process_multi_model_document(
                source_bytes=b"mock-pdf",
                filename="test.pdf",
                model="qwen3.5:4b",
                ollama_url="http://127.0.0.1:11434",
            )

        self.assertEqual(
            extracted_targets,
            ["GV-R92S128T", "GV-R92S64T"],
        )

        self.assertEqual(len(result["results"]), 2)

        self.assertEqual(
            result["results"][0]["markdown"],
            "# Gigabyte GV-R92S128T\n",
        )

        self.assertEqual(
            result["results"][1]["markdown"],
            "# Gigabyte GV-R92S64T\n",
        )

        self.assertTrue(
            all(
                item["review"]["status"] == "REVIEW"
                for item in result["results"]
            )
        )

        first = result["results"][0]
        second = result["results"][1]

        self.assertIn("review_markdown", first)
        self.assertIn("review_markdown", second)

        self.assertIn(
            "GV-R92S128T",
            first["review_markdown"],
        )
        self.assertIn(
            "GV-R92S64T",
            second["review_markdown"],
        )

        self.assertIn(
            "MULTI_MODEL_VALIDATION_PENDING",
            first["review_markdown"],
        )
        self.assertIn(
            "MULTI_MODEL_VALIDATION_PENDING",
            second["review_markdown"],
        )

        self.assertEqual(first["review"]["status"], "REVIEW")
        self.assertEqual(second["review"]["status"], "REVIEW")

if __name__ == "__main__":
    unittest.main()