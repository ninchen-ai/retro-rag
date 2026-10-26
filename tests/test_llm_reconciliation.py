import unittest

from llm_import.normalizers import reconcile_deterministic_value


class TestReconciliation(unittest.TestCase):

    def test_conflicting_clock_is_blocked(self):
        specs = {"core_clock_mhz": 650}
        evidence = {
            "core_clock_mhz": {
                "value": 650,
                "evidence": "Core Clock: 650 MHz",
            }
        }
        issues = []

        conflict = reconcile_deterministic_value(
            field_name="core_clock_mhz",
            current=650,
            candidate=589,
            source_evidence="Core Clock: 589 MHz",
            specs=specs,
            evidence=evidence,
            issues=issues,
        )

        self.assertTrue(conflict)
        self.assertIsNone(specs["core_clock_mhz"])
        self.assertEqual(
            evidence["core_clock_mhz"]["origin"],
            "validation_conflict",
        )
        self.assertEqual(
            evidence["core_clock_mhz"]["candidates"],
            [650, 589],
        )
        self.assertEqual(len(issues), 1)

    def test_matching_values_are_preserved(self):
        specs = {"core_clock_mhz": 589}
        evidence = {
            "core_clock_mhz": {
                "value": 589,
                "evidence": "Core Clock: 589 MHz",
            }
        }
        issues = []

        conflict = reconcile_deterministic_value(
            field_name="core_clock_mhz",
            current=589,
            candidate=589,
            source_evidence="Core Clock: 589 MHz",
            specs=specs,
            evidence=evidence,
            issues=issues,
        )

        self.assertFalse(conflict)
        self.assertEqual(specs["core_clock_mhz"], 589)
        self.assertEqual(len(issues), 0)


if __name__ == "__main__":
    unittest.main()
