import unittest
from urllib import request

from llm_import.nextcloud_review import (
    build_review_put_request,
)
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from llm_import.nextcloud_review import execute_review_put


class TestNextcloudReview(unittest.TestCase):

    def setUp(self):
        self.args = {
            "base_url": "http://127.0.0.1:8080",
            "user": "nina",
            "password": "test-password",
            "path": (
                "Retro-Computing/Import/review/"
                "abcdef1234567890/GV-R92S128T/"
                "GV-R92S128T.md"
            ),
            "content": "# Gigabyte GV-R92S128T",
        }

    def test_valid_request(self):
        request = build_review_put_request(**self.args)

        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(
            request.get_header("If-none-match"),
            "*",
        )
        self.assertIn(
            b"GV-R92S128T",
            request.data,
        )

    def test_rejects_path_outside_review(self):
        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Hardware/Grafikkarten/test.md"
        )

        with self.assertRaises(ValueError):
            build_review_put_request(**args)

    def test_rejects_path_traversal(self):
        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Import/review/"
            "../Hardware/test.md"
        )

        with self.assertRaises(ValueError):
            build_review_put_request(**args)

    def test_rejects_insecure_http(self):
        args = self.args.copy()
        args["base_url"] = "http://nextcloud.example.com"

        with self.assertRaises(ValueError):
            build_review_put_request(**args)

    def test_rejects_empty_content(self):
        args = self.args.copy()
        args["content"] = ""

        with self.assertRaises(ValueError):
            build_review_put_request(**args)

    @patch("llm_import.nextcloud_review.urlopen")
    def test_successful_upload(self, mock_build_opener):
        response = Mock()
        response.status = 201

        opener = mock_build_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        request = build_review_put_request(**self.args)
        result = execute_review_put(request)

        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(result["http_status"], 201)

    @patch("llm_import.nextcloud_review.build_opener")
    def test_successful_upload(self, mock_build_opener):
        response = Mock()
        response.status = 201

        opener = mock_build_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        request = build_review_put_request(**self.args)
        result = execute_review_put(request)

        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(result["http_status"], 201)

        opener.open.assert_called_once()

    @patch("llm_import.nextcloud_review.build_opener")
    def test_existing_file_not_overwritten(self, mock_build_opener):
        opener = mock_build_opener.return_value

        opener.open.side_effect = HTTPError(
            url="http://127.0.0.1:8080",
            code=412,
            msg="Precondition Failed",
            hdrs=None,
            fp=None,
        )

        request = build_review_put_request(**self.args)
        result = execute_review_put(request)

        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["http_status"], 412)

        opener.open.assert_called_once()

    @patch("llm_import.nextcloud_review.build_opener")
    def test_authentication_failure(self, mock_build_opener):
        opener = mock_build_opener.return_value

        opener.open.side_effect = HTTPError(
            url="http://127.0.0.1:8080",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        request = build_review_put_request(**self.args)

        with self.assertRaises(RuntimeError) as context:
            execute_review_put(request)

        self.assertIn("HTTP 401", str(context.exception))

        opener.open.assert_called_once()

    @patch("llm_import.nextcloud_review.build_opener")
    def test_redirect_is_rejected(self, mock_build_opener):
        opener = mock_build_opener.return_value

        opener.open.side_effect = HTTPError(
            url="http://127.0.0.1:8080",
            code=302,
            msg="Found",
            hdrs={"Location": "https://example.org/"},
            fp=None,
        )

        request = build_review_put_request(**self.args)

        with self.assertRaises(RuntimeError) as context:
            execute_review_put(request)

        self.assertIn("HTTP 302", str(context.exception))
        opener.open.assert_called_once()

if __name__ == "__main__":
    unittest.main()