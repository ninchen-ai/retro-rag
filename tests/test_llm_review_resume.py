
import unittest

from llm_import.review_resume import (
    decide_review_upload,
    sha256_content,
)


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


if __name__ == "__main__":
    unittest.main()
