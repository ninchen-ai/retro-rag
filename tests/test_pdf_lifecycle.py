
import unittest
from unittest.mock import MagicMock, patch
from scripts.sync_pdfs import (
    update_missing_lifecycle,
    reactivate_pdf,
    pdf_is_unchanged,
)

class TestPdfLifecycle(unittest.TestCase):

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_pending_dry_run(self, mock_connect):
        conn = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor

        # Dokument existiert und ist aktiv;
        # bisher liegt keine Fehlvormerkung vor.
        cursor.fetchone.side_effect = [
            (True,),
            None,
        ]

        result = update_missing_lifecycle(
            document_id=1018,
            password="test-password",
            dry_run=True,
        )

        self.assertEqual(result, "PENDING")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

        executed_sql = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]

        self.assertTrue(
            any(
                "INSERT INTO knowledge.pdf_missing_state" in sql
                for sql in executed_sql
            )
        )

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_waiting_dry_run(self, mock_connect):
        from datetime import datetime, timedelta, timezone

        conn = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor

        now = datetime.now(timezone.utc)

        cursor.fetchone.side_effect = [
            (True,),
            (now - timedelta(minutes=5), now),
        ]

        result = update_missing_lifecycle(
            document_id=1018,
            password="test-password",
            dry_run=True,
        )

        self.assertEqual(result, "WAITING")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

        executed_sql = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]

        self.assertFalse(
            any(
                "SET is_active = false" in sql
                for sql in executed_sql
            )
        )

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_deactivated_dry_run(self, mock_connect):
        from datetime import datetime, timedelta, timezone

        conn = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor

        now = datetime.now(timezone.utc)

        cursor.fetchone.side_effect = [
            (True,),
            (now - timedelta(minutes=15), now),
        ]

        result = update_missing_lifecycle(
            document_id=1018,
            password="test-password",
            dry_run=True,
        )

        self.assertEqual(result, "DEACTIVATED")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

        executed_sql = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]

        self.assertTrue(
            any(
                "SET is_active = false" in sql
                for sql in executed_sql
            )
        )

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_already_inactive_dry_run(self, mock_connect):
        from datetime import datetime, timedelta, timezone

        conn = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor

        now = datetime.now(timezone.utc)

        cursor.fetchone.side_effect = [
            (False,),
            (now - timedelta(minutes=15), now),
        ]

        result = update_missing_lifecycle(
            document_id=1018,
            password="test-password",
            dry_run=True,
        )

        self.assertEqual(result, "ALREADY_INACTIVE")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

        executed_sql = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]

        self.assertFalse(
            any(
                "SET is_active = false" in sql
                for sql in executed_sql
            )
        )

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_reactivate_dry_run(self, mock_connect):
        conn = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor

        # Dokument ist bisher deaktiviert.
        cursor.fetchone.side_effect = [
            (False, "176", "/old.pdf"), ("etag-123", 4096), (10, 2, 0, 1)
        ]

        result = reactivate_pdf(
            document_id=1018,
            password="test-password",
            expected_etag="etag-123",
            expected_size=4096,
            expected_file_id="176",
            expected_path="/old.pdf",
            dry_run=True,
        )

        self.assertEqual(result, "REACTIVATED")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

        executed_sql = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]

        self.assertTrue(any(
            "SET is_active = true" in sql
            for sql in executed_sql
        ))

        self.assertTrue(any(
            "DELETE FROM knowledge.pdf_missing_state" in sql
            for sql in executed_sql
        ))

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_already_active_dry_run(self, mock_connect):
        conn = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor

        # Dokument ist bereits aktiv.
        cursor.fetchone.side_effect = [
            (True, "177", "/new.pdf"), ("etag-456", 8192), (10, 2, 0, 1)
        ]

        result = reactivate_pdf(
            document_id=1019,
            password="test-password",
            expected_etag="etag-456",
            expected_size=8192,
            expected_file_id="177",
            expected_path="/new.pdf",
            dry_run=True,
        )

        self.assertEqual(result, "ALREADY_ACTIVE")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

        executed_sql = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]

        self.assertFalse(any(
            "SET is_active = false" in sql
            for sql in executed_sql
        ))

        self.assertTrue(any(
            "DELETE FROM knowledge.pdf_missing_state" in sql
            for sql in executed_sql
        ))

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_reactivation_rejects_changed_etag(self, mock_connect):
        conn, cursor = MagicMock(), MagicMock()
        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(False, "176", "/old.pdf"), ("other-etag", 4096)]
        with self.assertRaisesRegex(RuntimeError, "PDF-Version"):
            reactivate_pdf(1018, "password", "etag-123", 4096, "176", "/old.pdf", dry_run=False)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        sql = " ".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertNotIn("SET is_active = true", sql)

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_reactivation_rejects_bad_index(self, mock_connect):
        conn, cursor = MagicMock(), MagicMock()
        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            (False, "176", "/old.pdf"), ("etag-123", 4096), (10, 2, 0, 3)
        ]
        with self.assertRaisesRegex(RuntimeError, "Index"):
            reactivate_pdf(1018, "password", "etag-123", 4096, "176", "/old.pdf", dry_run=False)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_reactivation_commit(self, mock_connect):
        conn, cursor = MagicMock(), MagicMock()
        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            (False, "176", "/old.pdf"), ("etag-123", 4096), (10, 2, 0, 1)
        ]
        self.assertEqual(
            reactivate_pdf(1018, "password", "etag-123", 4096, "176", "/old.pdf", dry_run=False),
            "REACTIVATED",
        )
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_deactivation_commit(self, mock_connect):
        from datetime import datetime, timedelta, timezone
        conn, cursor = MagicMock(), MagicMock()
        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        now = datetime.now(timezone.utc)
        cursor.fetchone.side_effect = [
            (True,), (now - timedelta(minutes=11), now)
        ]
        self.assertEqual(
            update_missing_lifecycle(1018, "password", dry_run=False),
            "DEACTIVATED",
        )
        conn.commit.assert_called_once()
        sql = " ".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn("SET is_active = false", sql)

    @patch("scripts.sync_pdfs.psycopg.connect")
    def test_first_missing_scan_does_not_deactivate(self, mock_connect):
        conn, cursor = MagicMock(), MagicMock()
        mock_connect.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(True,), None]
        self.assertEqual(
            update_missing_lifecycle(1018, "password", dry_run=False),
            "PENDING",
        )
        conn.commit.assert_called_once()
        sql = " ".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertNotIn("SET is_active = false", sql)

    def test_pdf_unchanged(self):
        existing = {
            "path": "/Retro-Computing/Handbuch.pdf",
            "etag": "etag-123",
            "size": 4096,
            "page_count": 10,
            "chunk_count": 25,
        }

        item = {
            "path": "/Retro-Computing/Handbuch.pdf",
            "etag": "etag-123",
            "size": 4096,
        }

        self.assertTrue(pdf_is_unchanged(item, existing))

    def test_pdf_changed_etag(self):
        existing = {
            "path": "/Retro-Computing/Handbuch.pdf",
            "etag": "etag-123",
            "size": 4096,
            "page_count": 10,
            "chunk_count": 25,
        }

        item = {
            "path": "/Retro-Computing/Handbuch.pdf",
            "etag": "etag-456",
            "size": 4096,
        }

        self.assertFalse(pdf_is_unchanged(item, existing))

if __name__ == "__main__":
    unittest.main()
