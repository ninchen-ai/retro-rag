import unittest

from llm_import.model_context import find_shared_board_layout
from llm_import.video_evidence import suggest_video_evidence


class TestModelContext(unittest.TestCase):

    def test_shared_board_layout(self):
        source = """
[PDF-Seite 3]
1.2. Board Layout

GV-R92S128T (128MB DDR) / GV-R92S64T (64MB DDR)

VGA Monitor Connector
S-Video Output
"""

        for model in ("GV-R92S128T", "GV-R92S64T"):
            context = find_shared_board_layout(source, model)

            self.assertEqual(context["status"], "SHARED")

            suggestions = suggest_video_evidence(
                context["section"],
                ["VGA", "S-Video"],
            )

            self.assertEqual(
                suggestions,
                {
                    "VGA": "VGA Monitor Connector",
                    "S-Video": "S-Video Output",
                },
            )

    def test_unknown_model_not_accepted(self):
        source = """
1.2. Board Layout
GV-R92S128T / GV-R92S64T
VGA Monitor Connector
"""

        context = find_shared_board_layout(
            source,
            "GV-R92S256T",
        )

        self.assertEqual(context["status"], "UNCERTAIN")

    def test_later_model_specific_section_not_shared(self):
        source = """
[PDF-Seite 3]
1.2. Board Layout

GV-R92S128T / GV-R92S64T

VGA Monitor Connector
S-Video Output

1.3. GV-R92S128T Additional Features

HDMI Output
"""

        context = find_shared_board_layout(
            source,
            "GV-R92S64T",
        )

        self.assertEqual(context["status"], "SHARED")

        # Der gemeinsame Abschnitt darf nicht in
        # modellbezogene Unterabschnitte hineinreichen.
        self.assertNotIn(
            "HDMI Output",
            context["section"],
        )


if __name__ == "__main__":
    unittest.main()