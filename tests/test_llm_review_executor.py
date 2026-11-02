
import unittest

from llm_import.review_executor import simulate_review_execution
from llm_import.review_orchestrator import build_review_dry_run


class TestReviewExecutor(unittest.TestCase):

    def setUp(self):
        data = {
            "results": [{
                "source": {"sha256": "a" * 64},
                "classification": {"model": "GV-R92S128T"},
                "markdown": "# GPU",
                "review_markdown": "# Review",
            }]
        }
        self.plan = build_review_dry_run(data)

    def test_successful_simulation(self):
        result = simulate_review_execution(self.plan)

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(len(result["actions"]), 5)
        self.assertTrue(
            all(
                action["status"] in {"CREATED", "EXISTS"}
                for action in result["actions"]
            )
        )

    def test_failure_stops_remaining_actions(self):
        result = simulate_review_execution(self.plan, fail_at=2)

        statuses = [
            action["status"]
            for action in result["actions"]
        ]

        self.assertEqual(
            statuses,
            [
                "EXISTS",
                "CREATED",
                "FAILED",
                "SKIPPED",
                "SKIPPED",
            ],
        )
        self.assertEqual(result["status"], "FAILED")

    def test_input_plan_remains_unchanged(self):
        simulate_review_execution(self.plan, fail_at=1)

        self.assertTrue(
            all(
                action["status"] == "PLANNED"
                for action in self.plan["actions"]
            )
        )

    def test_rejects_invalid_operation(self):
        self.plan["actions"][0]["operation"] = "DELETE"

        with self.assertRaises(ValueError):
            simulate_review_execution(self.plan)

    def test_rejects_invalid_failure_position(self):
        with self.assertRaises(ValueError):
            simulate_review_execution(self.plan, fail_at=99)

    def test_rejects_put_before_directories(self):
        self.plan["actions"][1], self.plan["actions"][3] = (
            self.plan["actions"][3],
            self.plan["actions"][1],
        )

        with self.assertRaises(ValueError):
            simulate_review_execution(self.plan)

    def test_rejects_foreign_directory(self):
        self.plan["actions"][1]["path"] = (
            "Retro-Computing/Hardware/"
        )

        with self.assertRaises(ValueError):
            simulate_review_execution(self.plan)

    def test_rejects_missing_parent(self):
        self.plan["actions"].pop(1)

        with self.assertRaises(ValueError):
            simulate_review_execution(self.plan)

    def test_rejects_duplicate_path(self):
        self.plan["actions"].append(
            self.plan["actions"][-1].copy()
        )

        with self.assertRaises(ValueError):
            simulate_review_execution(self.plan)

if __name__ == "__main__":
    unittest.main()
