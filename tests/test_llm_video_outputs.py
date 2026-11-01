import unittest

from llm_import.validation import verify_video_outputs_evidence


SOURCE = (
    "Supports TV-Out and D-Sub connectors\n"
    "VGA D-Sub 15 pin\n"
    "S-Video\n"
    "Integrated with 128MB DDR memory\n"
)


class TestVideoOutputs(unittest.TestCase):

    def test_vga_from_dsub(self):
        self.assertTrue(
            verify_video_outputs_evidence(
                ["VGA"],
                ["Supports TV-Out and D-Sub connectors"],
                SOURCE,
            )
        )

    def test_svideo_from_explicit_label(self):
        self.assertTrue(
            verify_video_outputs_evidence(
                ["S-Video"],
                ["S-Video"],
                SOURCE,
            )
        )

    def test_two_supported_outputs(self):
        self.assertTrue(
            verify_video_outputs_evidence(
                ["VGA", "S-Video"],
                [
                    "VGA D-Sub 15 pin",
                    "S-Video",
                ],
                SOURCE,
            )
        )

    def test_wrong_evidence(self):
        self.assertFalse(
            verify_video_outputs_evidence(
                ["VGA"],
                ["Integrated with 128MB DDR memory"],
                SOURCE,
            )
        )

    def test_unsupported_hdmi(self):
        self.assertFalse(
            verify_video_outputs_evidence(
                ["HDMI"],
                ["Supports TV-Out and D-Sub connectors"],
                SOURCE,
            )
        )

    def test_missing_second_evidence(self):
        self.assertFalse(
            verify_video_outputs_evidence(
                ["VGA", "S-Video"],
                ["VGA D-Sub 15 pin"],
                SOURCE,
            )
        )

    def test_tv_out_not_proof_of_svideo(self):
        self.assertFalse(
            verify_video_outputs_evidence(
                ["S-Video"],
                ["Supports TV-Out and D-Sub connectors"],
                SOURCE,
            )
        )

    def test_duplicate_vga_alias(self):
        self.assertFalse(
            verify_video_outputs_evidence(
                ["VGA", "D-Sub"],
                [
                    "VGA D-Sub 15 pin",
                    "VGA D-Sub 15 pin",
                ],
                SOURCE,
            )
        )

    def test_negated_hdmi_is_not_valid(self):
        source = "HDMI is not supported."

        self.assertFalse(
            verify_video_outputs_evidence(
                ["HDMI"],
                ["HDMI is not supported."],
                source,
            )
        )

    def test_negated_vga_is_not_valid(self):
        source = "VGA output is not available."

        self.assertFalse(
            verify_video_outputs_evidence(
                ["VGA"],
                ["VGA output is not available."],
                source,
            )
        )

    def test_without_hdmi(self):
        source = "Graphics card without HDMI."

        self.assertFalse(
            verify_video_outputs_evidence(
                ["HDMI"],
                ["Graphics card without HDMI."],
                source,
            )
        )

    def test_no_dsub_connector(self):
        source = "No D-Sub connector available."

        self.assertFalse(
            verify_video_outputs_evidence(
                ["VGA"],
                ["No D-Sub connector available."],
                source,
            )
        )