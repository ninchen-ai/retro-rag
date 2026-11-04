
import unittest

from llm_import.review_preview import build_review_preview


class PreviewTransport:
    def __init__(self, files=None, root_exists=True):
        self.files = files or {}
        self.root_exists = root_exists

    def verify_directory(self, path):
        return self.root_exists

    def read(self, path):
        return self.files.get(path)

    def create_directory(self, path):
        raise AssertionError("Schreiboperation MKCOL verboten")

    def upload(self, path, content):
        raise AssertionError("Schreiboperation PUT verboten")


class TestReviewPreview(unittest.TestCase):

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

    def test_first_import_preview(self):
        preview = build_review_preview(
            self.package,
            transport=PreviewTransport(),
        )

        self.assertEqual(preview["mode"], "READ_ONLY")
        self.assertEqual(preview["status"], "READY")
        self.assertEqual(len(preview["models"]), 2)
        self.assertEqual(len(preview["files"]), 4)
        self.assertEqual(preview["write_operations"], 0)

        self.assertTrue(all(
            item["status"] == "UPLOAD_REQUIRED"
            for item in preview["files"]
        ))

    def test_conflict_blocks_preview(self):
        first_path = (
            "Retro-Computing/Import/review/"
            + "a" * 16
            + "/GV-R92S128T/GV-R92S128T.md"
        )

        transport = PreviewTransport(
            files={first_path: b"# Abweichender Inhalt"}
        )

        preview = build_review_preview(
            self.package,
            transport=transport,
        )

        self.assertEqual(preview["status"], "BLOCKED")
        self.assertEqual(preview["files"][0]["status"], "CONFLICT")
        self.assertEqual(preview["write_operations"], 0)

    def test_missing_root_blocks_preview(self):
        preview = build_review_preview(
            self.package,
            transport=PreviewTransport(root_exists=False),
        )

        self.assertEqual(preview["status"], "BLOCKED")
        self.assertEqual(
            preview["reason"],
            "REVIEW_ROOT_MISSING",
        )
        self.assertEqual(preview["write_operations"], 0)


if __name__ == "__main__":
    unittest.main()
