import unittest
from urllib import request

from llm_import.nextcloud_review import (
    build_review_put_request,
)
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from llm_import.nextcloud_review import (
    build_review_put_request,
    NoRedirectHandler,
    upload_review_file,
)
from llm_import.nextcloud_review import (
    build_review_mkcol_request,
    create_review_directory,
    verify_review_directory,
    read_review_file,
)

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

        result = upload_review_file(**self.args)

        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(result["http_status"], 201)

    @patch("llm_import.nextcloud_review.build_opener")
    def test_successful_upload(self, mock_build_opener):
        response = Mock()
        response.status = 201

        opener = mock_build_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        result = upload_review_file(**self.args)

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

        result = upload_review_file(**self.args)

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

        with self.assertRaises(RuntimeError) as context:
            upload_review_file(**self.args)

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

        with self.assertRaises(RuntimeError) as context:
            upload_review_file(**self.args)

        self.assertIn("HTTP 302", str(context.exception))
        opener.open.assert_called_once()

    def test_redirect_handler_blocks_external_redirect(self):
        handler = NoRedirectHandler()

        request = build_review_put_request(**self.args)

        redirected = handler.redirect_request(
            req=request,
            fp=None,
            code=302,
            msg="Found",
            headers={"Location": "https://example.org/"},
            newurl="https://example.org/",
        )

        self.assertIsNone(redirected)

    @patch("llm_import.nextcloud_review.build_opener")
    def test_upload_rejects_unsafe_path_without_network(
        self, mock_build_opener
    ):
        args = self.args.copy()
        args["path"] = "Retro-Computing/Hardware/test.md"

        with self.assertRaises(ValueError):
            upload_review_file(**args)

        mock_build_opener.assert_not_called()

    def test_build_mkcol_request(self):
        args = self.args.copy()

        args["path"] = (
            "Retro-Computing/Import/review/"
            "abcdef1234567890/GV-R92S128T/"
        )
        args.pop("content")

        request = build_review_mkcol_request(**args)

        self.assertEqual(request.get_method(), "MKCOL")
        self.assertTrue(request.full_url.endswith("/GV-R92S128T/"))

    def test_mkcol_rejects_path_traversal(self):
        args = self.args.copy()

        args["path"] = (
            "Retro-Computing/Import/review/"
            "../Hardware/"
        )
        args.pop("content")

        with self.assertRaises(ValueError):
            build_review_mkcol_request(**args)

    @patch("llm_import.nextcloud_review.build_opener")
    def test_mkcol_created(self, mock_build_opener):
        response = Mock()
        response.status = 201

        opener = mock_build_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Import/review/"
            "abcdef1234567890/GV-R92S128T/"
        )
        args.pop("content")

        result = create_review_directory(**args)

        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(result["http_status"], 201)

    @patch("llm_import.nextcloud_review.verify_review_directory")
    @patch("llm_import.nextcloud_review.build_opener")
    def test_mkcol_existing_directory_verified(
        self, mock_build_opener, mock_verify
    ):
        mock_build_opener.return_value.open.side_effect = HTTPError(
            url="http://127.0.0.1:8080",
            code=405,
            msg="Method Not Allowed",
            hdrs=None,
            fp=None,
        )

        mock_verify.return_value = True

        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Import/review/"
            "abcdef1234567890/GV-R92S128T/"
        )
        args.pop("content")

        result = create_review_directory(**args)

        self.assertEqual(result["status"], "EXISTS")
        self.assertEqual(result["http_status"], 405)

        mock_verify.assert_called_once_with(**args)

    @patch("llm_import.nextcloud_review.build_opener")
    def test_propfind_confirms_directory(self, mock_build_opener):
        xml = b"""<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
          <d:response>
          <d:href>/remote.php/dav/files/nina/Retro-Computing/Import/review/abcdef1234567890/GV-R92S128T/</d:href>
            <d:propstat>
              <d:prop>
                <d:resourcetype>
                  <d:collection/>
                </d:resourcetype>
              </d:prop>
              <d:status>HTTP/1.1 200 OK</d:status>
            </d:propstat>
          </d:response>
        </d:multistatus>"""

        response = Mock()
        response.status = 207
        response.read.return_value = xml

        opener = mock_build_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Import/review/"
            "abcdef1234567890/GV-R92S128T/"
        )
        args.pop("content")

        self.assertTrue(verify_review_directory(**args))

    @patch("llm_import.nextcloud_review.build_opener")
    def test_propfind_rejects_file_as_directory(
        self, mock_build_opener
    ):
        xml = b"""<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
          <d:response>
          <d:href>/remote.php/dav/files/nina/Retro-Computing/Import/review/abcdef1234567890/GV-R92S128T/</d:href>
            <d:propstat>
              <d:prop><d:resourcetype/></d:prop>
              <d:status>HTTP/1.1 200 OK</d:status>
            </d:propstat>
          </d:response>
        </d:multistatus>"""

        response = Mock()
        response.status = 207
        response.read.return_value = xml

        opener = mock_build_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Import/review/"
            "abcdef1234567890/GV-R92S128T/"
        )
        args.pop("content")

        self.assertFalse(verify_review_directory(**args))

    @patch("llm_import.nextcloud_review.build_opener")
    def test_propfind_rejects_wrong_directory(self, mock_build_opener):
        xml = b"""<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
          <d:response>
            <d:href>/remote.php/dav/files/nina/Retro-Computing/Hardware/</d:href>
            <d:propstat>
              <d:prop>
                <d:resourcetype>
                  <d:collection/>
                </d:resourcetype>
              </d:prop>
              <d:status>HTTP/1.1 200 OK</d:status>
            </d:propstat>
          </d:response>
        </d:multistatus>"""

        response = Mock()
        response.status = 207
        response.read.return_value = xml

        opener = mock_build_opener.return_value
        opener.open.return_value.__enter__.return_value = response

        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Import/review/"
            "abcdef1234567890/GV-R92S128T/"
        )
        args.pop("content")

        with self.assertRaises(RuntimeError) as context:
            verify_review_directory(**args)

        self.assertIn(
            "gehört nicht zum Zielverzeichnis",
            str(context.exception),
        )

    @patch("llm_import.nextcloud_review.verify_review_directory")
    @patch("llm_import.nextcloud_review.build_opener")
    def test_mkcol_rejects_unverified_directory(
        self, mock_build_opener, mock_verify
    ):
        mock_build_opener.return_value.open.side_effect = HTTPError(
            url="http://127.0.0.1:8080",
            code=405,
            msg="Method Not Allowed",
            hdrs=None,
            fp=None,
        )

        mock_verify.return_value = False

        args = self.args.copy()
        args["path"] = (
            "Retro-Computing/Import/review/"
            "abcdef1234567890/GV-R92S128T/"
        )
        args.pop("content")

        with self.assertRaises(RuntimeError) as context:
            create_review_directory(**args)

        self.assertIn(
            "kein Verzeichnis nachweisbar",
            str(context.exception),
        )

        mock_verify.assert_called_once_with(**args)


    def test_get_existing_review_file(self):
        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            response = Mock()
            response.status = 200
            response.read.return_value = b"# GPU"

            mock_opener.return_value.open.return_value.__enter__.return_value = (
                response
            )

            args = self.args.copy()
            args.pop("content")

            result = read_review_file(**args)

            self.assertEqual(result, b"# GPU")

            request = mock_opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")

    def test_get_missing_review_file(self):
        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            mock_opener.return_value.open.side_effect = HTTPError(
                url="http://127.0.0.1:8080",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=None,
            )

            args = self.args.copy()
            args.pop("content")

            self.assertIsNone(read_review_file(**args))

    def test_get_empty_file_is_not_missing(self):
        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            response = Mock()
            response.status = 200
            response.read.return_value = b""

            mock_opener.return_value.open.return_value.__enter__.return_value = (
                response
            )

            args = self.args.copy()
            args.pop("content")

            self.assertEqual(read_review_file(**args), b"")

    def test_get_rejects_oversized_file(self):
        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            response = Mock()
            response.status = 200
            response.read.return_value = b"x" * (2 * 1024 * 1024 + 1)

            mock_opener.return_value.open.return_value.__enter__.return_value = (
                response
            )

            args = self.args.copy()
            args.pop("content")

            with self.assertRaisesRegex(
                RuntimeError, "Leselimit"
            ):
                read_review_file(**args)

    def test_get_rejects_unsafe_path_without_network(self):
        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            args = self.args.copy()
            args.pop("content")
            args["path"] = "Retro-Computing/Hardware/test.md"

            with self.assertRaises(ValueError):
                read_review_file(**args)

            mock_opener.assert_not_called()


    def test_get_permission_denied(self):
        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            mock_opener.return_value.open.side_effect = HTTPError(
                url="http://127.0.0.1:8080",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=None,
            )

            args = self.args.copy()
            args.pop("content")

            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                read_review_file(**args)

    def test_get_redirect_rejected(self):
        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            mock_opener.return_value.open.side_effect = HTTPError(
                url="http://127.0.0.1:8080",
                code=302,
                msg="Found",
                hdrs=None,
                fp=None,
            )

            args = self.args.copy()
            args.pop("content")

            with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
                read_review_file(**args)

    def test_get_network_failure(self):
        from urllib.error import URLError

        with patch(
            "llm_import.nextcloud_review.build_opener"
        ) as mock_opener:
            mock_opener.return_value.open.side_effect = URLError(
                "Connection refused"
            )

            args = self.args.copy()
            args.pop("content")

            with self.assertRaisesRegex(
                RuntimeError, "WebDAV-Verbindung"
            ):
                read_review_file(**args)


    @patch("llm_import.nextcloud_review.build_opener")
    def test_put_http_409_is_error(self, mock_opener):
        mock_opener.return_value.open.side_effect = HTTPError(
            url="http://127.0.0.1:8080",
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=None,
        )

        with self.assertRaisesRegex(
            RuntimeError, "HTTP 409"
        ):
            upload_review_file(**self.args)

    @patch("llm_import.nextcloud_review.build_opener")
    def test_put_http_412_is_conflict(self, mock_opener):
        mock_opener.return_value.open.side_effect = HTTPError(
            url="http://127.0.0.1:8080",
            code=412,
            msg="Precondition Failed",
            hdrs=None,
            fp=None,
        )

        result = upload_review_file(**self.args)

        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["http_status"], 412)


if __name__ == "__main__":
    unittest.main()