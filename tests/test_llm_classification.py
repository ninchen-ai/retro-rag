import unittest

from llm_import.classification import validate_classification


class TestClassification(unittest.TestCase):

    def test_valid_gpu(self):
        findings = validate_classification(
            {
                "category": "grafikkarte",
                "manufacturer": "MSI",
                "model": "GeForce 210",
            },
            "MSI GeForce 210",
        )
        self.assertEqual(findings, [])

    def test_unsupported_category(self):
        findings = validate_classification(
            {
                "category": "cpu",
                "manufacturer": "Intel",
                "model": "E8400",
            },
            "Intel E8400",
        )
        self.assertIn(
            "UNSUPPORTED_CATEGORY",
            [item["code"] for item in findings],
        )

    def test_missing_manufacturer(self):
        findings = validate_classification(
            {
                "category": "grafikkarte",
                "manufacturer": "",
                "model": "GeForce 210",
            },
            "NVIDIA GeForce 210",
        )
        self.assertIn(
            "MISSING_IDENTITY",
            [item["code"] for item in findings],
        )

    def test_model_not_in_source(self):
        findings = validate_classification(
            {
                "category": "grafikkarte",
                "manufacturer": "MSI",
                "model": "GeForce 210",
            },
            "MSI Radeon HD 5450",
        )
        self.assertIn(
            "IDENTITY_NOT_IN_SOURCE",
            [item["code"] for item in findings],
        )


if __name__ == "__main__":
    unittest.main()