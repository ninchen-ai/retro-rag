"""Bookmark anchor diagnostic tests: split text rectangles and page rotation."""
import unittest
import pymupdf

from experiments.pdf_bookmark_anchor_audit import title_variants, bookmark_target_y, audit_bookmarks


class BookmarkAnchorAuditTests(unittest.TestCase):
    def test_root_title_number_variant(self):
        self.assertEqual(title_variants("Introduction 1"), ["Introduction 1", "1 Introduction"])

    def test_regular_title_kept(self):
        self.assertEqual(title_variants("1.1 Terminology"), ["1.1 Terminology"])

    def test_destination_y_unrotated(self):
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        self.assertEqual(bookmark_target_y(page, {"to": pymupdf.Point(71, 699)}), 93)
        page.set_rotation(90)
        self.assertIsNone(bookmark_target_y(page, {"to": pymupdf.Point(71, 699)}))
        doc.close()

    def test_missing_bookmark_title_is_reported_not_approved(self):
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "Missing heading", 1]])
        report = audit_bookmarks(doc.tobytes())
        self.assertFalse(report["approved"])
        self.assertEqual(report["bookmark_count"], 1)
        self.assertEqual(report["status_counts"].get("TEXT_NOT_FOUND", 0) +
                         report["status_counts"].get("UNSUPPORTED_DESTINATION", 0), 1)
        doc.close()


if __name__ == "__main__":
    unittest.main()
