
import unittest
from unittest.mock import patch, Mock
from hashlib import sha256

from scripts import apply_review_package as app


class TestReviewApproval(unittest.TestCase):

    def setUp(self):
        self.cache_bytes = b'{"test": true}'
        self.cache_hash = sha256(self.cache_bytes).hexdigest()

        self.preview = {
            "status": "READY",
            "source_sha256": app.SOURCE_SHA,
            "files": [],
            "write_operations": 0,
        }

    @patch.object(app, "execute_review_package")
    @patch.object(app, "NextcloudReviewWriteTransport")
    @patch.object(app, "build_review_preview")
    @patch.object(app, "NextcloudReviewTransport")
    @patch.object(app, "load_package")
    @patch.object(app, "getpass")
    @patch("scripts.apply_review_package.Path.read_bytes")
    @patch("sys.argv", ["apply_review_package.py"])
    def test_without_apply_no_writes(
        self,
        mock_read,
        mock_password,
        mock_load,
        mock_reader,
        mock_preview,
        mock_writer,
        mock_execute,
    ):
        mock_read.return_value = self.cache_bytes
        mock_load.return_value = {"results": []}
        mock_preview.return_value = self.preview

        app.main()

        mock_writer.assert_not_called()
        mock_execute.assert_not_called()
        mock_read.assert_called_once()

    @patch.object(app, "execute_review_package")
    @patch.object(app, "NextcloudReviewWriteTransport")
    @patch.object(app, "build_review_preview")
    @patch.object(app, "NextcloudReviewTransport")
    @patch.object(app, "load_package")
    @patch.object(app, "getpass")
    @patch("scripts.apply_review_package.Path.read_bytes")
    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value=app.CONFIRMATION)
    @patch("sys.argv", ["apply_review_package.py", "--apply"])
    def test_changed_cache_prevents_upload(
        self,
        mock_input,
        mock_tty,
        mock_read,
        mock_password,
        mock_load,
        mock_reader,
        mock_preview,
        mock_writer,
        mock_execute,
    ):
        mock_read.side_effect = [
            self.cache_bytes,
            b'{"test": false}',
        ]
        mock_load.return_value = {"results": []}
        mock_preview.return_value = self.preview

        with self.assertRaises(SystemExit):
            app.main()

        mock_writer.assert_not_called()
        mock_execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
