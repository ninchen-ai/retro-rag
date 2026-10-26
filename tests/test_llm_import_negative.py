import unittest

from llm_import.source_checks import check_source


class TestNegativeImports(unittest.TestCase):

    def test_conflicting_memory_clock(self):
        source = """
MSI GeForce 210
Graphics Processing Unit: NVIDIA GeForce 210
Memory Speed: 1000 MHz
Memory Speed: 1200 MHz
Memory Type: DDR3
"""

        findings = check_source(
            source, "MSI", "GeForce 210"
        )

        conflicts = [
            finding
            for finding in findings
            if finding["code"] == "CONFLICTING_VALUES"
            and finding["field"] == "memory_clock_mhz"
        ]

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(
            conflicts[0]["values"],
            [1000, 1200]
        )

    def test_conflicting_gpu_clock(self):
        source = """
MSI GeForce 210
Graphics Processing Unit: NVIDIA GeForce 210
Core Clock: 589 MHz
Core Clock: 650 MHz
Memory Type: DDR3
"""
        findings = check_source(
            source, "MSI", "GeForce 210"
        )

        self.assertTrue(any(
            f["code"] == "CONFLICTING_VALUES"
            and f["field"] == "core_clock_mhz"
            for f in findings
        ))

    def test_missing_model_identity(self):
        source = """
MSI Graphics Card
Interface: PCI Express x16 2.0
Memory Type: DDR3
"""
        findings = check_source(
            source, "MSI", "GeForce 210"
        )

        self.assertTrue(any(
            f["code"] == "MODEL_AMBIGUOUS"
            and f["field"] == "model"
            for f in findings
        ))

    def test_insufficient_data(self):
        source = """
MSI GeForce 210
Technical product information.
"""
        findings = check_source(
            source, "MSI", "GeForce 210"
        )

        self.assertTrue(any(
            f["code"] == "INSUFFICIENT_DATA"
            for f in findings
        ))

    def test_valid_source(self):
        source = """
MSI GeForce 210
Graphics Processing Unit: NVIDIA GeForce 210
Core Clock: 589 MHz
Memory Speed: 1000 MHz
Memory Type: DDR3
Memory Bus: 64 bits
"""
        findings = check_source(
            source, "MSI", "GeForce 210"
        )

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
