
import unittest

from llm_import.review_resume import (
    decide_review_upload,
    sha256_content,
    inspect_review_upload,
    inspect_review_package,
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


if __name__ == "__main__":
    unittest.main()
