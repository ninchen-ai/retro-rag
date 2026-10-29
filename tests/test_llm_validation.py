import unittest

from scripts.import_llm import validate_specs
from llm_import.validation import verify_api_support_evidence, verify_gpu_field_evidence, classify_gpu_field_coverage


class TestStructuredValidation(unittest.TestCase):

    def test_invalid_integer_creates_structured_issue(self):
        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        extraction = {
            "specs": {
                "core_clock_mhz": {
                    "value": "589",
                    "evidence": "Core Clock: 589 MHz",
                }
            },
            "warnings": [],
        }

        specs, problems, evidence, issues = validate_specs(
            extraction,
            schema,
            "Core Clock: 589 MHz",
        )

        self.assertIsNone(specs["core_clock_mhz"])
        self.assertTrue(problems)
        issue_codes = {issue.code for issue in issues}

        self.assertIn("INVALID_VALUE", issue_codes)
        self.assertIn("NO_VERIFIED_SPECS", issue_codes)

        invalid_issue = next(
            issue for issue in issues
            if issue.code == "INVALID_VALUE"
        )

        self.assertEqual(invalid_issue.field, "core_clock_mhz")
        self.assertIsNone(evidence["core_clock_mhz"]["value"])
        self.assertEqual(
            evidence["core_clock_mhz"]["origin"],
            "rejected",
        )
        self.assertEqual(
            evidence["core_clock_mhz"]["evidence"],
            "",
        )

    def test_missing_field_creates_rejected_evidence(self):
        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        extraction = {
            "specs": {},
            "warnings": [],
        }

        specs, problems, evidence, issues = validate_specs(
            extraction,
            schema,
            "Core Clock: 589 MHz",
        )

        self.assertIsNone(specs["core_clock_mhz"])
        self.assertEqual(evidence["core_clock_mhz"]["value"], None)
        self.assertEqual(
            evidence["core_clock_mhz"]["origin"],
            "rejected",
        )
        self.assertEqual(issues[0].code, "FIELD_MISSING")
        self.assertTrue(problems)

    def test_missing_source_evidence_is_rejected(self):
        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        extraction = {
            "specs": {
                "core_clock_mhz": {
                    "value": 589,
                    "evidence": "Core Clock: 589 MHz",
                }
            },
            "warnings": [],
        }

        specs, problems, evidence, issues = validate_specs(
            extraction,
            schema,
            "Core Clock: 650 MHz",
        )

        self.assertIsNone(specs["core_clock_mhz"])
        self.assertIsNone(evidence["core_clock_mhz"]["value"])
        self.assertEqual(evidence["core_clock_mhz"]["origin"], "rejected")
        self.assertEqual(issues[0].code, "EVIDENCE_NOT_FOUND")
        self.assertTrue(problems)

    def test_value_verification_failure_is_rejected(self):
        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        extraction = {
            "specs": {
                "core_clock_mhz": {
                    "value": 650,
                    "evidence": "Core Clock: 589 MHz",
                }
            },
            "warnings": [],
        }

        specs, problems, evidence, issues = validate_specs(
            extraction,
            schema,
            "Core Clock: 589 MHz",
        )

        self.assertIsNone(specs["core_clock_mhz"])
        self.assertIsNone(evidence["core_clock_mhz"]["value"])
        self.assertEqual(evidence["core_clock_mhz"]["origin"], "rejected")
        self.assertEqual(issues[0].code, "VALUE_VERIFICATION_FAILED")
        self.assertTrue(problems)

    def test_empty_value_with_evidence_creates_issue(self):
        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        extraction = {
            "specs": {
                "core_clock_mhz": {
                    "value": None,
                    "evidence": "Core Clock: 589 MHz",
                }
            },
            "warnings": [],
        }

        specs, problems, evidence, issues = validate_specs(
            extraction,
            schema,
            "Core Clock: 589 MHz",
        )

        self.assertIsNone(specs["core_clock_mhz"])
        self.assertEqual(
            evidence["core_clock_mhz"]["evidence"],
            "",
        )
        self.assertEqual(
            evidence["core_clock_mhz"]["origin"],
            "rejected",
        )
        self.assertEqual(issues[0].code, "UNEXPECTED_EVIDENCE")
        self.assertTrue(problems)

    def test_invalid_warnings_format(self):
        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        extraction = {
            "specs": {
                "core_clock_mhz": {
                    "value": 589,
                    "evidence": "Core Clock: 589 MHz",
                }
            },
            "warnings": "keine",
        }

        specs, problems, evidence, issues = validate_specs(
            extraction, schema, "Core Clock: 589 MHz"
        )

        self.assertEqual(specs["core_clock_mhz"], 589)
        self.assertIn(
            "INVALID_WARNINGS_FORMAT",
            [issue.code for issue in issues],
        )
        self.assertTrue(problems)

    def test_no_verified_specs(self):
        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        extraction = {
            "specs": {
                "core_clock_mhz": {
                    "value": None,
                    "evidence": "",
                }
            },
            "warnings": [],
        }

        specs, problems, evidence, issues = validate_specs(
            extraction, schema, "Keine technischen Angaben"
        )

        self.assertIsNone(specs["core_clock_mhz"])
        self.assertIn(
            "NO_VERIFIED_SPECS",
            [issue.code for issue in issues],
        )
        self.assertTrue(problems)

    def test_api_support_evidence_valid(self):
        source = (
            "DirectX Version Support: 10.1\n"
            "OpenGL Version Support: 3.1"
        )

        self.assertTrue(
            verify_api_support_evidence(
                ["DirectX 10.1", "OpenGL 3.1"],
                [
                    "DirectX Version Support: 10.1",
                    "OpenGL Version Support: 3.1",
                ],
                source,
            )
        )

    def test_api_support_evidence_rejects_wrong_version(self):
        source = (
            "DirectX Version Support: 10.1\n"
            "OpenGL Version Support: 3.1"
        )

        self.assertFalse(
            verify_api_support_evidence(
                ["DirectX 12", "OpenGL 3.1"],
                [
                    "DirectX Version Support: 10.1",
                    "OpenGL Version Support: 3.1",
                ],
                source,
            )
        )

    def test_invalid_warnings_does_not_imply_missing_specs(self):
        from import_llm import validate_specs

        schema = {
            "fields": {
                "core_clock_mhz": {
                    "type": "integer",
                    "nullable": True,
                }
            }
        }

        data = {
            "specs": {
                "core_clock_mhz": {
                    "value": 589,
                    "evidence": "Core Clock: 589 MHz",
                }
            },
            "warnings": "invalid",
        }

        specs, problems, evidence, issues = validate_specs(
            data,
            schema,
            "Core Clock: 589 MHz",
        )

        codes = {issue.code for issue in issues}

        self.assertEqual(specs["core_clock_mhz"], 589)
        self.assertIn("INVALID_WARNINGS_FORMAT", codes)
        self.assertNotIn("NO_VERIFIED_SPECS", codes)

    def test_gpu_core_clock_evidence(self):
        source = (
            "Core Clock: 589 MHz\n"
            "Memory Speed: 1000 MHz"
        )

        self.assertTrue(
            verify_gpu_field_evidence(
                "core_clock_mhz",
                589,
                "Core Clock: 589 MHz",
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "core_clock_mhz",
                1000,
                "Memory Speed: 1000 MHz",
                source,
            )
        )

    def test_gpu_memory_type_evidence(self):
        source = "Memory Type: DDR3"

        self.assertTrue(
            verify_gpu_field_evidence(
                "memory_type",
                "DDR3",
                "Memory Type: DDR3",
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "memory_type",
                "GDDR5",
                "Memory Type: DDR3",
                source,
            )
        )

    def test_gpu_hdcp_evidence(self):
        source = "HDCP Support: No"

        self.assertTrue(
            verify_gpu_field_evidence(
                "hdcp_support",
                False,
                "HDCP Support: No",
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "hdcp_support",
                True,
                "HDCP Support: No",
                source,
            )
        )

    def test_gpu_evidence_must_exist_in_source(self):
        self.assertFalse(
            verify_gpu_field_evidence(
                "core_clock_mhz",
                589,
                "Core Clock: 589 MHz",
                "Memory Speed: 589 MHz",
            )
        )

    def test_gpu_semantic_coverage(self):
        specs = {
            "core_clock_mhz": 589,
            "memory_type": "DDR3",
            "hdcp_support": True,
            "api_support": ["DirectX 10.1"],
            "interface": "PCI Express x16 2.0",
            "vram_mib": None,
            "video_outputs": [],
            "gpu_manufacturer": "NVIDIA",
            "gpu_chip": "GeForce 210",
        }

        coverage = classify_gpu_field_coverage(specs)

        self.assertEqual(
            coverage["core_clock_mhz"],
            "VERIFICATION_AVAILABLE",
        )
        self.assertEqual(
            coverage["memory_type"],
            "VERIFICATION_AVAILABLE",
        )
        self.assertEqual(
            coverage["hdcp_support"],
            "VERIFICATION_AVAILABLE",
        )
        self.assertEqual(
            coverage["api_support"],
            "VERIFICATION_AVAILABLE",
        )
        self.assertEqual(
            coverage["interface"],
            "VERIFICATION_AVAILABLE",
        )
        self.assertEqual(
            coverage["vram_mib"],
            "MISSING",
        )
        self.assertEqual(
            coverage["video_outputs"],
            "MISSING",
        )
        self.assertEqual(
            coverage["gpu_manufacturer"],
            "VERIFICATION_AVAILABLE",
        )
        self.assertEqual(
            coverage["gpu_chip"],
            "VERIFICATION_AVAILABLE",
        )

    def test_gpu_memory_clock_field_context(self):
        source = (
            "Core Clock: 589 MHz\n"
            "Memory Speed: 1000 MHz"
        )

        self.assertTrue(
            verify_gpu_field_evidence(
                "memory_clock_mhz",
                1000,
                "Memory Speed: 1000 MHz",
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "memory_clock_mhz",
                589,
                "Core Clock: 589 MHz",
                source,
            )
        )

    def test_gpu_memory_bus_width(self):
        source = "Memory Bus: 64 bits"

        self.assertTrue(
            verify_gpu_field_evidence(
                "memory_bus_width_bit",
                64,
                source,
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "memory_bus_width_bit",
                128,
                source,
                source,
            )
        )

    def test_gpu_interface_evidence(self):
        source = "Interface: PCI Express x16 2.0"

        self.assertTrue(
            verify_gpu_field_evidence(
                "interface",
                "PCI Express x16 2.0",
                source,
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "interface",
                "PCI Express x16 3.0",
                source,
                source,
            )
        )

    def test_gpu_dimensions_evidence(self):
        source = "Card Dimension: 145 x 84 x 18 mm"

        self.assertTrue(
            verify_gpu_field_evidence(
                "dimensions_mm",
                "145 x 84 x 18 mm",
                source,
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "dimensions_mm",
                "145 x 84 x 20 mm",
                source,
                source,
            )
        )

    def test_gpu_manufacturer_and_chip_evidence(self):
        source = (
            "Graphics Processing Unit: NVIDIA GeForce 210"
        )

        self.assertTrue(
            verify_gpu_field_evidence(
                "gpu_manufacturer",
                "NVIDIA",
                source,
                source,
            )
        )

        self.assertTrue(
            verify_gpu_field_evidence(
                "gpu_chip",
                "GeForce 210",
                source,
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "gpu_manufacturer",
                "MSI",
                source,
                source,
            )
        )

        self.assertFalse(
            verify_gpu_field_evidence(
                "gpu_chip",
                "GeForce 210 GT",
                source,
                source,
            )
        )

if __name__ == "__main__":
    unittest.main()
