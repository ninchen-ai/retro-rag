"""Prompt-variant regression tests for the read-only PDF vision experiment."""
import unittest

from experiments.pdf_vision_benchmark import functional_prompt, targeted_prompt


class VisionBenchmarkPromptTests(unittest.TestCase):
    def test_functional_prompt_preserves_candidates_without_answers(self):
        candidates = (
            "Recommendations for Thermal Performance",
            "ADD-IN CARD",
            "FAN DIRECTION",
        )
        prompt = functional_prompt(candidates)
        for text in candidates:
            self.assertIn(text, prompt)
        self.assertIn("spatial grouping", prompt)
        self.assertIn("uncertain", prompt)
        self.assertNotIn('"kind": "figure_label"', prompt)

    def test_baseline_and_functional_are_distinct(self):
        candidates = ("Sample Label",)
        self.assertNotEqual(targeted_prompt(candidates), functional_prompt(candidates))


if __name__ == "__main__":
    unittest.main()
