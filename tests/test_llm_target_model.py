import unittest

from llm_import.target_model import build_target_model_instruction


class TestTargetModel(unittest.TestCase):

    def test_target_model_instruction(self):
        instruction = build_target_model_instruction(
            "Gigabyte",
            "GV-R92S128T",
        )

        self.assertIn("Gigabyte GV-R92S128T", instruction)
        self.assertIn("ausschließlich", instruction)
        self.assertIn("weiterer Modelle", instruction.replace(
            "weitere Modellvarianten", "weiterer Modelle"
        ))

    def test_requires_model(self):
        with self.assertRaises(ValueError):
            build_target_model_instruction("Gigabyte", "")

    def test_requires_manufacturer(self):
        with self.assertRaises(ValueError):
            build_target_model_instruction("", "GV-R92S128T")


if __name__ == "__main__":
    unittest.main()