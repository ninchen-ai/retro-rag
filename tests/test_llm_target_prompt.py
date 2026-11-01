import unittest
from unittest.mock import patch

from scripts import import_llm


class StopAfterPrompt(Exception):
    pass


class TestTargetPrompt(unittest.TestCase):

    def test_target_model_is_in_extraction_prompt(self):
        captured = {}

        def fake_call_ollama(
            ollama_url,
            model,
            system_prompt,
            source,
            schema,
        ):
            captured["prompt"] = system_prompt
            raise StopAfterPrompt()

        with patch.object(
            import_llm,
            "call_ollama",
            side_effect=fake_call_ollama,
        ):
            with self.assertRaises(StopAfterPrompt):
                import_llm.extract_gpu_document(
                    source=(
                        "GV-R92S128T / GV-R92S64T "
                        "ATI Radeon 9200SE"
                    ),
                    category="grafikkarte",
                    manufacturer="Gigabyte",
                    model_name="GV-R92S128T",
                    model="qwen3.5:4b",
                    ollama_url="http://127.0.0.1:11434",
                    target_model="GV-R92S128T",
                )

        self.assertIn(
            "Gigabyte GV-R92S128T",
            captured["prompt"],
        )

        self.assertIn(
            "ausschließlich",
            captured["prompt"],
        )

    def test_default_prompt_without_target(self):
        captured = {}

        def fake_call_ollama(
            ollama_url,
            model,
            system_prompt,
            source,
            schema,
        ):
            captured["prompt"] = system_prompt
            raise StopAfterPrompt()

        with patch.object(
            import_llm,
            "call_ollama",
            side_effect=fake_call_ollama,
        ):
            with self.assertRaises(StopAfterPrompt):
                import_llm.extract_gpu_document(
                    source="MSI GeForce 210",
                    category="grafikkarte",
                    manufacturer="MSI",
                    model_name="GeForce 210",
                    model="qwen3.5:4b",
                    ollama_url="http://127.0.0.1:11434",
                )

        self.assertNotIn(
            "Extrahiere ausschließlich Eigenschaften des Hardwaremodells",
            captured["prompt"],
        )


if __name__ == "__main__":
    unittest.main()