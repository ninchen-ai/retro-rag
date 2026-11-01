import unittest

from llm_import.source_checks import check_source


class TestManualSourceChecks(unittest.TestCase):

    def test_gigabyte_manual_has_sufficient_data(self):
        source = (
            "Gigabyte GV-R92S128T\n"
            "Powered by ATi RADEON 9200SE "
            "Graphics Processing Unit (GPU)\n"
            "Supports Direct X 8.1\n"
            "Supports AGP 8X\n"
        )

        findings = check_source(
            source,
            manufacturer="Gigabyte",
            model="GV-R92S128T",
        )

        codes = {item["code"] for item in findings}

        self.assertNotIn("INSUFFICIENT_DATA", codes)
        self.assertNotIn("MODEL_AMBIGUOUS", codes)

    def test_pdf_sorted_text_layout(self):
        source = (
            "Gigabyte GV-R92S64T\n"
            "1.1. FeaturesEnglish    •   "
            "Powered by ATi RADEON 9200SE "
            "Graphics Processing Unit (GPU)\n"
            "• Supports Direct X 8.1\n"
            "• Supports AGP 8X\n"
        )

        findings = check_source(
            source,
            manufacturer="Gigabyte",
            model="GV-R92S64T",
        )

        self.assertFalse(
            any(
                item["code"] == "INSUFFICIENT_DATA"
                for item in findings
            )
        )

    def test_repeated_api_is_only_one_field(self):
        source = (
            "Gigabyte GV-R92S128T\n"
            "Supports Direct X 8.1\n"
            "Supports Direct X 8.1\n"
            "Supports Direct X 8.1\n"
        )

        findings = check_source(
            source,
            manufacturer="Gigabyte",
            model="GV-R92S128T",
        )

        insufficient = [
            item for item in findings
            if item["code"] == "INSUFFICIENT_DATA"
        ]

        self.assertEqual(len(insufficient), 1)
        self.assertEqual(
            insufficient[0]["recognized_fields"],
            1,
        )

    def test_weak_document_stays_insufficient(self):
        source = (
            "Gigabyte GV-R92S128T\n"
            "High performance graphics card.\n"
            "Suitable for multimedia applications.\n"
        )

        findings = check_source(
            source,
            manufacturer="Gigabyte",
            model="GV-R92S128T",
        )

        self.assertTrue(
            any(
                item["code"] == "INSUFFICIENT_DATA"
                for item in findings
            )
        )


if __name__ == "__main__":
    unittest.main()