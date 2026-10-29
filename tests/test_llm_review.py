import unittest

from llm_import.review import (
    ReviewReport,
    ValidationIssue,
    add_legacy_issues,
    evaluate_final_fields,
    evaluate_final_review,
    separate_legacy_issues,
    resolve_validation_issues,
    evaluate_gpu_evidence,
)

class TestReviewReport(unittest.TestCase):

    def test_info_does_not_require_review(self):
        report = ReviewReport()
        report.add(
            "VALUE_NORMALIZED",
            "info",
            "dimensions_mm",
            "Abmessungen erfolgreich normalisiert",
        )

        self.assertFalse(report.requires_review)
        self.assertEqual(report.status, "VALIDATED")

    def test_warning_requires_review(self):
        report = ReviewReport()
        report.add(
            "UNIT_AMBIGUITY",
            "warning",
            "vram_mib",
            "Quelle nennt MB, Schema erwartet MiB",
        )

        self.assertTrue(report.requires_review)
        self.assertEqual(report.status, "REVIEW")

    def test_conflict_requires_review(self):
        report = ReviewReport()
        report.add(
            "CONFLICTING_VALUES",
            "error",
            "memory_clock_mhz",
            "1000 MHz und 1200 MHz gefunden",
        )

        self.assertTrue(report.requires_review)
        self.assertEqual(report.status, "REVIEW")

    def test_invalid_severity(self):
        report = ReviewReport()

        with self.assertRaises(ValueError):
            report.add("TEST", "critical")

    def test_legacy_warning_requires_review(self):
        report = ReviewReport()

        add_legacy_issues(
            report,
            ["LLM: Speichergröße nicht eindeutig"],
            [],
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(
            report.findings[0].code,
            "LLM_WARNING_UNVERIFIED",
        )

    def test_source_conflict_not_duplicated(self):
        report = ReviewReport()

        finding = {
            "code": "CONFLICTING_VALUES",
            "field": "memory_clock_mhz",
            "values": [1000, 1200],
            "severity": "review",
        }

        report.add(
            code="CONFLICTING_VALUES",
            severity="error",
            field_name="memory_clock_mhz",
        )

        old_message = (
            f"{finding['code']}: "
            f"{finding['field']} – {finding}"
        )

        add_legacy_issues(
            report,
            [old_message],
            [finding],
        )

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.status, "REVIEW")

    def test_llm_diagnostics_are_preserved(self):
        report = ReviewReport()

        add_legacy_issues(
            report,
            [
                "LLM: Abmessungen angeblich nicht vorhanden",
                "LLM: Abmessungen angeblich nicht vorhanden",
            ],
            [],
        )

        self.assertEqual(
            report.llm_diagnostics,
            ["LLM: Abmessungen angeblich nicht vorhanden"],
        )

        # Bestehende Sicherheitsentscheidung bleibt erhalten.
        self.assertEqual(report.status, "REVIEW")

    def test_final_source_conflict(self):
        report = evaluate_final_fields(
            {"memory_clock_mhz": None},
            {
                "memory_clock_mhz": {
                    "value": None,
                    "origin": "conflict",
                    "candidates": [1000, 1200],
                }
            },
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertEqual(report.findings[0].severity, "error")

    def test_final_validation_conflict(self):
        report = evaluate_final_fields(
            {"core_clock_mhz": None},
            {
                "core_clock_mhz": {
                    "value": None,
                    "origin": "validation_conflict",
                    "candidates": [650, 589],
                }
            },
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertEqual(
            report.findings[0].code,
            "VALIDATION_CONFLICT",
        )

    def test_final_verified_fields_have_no_conflict(self):
        report = evaluate_final_fields(
            {"dimensions_mm": "145 x 84 x 18 mm"},
            {
                "dimensions_mm": {
                    "value": "145 x 84 x 18 mm",
                    "evidence": "Card Dimension: 145 x 84 x 18 mm",
                    "origin": "deterministic",
                }
            },
        )

        self.assertEqual(len(report.findings), 0)
        self.assertFalse(report.requires_review)

    def test_conflict_value_must_be_null(self):
        report = evaluate_final_fields(
            {"memory_clock_mhz": 1000},
            {
                "memory_clock_mhz": {
                    "value": None,
                    "origin": "conflict",
                    "candidates": [1000, 1200],
                }
            },
        )

        codes = [finding.code for finding in report.findings]

        self.assertIn("CONFLICTING_VALUES", codes)
        self.assertIn("CONFLICT_VALUE_NOT_BLOCKED", codes)

    def test_final_value_must_match_evidence(self):
        report = evaluate_final_fields(
            {"core_clock_mhz": 589},
            {
                "core_clock_mhz": {
                    "value": 650,
                    "evidence": "Core Clock: 650 MHz",
                }
            },
        )

        codes = [finding.code for finding in report.findings]

        self.assertIn("EVIDENCE_VALUE_MISMATCH", codes)
        self.assertEqual(report.status, "REVIEW")

    def test_missing_evidence_is_rejected(self):
        report = evaluate_final_fields(
            {"core_clock_mhz": 589},
            {},
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertEqual(
            report.findings[0].code,
            "EVIDENCE_MISSING",
        )

    def test_separate_legacy_issues(self):
        problems, diagnostics = separate_legacy_issues([
            "vram_mib: Quellbeleg nennt MiB nicht eindeutig",
            "LLM: Abmessungen nicht gefunden",
            "core_clock_mhz: wörtlicher Quellenbeleg fehlt",
        ])

        self.assertEqual(len(problems), 2)
        self.assertEqual(len(diagnostics), 1)
        self.assertTrue(diagnostics[0].startswith("LLM:"))

    def test_validation_issue_defaults_to_unresolved(self):
        issue = ValidationIssue(
            code="EVIDENCE_NOT_FOUND",
            field="dimensions_mm",
            message="Wörtlicher Quellenbeleg fehlt",
        )

        self.assertFalse(issue.resolved)
        self.assertEqual(issue.field, "dimensions_mm")
        self.assertEqual(issue.code, "EVIDENCE_NOT_FOUND")

    def test_final_review_keeps_unresolved_validation_issue(self):
        issues = [
            ValidationIssue(
                code="INVALID_VALUE",
                field="core_clock_mhz",
                message="Ungültiger Wert",
            )
        ]

        specs = {"core_clock_mhz": None}
        evidence = {
            "core_clock_mhz": {
                "value": None,
                "evidence": "",
                "origin": "rejected",
            }
        }

        report = evaluate_final_review(
            issues,
            [],
            specs,
            evidence,
            source="Core Clock: 589 MHz",
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertIn(
            "INVALID_VALUE",
            [finding.code for finding in report.findings],
        )

    def test_final_review_detects_source_conflict(self):
        specs = {"memory_clock_mhz": None}
        evidence = {
            "memory_clock_mhz": {
                "value": None,
                "evidence": "",
                "origin": "conflict",
                "candidates": [1000, 1200],
            }
        }

        source_findings = [
            {
                "code": "CONFLICTING_VALUES",
                "field": "memory_clock_mhz",
                "values": [1000, 1200],
                "severity": "review",
            }
        ]

        report = evaluate_final_review(
            [],
            source_findings,
            specs,
            evidence,
            source=(
                "Memory Speed: 1000 MHz\n"
                "Memory Speed: 1200 MHz"
            ),
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertTrue(
            any(
                finding.code == "CONFLICTING_VALUES"
                for finding in report.findings
            )
        )

    def test_resolve_deterministic_integer(self):
        issues = [
            ValidationIssue(
                code="FIELD_MISSING",
                field="core_clock_mhz",
                message="Feld fehlt",
            )
        ]

        specs = {"core_clock_mhz": 589}
        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
                "origin": "deterministic",
            }
        }

        result = resolve_validation_issues(
            issues,
            specs,
            evidence,
            "Core Clock: 589 MHz",
        )

        self.assertTrue(result[0].resolved)

    def test_reject_fake_deterministic_evidence(self):
        issues = [
            ValidationIssue(
                code="FIELD_MISSING",
                field="core_clock_mhz",
                message="Feld fehlt",
            )
        ]

        specs = {"core_clock_mhz": 589}
        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
                "origin": "deterministic",
            }
        }

        result = resolve_validation_issues(
            issues,
            specs,
            evidence,
            "Core Clock: 650 MHz",
        )

        self.assertFalse(result[0].resolved)

    def test_reject_mb_as_mib_during_resolution(self):
        issue = ValidationIssue(
            code="VALUE_VERIFICATION_FAILED",
            field="vram_mib",
            message="MB ist nicht MiB",
        )

        specs = {"vram_mib": 1024}

        evidence = {
            "vram_mib": {
                "value": 1024,
                "evidence": "Memory Size: 1024 MB",
                "origin": "deterministic",
            }
        }

        result = resolve_validation_issues(
            [issue],
            specs,
            evidence,
            "Memory Size: 1024 MB",
        )

        self.assertFalse(result[0].resolved)

    def test_final_review_resolves_verified_integer(self):
        issue = ValidationIssue(
            code="FIELD_MISSING",
            field="core_clock_mhz",
            message="Feld fehlte zunächst",
        )

        specs = {"core_clock_mhz": 589}
        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
                "origin": "deterministic",
            }
        }

        report = evaluate_final_review(
            [issue],
            [],
            specs,
            evidence,
            source="Core Clock: 589 MHz",
        )

        self.assertEqual(report.status, "VALIDATED")

    def test_no_verified_specs_stays_review_for_unverified_value(self):
        issue = ValidationIssue(
            code="NO_VERIFIED_SPECS",
            field=None,
            message="Keine belegten Spezifikationen",
        )

        specs = {"core_clock_mhz": 589}
        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
                "origin": "llm",
            }
        }

        report = evaluate_final_review(
            [issue],
            [],
            specs,
            evidence,
            source="Core Clock: 589 MHz",
        )

        self.assertEqual(report.status, "REVIEW")

    def test_no_verified_specs_resolves_with_deterministic_value(self):
        issue = ValidationIssue(
            code="NO_VERIFIED_SPECS",
            field=None,
            message="Keine belegten Spezifikationen",
        )

        specs = {"core_clock_mhz": 589}
        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
                "origin": "deterministic",
            }
        }

        report = evaluate_final_review(
            [issue],
            [],
            specs,
            evidence,
            source="Core Clock: 589 MHz",
        )

        self.assertEqual(report.status, "VALIDATED")

    def test_final_review_deduplicates_source_conflict(self):
        specs = {"core_clock_mhz": None}
        evidence = {
            "core_clock_mhz": {
                "value": None,
                "evidence": "",
                "origin": "conflict",
                "candidates": [589, 650],
            }
        }
        source_findings = [
            {
                "code": "CONFLICTING_VALUES",
                "field": "core_clock_mhz",
                "values": [589, 650],
                "severity": "review",
            }
        ]

        report = evaluate_final_review(
            [],
            source_findings,
            specs,
            evidence,
            source=(
                "Core Clock: 589 MHz\n"
                "Core Clock: 650 MHz"
            ),
        )

        conflicts = [
            finding
            for finding in report.findings
            if finding.code == "CONFLICTING_VALUES"
            and finding.field == "core_clock_mhz"
        ]

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(report.status, "REVIEW")

    def test_resolve_verified_api_support(self):
        issue = ValidationIssue(
            code="EVIDENCE_NOT_FOUND",
            field="api_support",
            message="Wörtlicher Quellenbeleg fehlt",
        )

        source = (
            "DirectX Version Support: 10.1\n"
            "OpenGL Version Support: 3.1"
        )

        specs = {
            "api_support": ["DirectX 10.1", "OpenGL 3.1"]
        }

        evidence = {
            "api_support": {
                "value": ["DirectX 10.1", "OpenGL 3.1"],
                "evidence": [
                    "DirectX Version Support: 10.1",
                    "OpenGL Version Support: 3.1",
                ],
                "origin": "deterministic",
            }
        }

        result = resolve_validation_issues(
            [issue], specs, evidence, source
        )

        self.assertTrue(result[0].resolved)

    def test_reject_unverified_api_support(self):
        issue = ValidationIssue(
            code="EVIDENCE_NOT_FOUND",
            field="api_support",
            message="Wörtlicher Quellenbeleg fehlt",
        )

        source = (
            "DirectX Version Support: 10.1\n"
            "OpenGL Version Support: 3.1"
        )

        specs = {
            "api_support": ["DirectX 12", "OpenGL 3.1"]
        }

        evidence = {
            "api_support": {
                "value": ["DirectX 12", "OpenGL 3.1"],
                "evidence": [
                    "DirectX Version Support: 10.1",
                    "OpenGL Version Support: 3.1",
                ],
                "origin": "deterministic",
            }
        }

        result = resolve_validation_issues(
            [issue], specs, evidence, source
        )

        self.assertFalse(result[0].resolved)

    def test_final_review_deduplicates_multiple_conflicts(self):
        source_findings = [
            {
                "code": "CONFLICTING_VALUES",
                "field": "core_clock_mhz",
                "values": [589, 650],
            },
            {
                "code": "CONFLICTING_VALUES",
                "field": "core_clock_mhz",
                "values": [589, 650],
            },
        ]

        specs = {"core_clock_mhz": None}

        evidence = {
            "core_clock_mhz": {
                "value": None,
                "evidence": "",
                "origin": "conflict",
                "candidates": [589, 650],
            }
        }

        report = evaluate_final_review(
            [],
            source_findings,
            specs,
            evidence,
            source="Core Clock: 589 MHz\nCore Clock: 650 MHz",
        )

        conflicts = [
            finding
            for finding in report.findings
            if finding.code == "CONFLICTING_VALUES"
            and finding.field == "core_clock_mhz"
        ]

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].details["values"], [589, 650])
        self.assertEqual(report.status, "REVIEW")

    def test_final_gpu_evidence_valid(self):
        specs = {
            "core_clock_mhz": 589,
            "memory_type": "DDR3",
            "hdcp_support": True,
        }

        source = (
            "Core Clock: 589 MHz\n"
            "Memory Type: DDR3\n"
            "HDCP Support: Yes"
        )

        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
            },
            "memory_type": {
                "value": "DDR3",
                "evidence": "Memory Type: DDR3",
            },
            "hdcp_support": {
                "value": True,
                "evidence": "HDCP Support: Yes",
            },
        }

        report = evaluate_gpu_evidence(specs, evidence, source)

        self.assertEqual(report.status, "VALIDATED")

    def test_final_gpu_evidence_rejects_wrong_context(self):
        specs = {"core_clock_mhz": 589}

        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Memory Speed: 589 MHz",
            }
        }

        report = evaluate_gpu_evidence(
            specs,
            evidence,
            "Memory Speed: 589 MHz",
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertEqual(
            report.findings[0].code,
            "FINAL_EVIDENCE_INVALID",
        )

    def test_final_gpu_evidence_rejects_wrong_boolean(self):
        specs = {"hdcp_support": True}

        evidence = {
            "hdcp_support": {
                "value": True,
                "evidence": "HDCP Support: No",
            }
        }

        report = evaluate_gpu_evidence(
            specs,
            evidence,
            "HDCP Support: No",
        )

        self.assertEqual(report.status, "REVIEW")

    def test_final_review_rejects_wrong_memory_clock_context(self):
        specs = {
            "memory_clock_mhz": 589,
        }

        evidence = {
            "memory_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
            }
        }

        report = evaluate_final_review(
            validation_issues=[],
            source_findings=[],
            specs=specs,
            evidence=evidence,
            source="Core Clock: 589 MHz",
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertTrue(
            any(
                finding.code == "FINAL_EVIDENCE_INVALID"
                for finding in report.findings
            )
        )

    def test_final_review_valid_api_support(self):
        source = "DirectX Version Support: 10.1"

        report = evaluate_final_review(
            validation_issues=[],
            source_findings=[],
            specs={"api_support": ["DirectX 10.1"]},
            evidence={
                "api_support": {
                    "value": ["DirectX 10.1"],
                    "evidence": [
                        "DirectX Version Support: 10.1"
                    ],
                    "origin": "deterministic",
                }
            },
            source=source,
        )

        self.assertEqual(report.status, "VALIDATED")

    def test_final_review_rejects_wrong_api_version(self):
        source = "DirectX Version Support: 10.1"

        report = evaluate_final_review(
            validation_issues=[],
            source_findings=[],
            specs={"api_support": ["DirectX 12"]},
            evidence={
                "api_support": {
                    "value": ["DirectX 12"],
                    "evidence": [
                        "DirectX Version Support: 10.1"
                    ],
                    "origin": "deterministic",
                }
            },
            source=source,
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertTrue(any(
            finding.code == "FINAL_EVIDENCE_INVALID"
            for finding in report.findings
        ))

    def test_final_review_rejects_unknown_field(self):
        report = evaluate_final_review(
            validation_issues=[],
            source_findings=[],
            specs={"unknown_gpu_property": "example"},
            evidence={
                "unknown_gpu_property": {
                    "value": "example",
                    "evidence": "Unknown GPU Property: example",
                }
            },
            source="Unknown GPU Property: example",
        )

        self.assertEqual(report.status, "REVIEW")
        self.assertTrue(any(
            finding.code == "UNVERIFIED_FIELD"
            for finding in report.findings
        ))

    def test_normalization_conflict_forces_review(self):
        report = evaluate_final_review(
            validation_issues=[
                ValidationIssue(
                    code="NORMALIZATION_CONFLICT",
                    field=None,
                    message="GPU-Chip widerspricht dem Quelltext",
                )
            ],
            source_findings=[],
            specs={"gpu_chip": None},
            evidence={
                "gpu_chip": {
                    "value": None,
                    "evidence": "",
                }
            },
            source="Graphics Processing Unit: NVIDIA GeForce 210",
        )

        self.assertEqual(report.status, "REVIEW")

        self.assertTrue(any(
            finding.code == "NORMALIZATION_CONFLICT"
            for finding in report.findings
        ))

if __name__ == "__main__":
    unittest.main()
