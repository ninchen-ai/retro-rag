
import unittest

from llm_import.review_apply import execute_review_package
from llm_import.review_package import plan_review_package


class FakeTransport:
    """Speicherbasierter Ersatz für Nextcloud."""

    def __init__(self, existing=None, fail_upload_at=None):
        self.files = dict(existing or {})
        self.upload_count = 0
        self.fail_upload_at = fail_upload_at
        self.uploaded_paths = []

    def read(self, path):
        return self.files.get(path)

    def verify_directory(self, path):
        return path == "Retro-Computing/Import/review/"

    def create_directory(self, path):
        return "CREATED"

    def upload(self, path, content):
        self.upload_count += 1

        if self.upload_count == self.fail_upload_at:
            raise RuntimeError("Simulierter Uploadfehler")

        if path in self.files:
            return "CONFLICT"

        self.files[path] = content
        self.uploaded_paths.append(path)
        return "CREATED"


class TestReviewApply(unittest.TestCase):

    def setUp(self):
        self.package = {
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
        self.planned = plan_review_package(self.package)

    def test_complete_first_upload(self):
        transport = FakeTransport()

        result = execute_review_package(
            self.package,
            transport=transport,
        )

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(transport.upload_count, 4)
        self.assertEqual(
            sum(x["status"] == "CONFIRMED" for x in result["results"]),
            4,
        )

    def test_resume_skips_identical_files(self):
        existing = {
            entry["path"]: entry["content"].encode("utf-8")
            for entry in self.planned[:2]
        }

        transport = FakeTransport(existing=existing)

        result = execute_review_package(
            self.package,
            transport=transport,
        )

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(transport.upload_count, 2)
        self.assertEqual(
            sum(x["status"] == "UNCHANGED" for x in result["results"]),
            2,
        )

    def test_upload_failure_stops_remaining_actions(self):
        transport = FakeTransport(fail_upload_at=2)

        result = execute_review_package(
            self.package,
            transport=transport,
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(transport.upload_count, 2)
        self.assertEqual(
            sum(x["status"] == "SKIPPED" for x in result["results"]),
            2,
        )
        self.assertEqual(len(transport.files), 1)

    def test_upload_exception_after_success_is_confirmed(self):
        transport = FakeTransport()

        original_upload = transport.upload

        def upload_then_disconnect(path, content):
            original_upload(path, content)
            raise RuntimeError("Verbindung nach Upload abgebrochen")

        transport.upload = upload_then_disconnect

        result = execute_review_package(
            self.package,
            transport=transport,
        )

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(len(transport.files), 4)
        self.assertEqual(
            sum(
                item["status"] == "CONFIRMED"
                for item in result["results"]
            ),
            4,
        )

    def test_upload_exception_without_saved_file_fails(self):
        transport = FakeTransport()

        def disconnect_without_saving(path, content):
            raise RuntimeError("Verbindung vor Upload abgebrochen")

        transport.upload = disconnect_without_saving

        result = execute_review_package(
            self.package,
            transport=transport,
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(transport.files), 0)
        self.assertEqual(
            sum(
                item["status"] == "SKIPPED"
                for item in result["results"]
            ),
            3,
        )

if __name__ == "__main__":
    unittest.main()
