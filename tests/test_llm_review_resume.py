import unittest

from llm_import.review_resume import (
    decide_review_upload,
    sha256_content,
    inspect_review_upload,
    inspect_review_package,
    verify_uncertain_review_upload,
    plan_package_resume,
)
from unittest.mock import patch


class TestReviewResume(unittest.TestCase):

    def test_missing_remote_file_requires_upload(self):
        result = decide_review_upload(
            local_content=b"# GPU",
            remote_content=None,
        )
        self.assertEqual(result["status"], "UPLOAD_REQUIRED")

    def test_identical_remote_file_is_unchanged(self):
        result = decide_review_upload(
            local_content=b"# GPU",
            remote_content=b"# GPU",
        )
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(
            result["local_sha256"],
            result["remote_sha256"],
        )

    def test_different_remote_file_is_conflict(self):
        result = decide_review_upload(
            local_content=b"# GPU Version 2",
            remote_content=b"# GPU Version 1",
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertNotEqual(
            result["local_sha256"],
            result["remote_sha256"],
        )

    def test_empty_content_is_compared_correctly(self):
        result = decide_review_upload(
            local_content=b"",
            remote_content=b"",
        )
        self.assertEqual(result["status"], "UNCHANGED")

    def test_invalid_local_content_rejected(self):
        with self.assertRaises(ValueError):
            decide_review_upload(
                local_content="# GPU",
                remote_content=None,
            )

    def test_invalid_remote_content_rejected(self):
        with self.assertRaises(ValueError):
            decide_review_upload(
                local_content=b"# GPU",
                remote_content="# GPU",
            )

    def test_inspect_missing_remote(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            return_value=None,
        ) as mock_read:
            result = inspect_review_upload(
                base_url="http://127.0.0.1:8080",
                user="nina",
                password="test",
                path="Retro-Computing/Import/review/test.md",
                local_content=b"# GPU",
            )

        self.assertEqual(result["status"], "UPLOAD_REQUIRED")
        self.assertIsNone(result["remote_sha256"])
        mock_read.assert_called_once()

    def test_inspect_identical_remote(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            return_value=b"# GPU",
        ):
            result = inspect_review_upload(
                base_url="http://127.0.0.1:8080",
                user="nina",
                password="test",
                path="Retro-Computing/Import/review/test.md",
                local_content=b"# GPU",
            )

        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(
            result["local_sha256"],
            result["remote_sha256"],
        )

    def test_inspect_conflicting_remote(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            return_value=b"# Andere GPU",
        ):
            result = inspect_review_upload(
                base_url="http://127.0.0.1:8080",
                user="nina",
                password="test",
                path="Retro-Computing/Import/review/test.md",
                local_content=b"# GPU",
            )

        self.assertEqual(result["status"], "CONFLICT")

    def test_inspect_propagates_read_error(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            side_effect=RuntimeError("WebDAV-GET fehlgeschlagen"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "WebDAV-GET"
            ):
                inspect_review_upload(
                    base_url="http://127.0.0.1:8080",
                    user="nina",
                    password="test",
                    path="Retro-Computing/Import/review/test.md",
                    local_content=b"# GPU",
                )

    def test_inspect_invalid_content_without_network(self):
        with patch(
            "llm_import.review_resume.read_review_file"
        ) as mock_read:
            with self.assertRaises(ValueError):
                inspect_review_upload(
                    base_url="http://127.0.0.1:8080",
                    user="nina",
                    password="test",
                    path="Retro-Computing/Import/review/test.md",
                    local_content="# GPU",
                )

            mock_read.assert_not_called()


    def make_package(self):
        return {
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

    def package_args(self):
        return {
            "base_url": "http://127.0.0.1:8080",
            "user": "nina",
            "password": "test",
        }

    @patch("llm_import.review_resume.inspect_review_upload")
    def test_package_all_files_missing(self, mock_inspect):
        def inspect(**kwargs):
            return {
                "path": kwargs["path"],
                "status": "UPLOAD_REQUIRED",
                "local_sha256": "a" * 64,
                "remote_sha256": None,
            }

        mock_inspect.side_effect = inspect

        result = inspect_review_package(
            self.make_package(), **self.package_args()
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["file_count"], 4)
        self.assertEqual(mock_inspect.call_count, 4)

    @patch("llm_import.review_resume.inspect_review_upload")
    def test_package_all_files_unchanged(self, mock_inspect):
        def inspect(**kwargs):
            return {
                "path": kwargs["path"],
                "status": "UNCHANGED",
                "local_sha256": "a" * 64,
                "remote_sha256": "a" * 64,
            }

        mock_inspect.side_effect = inspect

        result = inspect_review_package(
            self.make_package(), **self.package_args()
        )

        self.assertEqual(result["status"], "READY")
        self.assertTrue(
            all(item["status"] == "UNCHANGED"
                for item in result["results"])
        )

    @patch("llm_import.review_resume.inspect_review_upload")
    def test_package_conflict_blocks_remaining(self, mock_inspect):
        def inspect(**kwargs):
            status = (
                "CONFLICT" if mock_inspect.call_count == 2
                else "UPLOAD_REQUIRED"
            )
            return {"path": kwargs["path"], "status": status}

        mock_inspect.side_effect = inspect

        result = inspect_review_package(
            self.make_package(), **self.package_args()
        )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            [item["status"] for item in result["results"]],
            ["UPLOAD_REQUIRED", "CONFLICT", "SKIPPED", "SKIPPED"],
        )
        self.assertEqual(mock_inspect.call_count, 2)

    @patch("llm_import.review_resume.inspect_review_upload")
    def test_package_read_failure_blocks(self, mock_inspect):
        mock_inspect.side_effect = RuntimeError("HTTP 403")

        result = inspect_review_package(
            self.make_package(), **self.package_args()
        )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["results"][0]["status"], "FAILED")
        self.assertEqual(mock_inspect.call_count, 1)

    @patch("llm_import.review_resume.inspect_review_upload")
    def test_invalid_package_never_reads_remote(self, mock_inspect):
        package = self.make_package()
        package["results"][0]["review_markdown"] = ""

        with self.assertRaises(ValueError):
            inspect_review_package(package, **self.package_args())

        mock_inspect.assert_not_called()


    def test_uncertain_upload_confirmed(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            return_value=b"# GPU",
        ):
            result = verify_uncertain_review_upload(
                **self.package_args(),
                path="Retro-Computing/Import/review/test.md",
                local_content=b"# GPU",
            )

        self.assertEqual(result["status"], "CONFIRMED")
        self.assertEqual(
            result["local_sha256"],
            result["remote_sha256"],
        )

    def test_uncertain_upload_missing(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            return_value=None,
        ):
            result = verify_uncertain_review_upload(
                **self.package_args(),
                path="Retro-Computing/Import/review/test.md",
                local_content=b"# GPU",
            )

        self.assertEqual(result["status"], "MISSING")

    def test_uncertain_upload_conflict(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            return_value=b"# Andere GPU",
        ):
            result = verify_uncertain_review_upload(
                **self.package_args(),
                path="Retro-Computing/Import/review/test.md",
                local_content=b"# GPU",
            )

        self.assertEqual(result["status"], "CONFLICT")

    def test_uncertain_upload_network_error(self):
        with patch(
            "llm_import.review_resume.read_review_file",
            side_effect=RuntimeError("Verbindung abgebrochen"),
        ):
            result = verify_uncertain_review_upload(
                **self.package_args(),
                path="Retro-Computing/Import/review/test.md",
                local_content=b"# GPU",
            )

        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["error"], "RuntimeError")

    def test_uncertain_upload_invalid_content_no_network(self):
        with patch(
            "llm_import.review_resume.read_review_file"
        ) as mock_read:
            with self.assertRaises(ValueError):
                verify_uncertain_review_upload(
                    **self.package_args(),
                    path="Retro-Computing/Import/review/test.md",
                    local_content="# GPU",
                )

            mock_read.assert_not_called()


    def test_resume_partially_uploaded_package(self):
        precheck = {
            "mode": "PRECHECK",
            "file_count": 4,
            "results": [
                {"path": "a.md", "status": "UNCHANGED"},
                {"path": "a.review.md", "status": "UNCHANGED"},
                {"path": "b.md", "status": "UPLOAD_REQUIRED"},
                {"path": "b.review.md", "status": "UPLOAD_REQUIRED"},
            ],
        }

        result = plan_package_resume(precheck)

        self.assertEqual(result["status"], "READY")
        self.assertEqual(
            [x["action"] for x in result["decisions"]],
            [
                "SKIP_IDENTICAL",
                "SKIP_IDENTICAL",
                "UPLOAD_CANDIDATE",
                "UPLOAD_CANDIDATE",
            ],
        )

    def test_resume_conflict_blocks_entire_package(self):
        precheck = {
            "mode": "PRECHECK",
            "file_count": 2,
            "results": [
                {"path": "a.md", "status": "UPLOAD_REQUIRED"},
                {"path": "b.md", "status": "CONFLICT"},
            ],
        }

        result = plan_package_resume(precheck)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(
            all(x["action"] == "BLOCK" for x in result["decisions"])
        )

    def test_resume_unknown_blocks_package(self):
        precheck = {
            "mode": "PRECHECK",
            "file_count": 2,
            "results": [
                {"path": "a.md", "status": "UNCHANGED"},
                {"path": "b.md", "status": "UNKNOWN"},
            ],
        }

        result = plan_package_resume(precheck)

        self.assertEqual(result["status"], "BLOCKED")

    def test_resume_rejects_incomplete_precheck(self):
        precheck = {
            "mode": "PRECHECK",
            "file_count": 4,
            "results": [
                {"path": "a.md", "status": "UNCHANGED"},
            ],
        }

        with self.assertRaises(ValueError):
            plan_package_resume(precheck)


    def test_resume_rejects_duplicate_paths(self):
        precheck = {
            "mode": "PRECHECK",
            "file_count": 2,
            "results": [
                {"path": "a.md", "status": "UNCHANGED"},
                {"path": "a.md", "status": "UPLOAD_REQUIRED"},
            ],
        }

        with self.assertRaisesRegex(ValueError, "Doppelter Dateipfad"):
            plan_package_resume(precheck)

    def test_resume_rejects_unknown_status(self):
        precheck = {
            "mode": "PRECHECK",
            "file_count": 1,
            "results": [
                {"path": "a.md", "status": "SUCCESS"},
            ],
        }

        with self.assertRaisesRegex(ValueError, "Unbekannter Dateistatus"):
            plan_package_resume(precheck)

    def test_resume_skipped_blocks_package(self):
        precheck = {
            "mode": "PRECHECK",
            "file_count": 2,
            "results": [
                {"path": "a.md", "status": "UPLOAD_REQUIRED"},
                {"path": "b.md", "status": "SKIPPED"},
            ],
        }

        result = plan_package_resume(precheck)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            [item["action"] for item in result["decisions"]],
            ["BLOCK", "BLOCK"],
        )


if __name__ == "__main__":
    unittest.main()
