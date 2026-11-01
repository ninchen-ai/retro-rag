import unittest

from llm_import.normalizers import normalize_gpu_identity_and_apis


SOURCE = (
    "VGA Card GV-R92S128T / GV-R92S64T\n"
    "Powered by ATi RADEON 9200SE Graphics Processing Unit (GPU)\n"
)


class TestGpuIdentityNormalization(unittest.TestCase):

    def test_split_vendor_and_chip(self):
        specs = {
            "gpu_manufacturer": None,
            "gpu_chip": "ATi RADEON 9200SE",
        }
        evidence = {}
        issues = []

        normalize_gpu_identity_and_apis(
            SOURCE, specs, evidence, issues
        )

        self.assertEqual(specs["gpu_manufacturer"], "ATi")
        self.assertEqual(specs["gpu_chip"], "RADEON 9200SE")
        self.assertEqual(issues, [])

    def test_complete_missing_identity(self):
        specs = {
            "gpu_manufacturer": None,
            "gpu_chip": None,
        }
        evidence = {}
        issues = []

        normalize_gpu_identity_and_apis(
            SOURCE, specs, evidence, issues
        )

        self.assertEqual(specs["gpu_manufacturer"], "ATi")
        self.assertEqual(specs["gpu_chip"], "RADEON 9200SE")
        self.assertEqual(
            evidence["gpu_chip"]["origin"],
            "deterministic",
        )

    def test_reject_conflicting_chip(self):
        specs = {
            "gpu_manufacturer": "ATi",
            "gpu_chip": "RADEON 9800",
        }
        evidence = {}
        issues = []

        normalize_gpu_identity_and_apis(
            SOURCE, specs, evidence, issues
        )

        self.assertEqual(specs["gpu_chip"], "RADEON 9800")
        self.assertTrue(issues)

    def test_reject_conflicting_vendor(self):
        specs = {
            "gpu_manufacturer": "NVIDIA",
            "gpu_chip": None,
        }
        evidence = {}
        issues = []

        normalize_gpu_identity_and_apis(
            SOURCE, specs, evidence, issues
        )

        self.assertEqual(specs["gpu_manufacturer"], "NVIDIA")
        self.assertTrue(issues)

    def test_pdf_sorted_text_layout(self):
        source = (
            "1.1. FeaturesEnglish    •   "
            "Powered by ATi RADEON 9200SE "
            "Graphics Processing Unit (GPU)"
        )

        specs = {
            "gpu_manufacturer": None,
            "gpu_chip": None,
        }

        evidence = {}
        issues = []

        normalize_gpu_identity_and_apis(
            source,
            specs,
            evidence,
            issues,
        )

        self.assertEqual(
            specs["gpu_manufacturer"],
            "ATi",
        )
        self.assertEqual(
            specs["gpu_chip"],
            "RADEON 9200SE",
        )
        self.assertEqual(issues, [])

    def test_different_gpu_chips_are_not_assigned_automatically(self):
        source = (
            "GV-R92S128T\n"
            "Powered by ATi RADEON 9200SE "
            "Graphics Processing Unit (GPU)\n"
            "GV-R96P128D\n"
            "Powered by ATi RADEON 9600 PRO "
            "Graphics Processing Unit (GPU)\n"
        )

        specs = {
            "gpu_manufacturer": None,
            "gpu_chip": None,
        }
        evidence = {}
        issues = []

        normalize_gpu_identity_and_apis(
            source, specs, evidence, issues
        )

        self.assertIsNone(specs["gpu_chip"])
        self.assertTrue(issues)

    def test_repeated_same_gpu_is_allowed(self):
        source = (
            "Graphics Processing Unit: ATI RADEON 9200SE\n"
            "Powered by ATi RADEON 9200SE "
            "Graphics Processing Unit (GPU)\n"
        )

        specs = {
            "gpu_manufacturer": None,
            "gpu_chip": None,
        }

        evidence = {}
        issues = []

        normalize_gpu_identity_and_apis(
            source,
            specs,
            evidence,
            issues,
        )

        self.assertEqual(
            specs["gpu_manufacturer"].casefold(),
            "ati",
        )
        self.assertEqual(
            specs["gpu_chip"],
            "RADEON 9200SE",
        )
        self.assertEqual(issues, [])

if __name__ == "__main__":
    unittest.main()