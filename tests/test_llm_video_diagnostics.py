import copy
import unittest

from llm_import.video_evidence import diagnose_model_video_outputs


class TestVideoDiagnostics(unittest.TestCase):

    def test_diagnostics_do_not_modify_values(self):
        source = """
[PDF-Seite 3]
1.2. Board Layout

GV-R92S128T / GV-R92S64T

VGA Monitor Connector
S-Video Output
"""

        specs = {
            "video_outputs": ["VGA", "S-Video"]
        }

        evidence = {
            "video_outputs": {
                "value": ["VGA", "S-Video"],
                "evidence": "128MB DDR memory",
            }
        }

        original_specs = copy.deepcopy(specs)
        original_evidence = copy.deepcopy(evidence)

        result = diagnose_model_video_outputs(
            source=source,
            target_model="GV-R92S128T",
            values=specs["video_outputs"],
        )

        self.assertEqual(result["context_status"], "SHARED")
        self.assertTrue(result["valid"])

        self.assertEqual(specs, original_specs)
        self.assertEqual(evidence, original_evidence)

    def test_unknown_model_is_not_confirmed(self):
        source = """
1.2. Board Layout
GV-R92S128T / GV-R92S64T
VGA Monitor Connector
"""

        result = diagnose_model_video_outputs(
            source=source,
            target_model="GV-R92S256T",
            values=["VGA"],
        )

        self.assertEqual(result["context_status"], "UNCERTAIN")
        self.assertFalse(result["valid"])
        self.assertEqual(result["suggestions"], {})


if __name__ == "__main__":
    unittest.main()