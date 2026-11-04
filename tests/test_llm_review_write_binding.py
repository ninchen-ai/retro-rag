import unittest
from unittest.mock import patch

from llm_import.nextcloud_review import (
    create_review_directory,
    upload_review_file,
    build_review_put_request,
)
from llm_import.review_write_transport import (
    NextcloudReviewWriteTransport,
)


class TestReviewWriteBinding(unittest.TestCase):

    def test_bind_existing_webdav_functions(self):
        with (
            patch("llm_import.nextcloud_review.build_opener") as opener,
        ):
            response = opener.return_value.open.return_value
            response.__enter__.return_value.status = 201

            transport = NextcloudReviewWriteTransport(
                base_url="http://127.0.0.1:8080",
                user="nina",
                password="test",
                mkcol=create_review_directory,
                put=upload_review_file,
            )

            directory = (
                "Retro-Computing/Import/review/"
                "integration-test/"
            )
            file_path = directory + "test.md"

            self.assertEqual(
                transport.create_directory(directory),
                "CREATED",
            )

            self.assertEqual(
                transport.upload(file_path, b"# Test"),
                "CREATED",
            )

            requests = [
                call.args[0]
                for call in opener.return_value.open.call_args_list
            ]

            self.assertEqual(
                [request.get_method() for request in requests],
                ["MKCOL", "PUT"],
            )

            self.assertEqual(
                requests[1].get_header("If-none-match"),
                "*",
            )


if __name__ == "__main__":
    unittest.main()