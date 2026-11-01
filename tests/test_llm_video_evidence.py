import unittest

from llm_import.video_evidence import suggest_video_evidence
from llm_import.validation import verify_video_outputs_evidence


class TestVideoEvidenceSuggestions(unittest.TestCase):

    def test_valid_video_outputs(self):
        source = (
            "VGA Monitor Connector\n"
            "S-Video Output\n"
        )

        values = ["VGA", "S-Video"]
        suggestions = suggest_video_evidence(source, values)

        self.assertEqual(
            suggestions,
            {
                "VGA": "VGA Monitor Connector",
                "S-Video": "S-Video Output",
            },
        )

        self.assertTrue(
            verify_video_outputs_evidence(
                values,
                [suggestions.get(v, "") for v in values],
                source,
            )
        )

    def test_memory_is_not_video_evidence(self):
        source = (
            "Integrated with 128MB DDR memory\n"
        )

        self.assertEqual(
            suggest_video_evidence(source, ["VGA", "S-Video"]),
            {},
        )

    def test_generic_vga_product_name_not_accepted(self):
        source = "Gigabyte VGA Card"

        self.assertEqual(
            suggest_video_evidence(source, ["VGA"]),
            {},
        )

    def test_generic_svideo_not_accepted(self):
        source = "S-Video"

        self.assertEqual(
            suggest_video_evidence(source, ["S-Video"]),
            {},
        )

    def test_unknown_connector_not_invented(self):
        source = "VGA Monitor Connector"

        self.assertEqual(
            suggest_video_evidence(source, ["HDMI"]),
            {},
        )

    def test_suggestion_does_not_bypass_validator(self):
        source = "No VGA Monitor Connector"

        suggestions = suggest_video_evidence(
            source,
            ["VGA"],
        )

        # Die Suchfunktion liefert zunächst nur Textkandidaten.
        # Der Validator muss die negierte Aussage ablehnen.
        self.assertFalse(
            verify_video_outputs_evidence(
                ["VGA"],
                [suggestions.get("VGA", "")],
                source,
            )
        )


if __name__ == "__main__":
    unittest.main()