"""Prompt-variant regression tests for the read-only PDF vision experiment."""
import unittest
import pymupdf

from experiments.pdf_vision_benchmark import functional_prompt, targeted_prompt, render_focus_crop, describe_pdf_layout


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


    def test_focus_crop_returns_png_and_bounds(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 120), "FAN DIRECTION", fontsize=14, fontname="hebo")
        page.insert_text((54, 220), "PULLING", fontsize=10)
        raw = doc.tobytes()
        doc.close()
        png, bounds = render_focus_crop(raw, 1, "FAN DIRECTION", 200)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(bounds[3], bounds[1])
        self.assertGreater(bounds[3], 220)

    def test_focus_crop_rejects_missing_text(self):
        doc = pymupdf.open()
        doc.new_page()
        raw = doc.tobytes()
        doc.close()
        with self.assertRaises(ValueError):
            render_focus_crop(raw, 1, "NOT THERE", 200)

    def test_layout_hints_have_evidence_not_classifications(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "1 Sample Section", fontsize=17, fontname="hebo")
        page.insert_text((54, 120), "FAN DIRECTION", fontsize=12, fontname="hebo")
        page.insert_text((54, 160), "PULLING", fontsize=10, fontname="helv")
        raw = doc.tobytes()
        doc.close()
        hints = describe_pdf_layout(raw, 1, ("FAN DIRECTION", "NO SUCH TEXT"))
        candidate = hints["candidates"][0]
        self.assertEqual(candidate["status"], "located")
        self.assertTrue(candidate["bold"])
        self.assertGreater(candidate["font_size_pt"], 10)
        self.assertTrue(any(
            line["text"] == "PULLING" for line in candidate["nearby_text_lines"]
        ))
        self.assertNotIn("kind", candidate)
        self.assertEqual(hints["candidates"][1]["status"], "not_unique_or_missing")

    def test_baseline_and_functional_are_distinct(self):
        candidates = ("Sample Label",)
        self.assertNotEqual(targeted_prompt(candidates), functional_prompt(candidates))


if __name__ == "__main__":
    unittest.main()
