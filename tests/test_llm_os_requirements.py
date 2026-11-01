import unittest

from llm_import.validation import verify_minimum_os_requirements


SOURCE = (
    "[PDF-Seite 2]\n"
    "Minimum System Requirement\n"
    "• IBM PC compatible with Pentium III processor\n"
    "• Operating Systems Win® 98/98SE / Win® 2000 / "
    "Win® ME / Win® XP\n"
    "• 64MB system memory\n"
    "\n"
    "[PDF-Seite 5]\n"
    "Driver Installation (Windows® XP/2000/ME/98)\n"
    "\n"
    "[PDF-Seite 7]\n"
    "This option is only available with Windows 98/98SE.\n"
)


class TestMinimumOSRequirements(unittest.TestCase):

    def test_windows_xp_requirement(self):
        self.assertTrue(
            verify_minimum_os_requirements(
                ["Windows XP"],
                ["Operating Systems Win® 98/98SE / Win® 2000 / Win® ME / Win® XP"],
                SOURCE,
            )
        )

    def test_windows_98_and_98se(self):
        self.assertTrue(
            verify_minimum_os_requirements(
                ["Windows 98", "Windows 98 SE"],
                [
                    "Operating Systems Win® 98/98SE / Win® 2000 / Win® ME / Win® XP",
                    "Operating Systems Win® 98/98SE / Win® 2000 / Win® ME / Win® XP",
                ],
                SOURCE,
            )
        )

    def test_unsupported_vista(self):
        self.assertFalse(
            verify_minimum_os_requirements(
                ["Windows Vista"],
                ["Operating Systems Win® 98/98SE / Win® 2000 / Win® ME / Win® XP"],
                SOURCE,
            )
        )

    def test_driver_heading_not_sufficient(self):
        source = (
            "Driver Installation (Windows XP/2000/ME/98)\n"
        )
        self.assertFalse(
            verify_minimum_os_requirements(
                ["Windows XP"],
                ["Driver Installation (Windows XP/2000/ME/98)"],
                source,
            )
        )

    def test_bios_instructions_not_sufficient(self):
        source = (
            "BIOS Flashing\n"
            "This option is only available with Windows 98/98SE.\n"
        )
        self.assertFalse(
            verify_minimum_os_requirements(
                ["Windows 98"],
                ["This option is only available with Windows 98/98SE."],
                source,
            )
        )

    def test_second_os_missing_from_source(self):
        source = (
            "Minimum System Requirement\n"
            "• Operating Systems Win XP\n"
        )

        self.assertFalse(
            verify_minimum_os_requirements(
                ["Windows XP", "Windows 2000"],
                ["Operating Systems Win XP"],
                source,
            )
        )

    def test_os_from_later_section_not_accepted(self):
        source = (
            "Minimum System Requirement\n"
            "• 64MB system memory\n"
            "\n"
            "Driver Installation\n"
            "Operating Systems Win XP\n"
        )

        self.assertFalse(
            verify_minimum_os_requirements(
                ["Windows XP"],
                ["Operating Systems Win XP"],
                source,
            )
        )

    def test_shared_evidence_with_win_aliases(self):
        evidence = (
            "Operating Systems Win® 98/98SE / "
            "Win® 2000 / Win® ME / Win® XP"
        )

        self.assertTrue(
            verify_minimum_os_requirements(
                [
                    "Win 98",
                    "Win 98SE",
                    "Win 2000",
                    "Win ME",
                    "Win XP",
                ],
                [evidence],
                SOURCE,
            )
        )

    def test_combined_windows_98_and_98se(self):
        evidence = (
            "Operating Systems Win® 98/98SE / "
            "Win® 2000 / Win® ME / Win® XP"
        )

        self.assertTrue(
            verify_minimum_os_requirements(
                ["Win 98/98SE", "Win 2000", "Win ME", "Win XP"],
                [evidence],
                SOURCE,
            )
        )


if __name__ == "__main__":
    unittest.main()