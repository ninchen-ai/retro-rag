
"""Integrationstests für den lesenden Review-Wiederanlauf."""

import unittest
from unittest.mock import patch

from llm_import.review_package import plan_review_package
from llm_import.review_resume import (
    inspect_review_package,
    validate_package_resume,
)


class TestReviewWorkflow(unittest.TestCase):

    def setUp(self):
        self.package = {
            "results": [
                {
                    "source": {"sha256": "a" * 64},
                    "classification": {"model": "GV-R92S128T"},
                    "markdown": "# GPU 128",
                    "review_markdown": "# Review 128",
                },
                {
                    "source": {"sha256": "a" * 64},
                    "classification": {"model": "GV-R92S64T"},
                    "markdown": "# GPU 64",
                    "review_markdown": "# Review 64",
                },
            ]
        }

        self.connection = {
            "base_url": "http://127.0.0.1:8080",
            "user": "nina",
            "password": "test",
        }

        self.files = {
            entry["path"]: entry["content"].encode("utf-8")
            for entry in plan_review_package(self.package)
        }

    @patch("llm_import.review_resume.read_review_file")
    def test_first_import_all_files_missing(self, mock_read):
        mock_read.return_value = None

        precheck = inspect_review_package(
            self.package, **self.connection
        )
        resume = validate_package_resume(self.package, precheck)

        self.assertEqual(precheck["status"], "READY")
        self.assertEqual(resume["status"], "READY")
        self.assertEqual(mock_read.call_count, 4)

        self.assertEqual(
            [item["action"] for item in resume["decisions"]],
            ["UPLOAD_CANDIDATE"] * 4,
        )

    @patch("llm_import.review_resume.read_review_file")
    def test_partial_upload_resume(self, mock_read):
        paths = list(self.files)
        remote = {
            paths[0]: self.files[paths[0]],
            paths[1]: self.files[paths[1]],
        }

        mock_read.side_effect = (
            lambda **kwargs: remote.get(kwargs["path"])
        )

        precheck = inspect_review_package(
            self.package, **self.connection
        )
        resume = validate_package_resume(self.package, precheck)

        self.assertEqual(resume["status"], "READY")
        self.assertEqual(
            [item["action"] for item in resume["decisions"]],
            [
                "SKIP_IDENTICAL",
                "SKIP_IDENTICAL",
                "UPLOAD_CANDIDATE",
                "UPLOAD_CANDIDATE",
            ],
        )

    @patch("llm_import.review_resume.read_review_file")
    def test_conflict_blocks_complete_package(self, mock_read):
        paths = list(self.files)

        def remote_read(**kwargs):
            if kwargs["path"] == paths[1]:
                return b"# Abweichender Inhalt"
            return None

        mock_read.side_effect = remote_read

        precheck = inspect_review_package(
            self.package, **self.connection
        )

        self.assertEqual(precheck["status"], "BLOCKED")
        self.assertEqual(
            [entry["status"] for entry in precheck["results"]],
            [
                "UPLOAD_REQUIRED",
                "CONFLICT",
                "SKIPPED",
                "SKIPPED",
            ],
        )

        # Ein abgebrochener PRECHECK darf keinen gebundenen
        # Wiederanlaufplan zur Ausführung liefern.
        with self.assertRaises(ValueError):
            validate_package_resume(self.package, precheck)

        self.assertEqual(mock_read.call_count, 2)


if __name__ == "__main__":
    unittest.main()
