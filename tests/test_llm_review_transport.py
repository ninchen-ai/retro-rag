
import unittest
from unittest.mock import patch

from llm_import.review_transport import NextcloudReviewTransport


class TestReviewTransport(unittest.TestCase):

    def setUp(self):
        self.transport = NextcloudReviewTransport(
            base_url="http://127.0.0.1:8080",
            user="nina",
            password="test",
        )

    @patch("llm_import.review_transport.read_review_file")
    def test_read_uses_webdav(self, mock_read):
        mock_read.return_value = b"# GPU"

        result = self.transport.read(
            "Retro-Computing/Import/review/test.md"
        )

        self.assertEqual(result, b"# GPU")
        mock_read.assert_called_once()

    @patch("llm_import.review_transport.verify_review_directory")
    def test_directory_check_uses_webdav(self, mock_verify):
        mock_verify.return_value = True

        result = self.transport.verify_directory(
            "Retro-Computing/Import/review/"
        )

        self.assertTrue(result)
        mock_verify.assert_called_once()

    def test_writes_are_disabled(self):
        with self.assertRaises(RuntimeError):
            self.transport.create_directory(
                "Retro-Computing/Import/review/test/"
            )

        with self.assertRaises(RuntimeError):
            self.transport.upload(
                "Retro-Computing/Import/review/test.md",
                b"# GPU",
            )


if __name__ == "__main__":
    unittest.main()
