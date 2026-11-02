
import unittest

from llm_import.review_resume import (
    decide_review_upload,
    sha256_content,
    inspect_review_upload,
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

if __name__ == "__main__":
    unittest.main()
