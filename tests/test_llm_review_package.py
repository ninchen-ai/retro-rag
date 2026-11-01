import unittest

from llm_import.review_package import (
    plan_review_package,
    safe_name,
)

class TestReviewPackage(unittest.TestCase):

    def test_two_models_produce_four_files(self):
        data = {
            "results": [
                {
                    "source": {"sha256": "a" * 64},
                    "classification": {
                        "model": "GV-R92S128T",
                    },
                    "markdown": "# 128 MB",
                    "review_markdown": "# Review 128 MB",
                },
                {
                    "source": {"sha256": "a" * 64},
                    "classification": {
                        "model": "GV-R92S64T",
                    },
                    "markdown": "# 64 MB",
                    "review_markdown": "# Review 64 MB",
                },
            ]
        }

        plan = plan_review_package(data)

        self.assertEqual(len(plan), 4)
        self.assertTrue(
            all(item["status"] == "PLANNED" for item in plan)
        )
        self.assertTrue(
            all(
                item["path"].startswith(
                    "Retro-Computing/Import/review/aaaaaaaaaaaaaaaa/"
                )
                for item in plan
            )
        )

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            safe_name("../Hardware")

    def test_rejects_missing_markdown(self):
        data = {
            "results": [{
                "classification": {
                    "model": "GV-R92S128T",
                },
                "markdown": None,
                "review_markdown": "# Review",
            }]
        }

        with self.assertRaises(ValueError):
            plan_review_package(data)

    def test_rejects_mixed_sources(self):
        data = {
            "results": [
                {
                    "source": {"sha256": "a" * 64},
                    "classification": {"model": "GV-R92S128T"},
                    "markdown": "# Modell A",
                    "review_markdown": "# Review A",
                },
                {
                    "source": {"sha256": "b" * 64},
                    "classification": {"model": "GV-R92S64T"},
                    "markdown": "# Modell B",
                    "review_markdown": "# Review B",
                },
            ]
        }

        with self.assertRaises(ValueError):
            plan_review_package(data)


if __name__ == "__main__":
    unittest.main()