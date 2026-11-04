
import unittest
from unittest.mock import Mock, patch

from llm_import.review_transport import NextcloudReviewTransport
from llm_import.nextcloud_review import verify_review_directory


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

    @patch("llm_import.nextcloud_review.build_opener")
    def test_propfind_allows_review_root(self, mock_opener):
        root = "Retro-Computing/Import/review/"

        response = Mock()
        response.status = 207
        response.read.return_value = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<d:multistatus xmlns:d="DAV:">'
            b'<d:response>'
            b'<d:href>'
            b'/remote.php/dav/files/nina/'
            b'Retro-Computing/Import/review/'
            b'</d:href>'
            b'<d:propstat>'
            b'<d:prop>'
            b'<d:resourcetype><d:collection/></d:resourcetype>'
            b'</d:prop>'
            b'<d:status>HTTP/1.1 200 OK</d:status>'
            b'</d:propstat>'
            b'</d:response>'
            b'</d:multistatus>'
        )

        opener = mock_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        result = verify_review_directory(
            base_url="http://127.0.0.1:8080",
            user="nina",
            password="test",
            path=root,
        )

        self.assertTrue(result)

        request = opener.open.call_args.args[0]

        self.assertEqual(request.get_method(), "PROPFIND")
        self.assertTrue(request.full_url.endswith(root))

if __name__ == "__main__":
    unittest.main()
