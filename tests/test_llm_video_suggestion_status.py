import unittest

from llm_import.video_evidence import video_suggestion_status


class TestVideoSuggestionStatus(unittest.TestCase):

    def test_valid_suggestions(self):
        diagnostic = {
            "context_status": "SHARED",
            "valid": True,
            "suggestions": {
                "VGA": "VGA Monitor Connector",
                "S-Video": "S-Video Output",
            },
        }

        self.assertEqual(
            video_suggestion_status(diagnostic),
            "EVIDENCE_SUGGESTED",
        )

    def test_unknown_model(self):
        diagnostic = {
            "context_status": "UNCERTAIN",
            "valid": False,
            "suggestions": {},
        }

        self.assertEqual(
            video_suggestion_status(diagnostic),
            "UNCERTAIN",
        )

    def test_incomplete_evidence(self):
        diagnostic = {
            "context_status": "SHARED",
            "valid": False,
            "suggestions": {
                "VGA": "VGA Monitor Connector",
            },
        }

        self.assertEqual(
            video_suggestion_status(diagnostic),
            "UNCERTAIN",
        )


if __name__ == "__main__":
    unittest.main()