
import unittest

from llm_import.review_orchestrator import build_review_dry_run


class TestReviewOrchestrator(unittest.TestCase):

    def setUp(self):
        self.data = {
            "results": [
                {
                    "source": {"sha256": "a" * 64},
                    "classification": {"model": "GV-R92S128T"},
                    "markdown": "# Radeon 9200SE 128 MB",
                    "review_markdown": "# Review 128 MB",
                },
                {
                    "source": {"sha256": "a" * 64},
                    "classification": {"model": "GV-R92S64T"},
                    "markdown": "# Radeon 9200SE 64 MB",
                    "review_markdown": "# Review 64 MB",
                },
            ]
        }

    def test_complete_dry_run(self):
        result = build_review_dry_run(self.data)

        self.assertEqual(result["mode"], "DRY_RUN")
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["model_count"], 2)
        self.assertEqual(result["directory_count"], 3)
        self.assertEqual(result["file_count"], 4)
        self.assertEqual(len(result["actions"]), 8)

        operations = [
            action["operation"]
            for action in result["actions"]
        ]

        self.assertEqual(
            operations,
            [
                "VERIFY_DIRECTORY",
                "MKCOL",
                "MKCOL",
                "MKCOL",
                "PUT",
                "PUT",
                "PUT",
                "PUT",
            ],
        )

    def test_all_actions_remain_planned(self):
        result = build_review_dry_run(self.data)

        self.assertTrue(
            all(
                action["status"] == "PLANNED"
                for action in result["actions"]
            )
        )

    def test_rejects_missing_review(self):
        self.data["results"][0]["review_markdown"] = None

        with self.assertRaises(ValueError):
            build_review_dry_run(self.data)

    def test_rejects_duplicate_model(self):
        self.data["results"][1]["classification"]["model"] = (
            "GV-R92S128T"
        )

        with self.assertRaises(ValueError):
            build_review_dry_run(self.data)

    def test_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            build_review_dry_run(None)

    def test_dry_run_does_not_expose_file_contents(self):
        result = build_review_dry_run(self.data)

        for action in result["actions"]:
            self.assertNotIn("content", action)


if __name__ == "__main__":
    unittest.main()
