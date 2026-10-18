"""Isolierte Hauptablauftests ohne Nextcloud, Ollama oder PostgreSQL."""
import os
import sys
import unittest
from unittest.mock import patch

from scripts.sync_pdfs import main


class TestPdfSyncFlow(unittest.TestCase):
    def setUp(self):
        self.credentials = patch.dict(os.environ, {
            "NEXTCLOUD_APP_PASSWORD": "test-nextcloud",
            "PGPASSWORD": "test-ingest",
            "RETRO_RAG_READER_PASSWORD": "test-reader",
        })
        self.argv = patch.object(sys, "argv", ["sync_pdfs.py", "--apply"])
        self.credentials.start()
        self.argv.start()
        self.addCleanup(self.credentials.stop)
        self.addCleanup(self.argv.stop)

    @staticmethod
    def old_document(active=True):
        return {
            "id": 1018, "fileid": "176", "is_active": active,
            "document_key": "manual-nc-176",
            "path": "/remote.php/dav/files/nina/Retro-Computing/old.pdf",
            "etag": '"old"', "size": 1000, "page_count": 1,
            "chunk_count": 1,
        }

    @staticmethod
    def current_file():
        return {
            "fileid": "177",
            "path": "/remote.php/dav/files/nina/Retro-Computing/new.pdf",
            "etag": '"new"', "size": 1000, "modified": None,
        }

    @patch("scripts.sync_pdfs.update_missing_lifecycle", return_value="PENDING")
    @patch("scripts.sync_pdfs.check_webdav_path", return_value="MISSING")
    @patch("scripts.sync_pdfs.get_known_pdfs")
    @patch("scripts.sync_pdfs.discover", return_value=[])
    def test_orphan_gets_pending_only_after_double_scan(
        self, discover, known, check_path, lifecycle
    ):
        known.return_value = {"176": self.old_document()}
        main()
        self.assertEqual(discover.call_count, 2)
        lifecycle.assert_called_once_with(1018, "test-ingest", dry_run=False)

    @patch("scripts.sync_pdfs.update_missing_lifecycle")
    @patch("scripts.sync_pdfs.check_webdav_path", return_value="MATCH")
    @patch("scripts.sync_pdfs.get_known_pdfs")
    @patch("scripts.sync_pdfs.discover", return_value=[])
    def test_orphan_with_existing_webdav_path_not_deactivated(
        self, discover, known, check_path, lifecycle
    ):
        known.return_value = {"176": self.old_document()}
        main()
        lifecycle.assert_not_called()

    @patch("scripts.sync_pdfs.update_missing_lifecycle")
    @patch("scripts.sync_pdfs.get_known_pdfs")
    @patch("scripts.sync_pdfs.discover")
    def test_different_scans_abort_before_lifecycle_changes(
        self, discover, known, lifecycle
    ):
        known.return_value = {}
        discover.side_effect = [[], [self.current_file()]]
        with self.assertRaisesRegex(RuntimeError, "während der Scans"):
            main()
        lifecycle.assert_not_called()

    @patch("scripts.sync_pdfs.reactivate_pdf", return_value="REACTIVATED")
    @patch("scripts.sync_pdfs.pdf_ready_for_reactivation", return_value=True)
    @patch("scripts.sync_pdfs.get_known_pdfs")
    @patch("scripts.sync_pdfs.discover")
    @patch("scripts.sync_pdfs.import_document")
    def test_new_pdf_imported_and_reactivated_after_validation(
        self, imported, discover, known, ready, reactivate
    ):
        f = self.current_file()
        entry = self.old_document(active=False)
        entry.update({
            "id": 1019, "fileid": "177", "document_key": "manual-nc-177",
            "path": f["path"],
            "etag": f["etag"], "size": f["size"],
        })
        discover.return_value = [f]
        known.side_effect = [{}, {"177": entry}]
        main()
        imported.assert_called_once()
        reactivate.assert_called_once_with(
            1019, "test-ingest", '"new"', 1000,
            "177", f["path"], dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
