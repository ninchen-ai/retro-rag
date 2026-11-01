import unittest

from llm_import.validation import (
    verify_gpu_field_evidence,
    verify_api_support_evidence,
)


SOURCE = (
    "Powered by ATi RADEON 9200SE Graphics Processing Unit (GPU)\n"
    "Supports Direct X 8.1\n"
    "Supports AGP 8X\n"
    "Integrated with 128MB(GV-R92S128T)/"
    "64MB(GV-R92S64T) DDR memory\n"
)


class TestManualEvidence(unittest.TestCase):

    def test_gpu_chip_from_manual(self):
        self.assertTrue(
            verify_gpu_field_evidence(
                "gpu_chip",
                "RADEON 9200SE",
                "Powered by ATi RADEON 9200SE "
                "Graphics Processing Unit (GPU)",
                SOURCE,
            )
        )

    def test_interface_from_manual(self):
        self.assertTrue(
            verify_gpu_field_evidence(
                "interface",
                "AGP 8X",
                "Supports AGP 8X",
                SOURCE,
            )
        )

    def test_memory_type_from_manual(self):
        self.assertTrue(
            verify_gpu_field_evidence(
                "memory_type",
                "DDR",
                "Integrated with 128MB(GV-R92S128T)/"
                "64MB(GV-R92S64T) DDR memory",
                SOURCE,
            )
        )

    def test_directx_from_manual(self):
        self.assertTrue(
            verify_api_support_evidence(
                ["DirectX 8.1"],
                ["Supports Direct X 8.1"],
                SOURCE,
            )
        )

    def test_reject_wrong_gpu(self):
        self.assertFalse(
            verify_gpu_field_evidence(
                "gpu_chip",
                "RADEON 9800",
                "Powered by ATi RADEON 9200SE "
                "Graphics Processing Unit (GPU)",
                SOURCE,
            )
        )

    def test_reject_wrong_directx_version(self):
        self.assertFalse(
            verify_api_support_evidence(
                ["DirectX 9.0"],
                ["Supports Direct X 8.1"],
                SOURCE,
            )
        )

    def test_reject_missing_source_evidence(self):
        self.assertFalse(
            verify_gpu_field_evidence(
                "interface",
                "PCI Express",
                "Supports PCI Express",
                SOURCE,
            )
        )


if __name__ == "__main__":
    unittest.main()