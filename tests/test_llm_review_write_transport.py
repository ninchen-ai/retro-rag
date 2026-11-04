
import unittest
from unittest.mock import Mock

from llm_import.review_write_transport import (
    NextcloudReviewWriteTransport,
)


class TestReviewWriteTransport(unittest.TestCase):

    def setUp(self):
        self.mkcol = Mock(
            return_value={"status": "CREATED", "http_status": 201}
        )
        self.put = Mock(
            return_value={"status": "CREATED", "http_status": 201}
        )

        self.transport = NextcloudReviewWriteTransport(
            base_url="http://127.0.0.1:8080",
            user="nina",
            password="test",
            mkcol=self.mkcol,
            put=self.put,
        )

    def test_create_directory(self):
        result = self.transport.create_directory(
            "Retro-Computing/Import/review/test/"
        )

        self.assertEqual(result, "CREATED")
        self.mkcol.assert_called_once()

    def test_existing_directory(self):
        self.mkcol.return_value = {
            "status": "EXISTS",
            "http_status": 405,
        }

        result = self.transport.create_directory(
            "Retro-Computing/Import/review/test/"
        )

        self.assertEqual(result, "EXISTS")

    def test_directory_failure(self):
        self.mkcol.side_effect = RuntimeError("HTTP 403")

        with self.assertRaises(RuntimeError):
            self.transport.create_directory(
                "Retro-Computing/Import/review/test/"
            )

    def test_upload(self):
        result = self.transport.upload(
            "Retro-Computing/Import/review/test.md",
            b"# Testdatei",
        )

        self.assertEqual(result, "CREATED")
        self.put.assert_called_once()

        self.assertEqual(
            self.put.call_args.kwargs["content"],
            "# Testdatei",
        )

    def test_upload_conflict(self):
        self.put.return_value = {
            "status": "CONFLICT",
            "http_status": 412,
        }

        with self.assertRaises(RuntimeError):
            self.transport.upload(
                "Retro-Computing/Import/review/test.md",
                b"# Testdatei",
            )

    def test_upload_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            self.transport.upload(
                "Retro-Computing/Import/review/test.md",
                "# Testdatei",
            )

        self.put.assert_not_called()

    def test_missing_write_functions(self):
        with self.assertRaises(TypeError):
            NextcloudReviewWriteTransport(
                base_url="http://127.0.0.1:8080",
                user="nina",
                password="test",
                mkcol=None,
                put=None,
            )

    def test_upload_rejects_unsafe_paths(self):
        invalid_paths = [
            "../test.md",
            "Retro-Computing/Import/test.md",
            "Retro-Computing/Import/review/../test.md",
            "Retro-Computing/Import/review/test.txt",
            "Retro-Computing/Import/review/test//file.md",
        ]

        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.transport.upload(path, b"# Test")

        self.put.assert_not_called()

    def test_mkcol_rejects_unsafe_paths(self):
        invalid_paths = [
            "../test/",
            "Retro-Computing/Import/test/",
            "Retro-Computing/Import/review/../test/",
            "Retro-Computing/Import/review/test//",
            "Retro-Computing/Import/review/test",
            "Retro-Computing/Import/review/",
        ]

        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.transport.create_directory(path)

        self.mkcol.assert_not_called()


if __name__ == "__main__":
    unittest.main()
