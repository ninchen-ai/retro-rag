"""Read-only chunk preview retains all page text and never verifies anchors."""
import unittest
import pymupdf
from unittest.mock import patch

from scripts.pdf_heading_review import ReviewHeading, ReviewReport
from scripts.pdf_heading_alignment import HeadingAlignment

from scripts.pdf_chunk_preview import preview_section_chunks


def fixture(pages):
    doc = pymupdf.open()
    for page_lines in pages:
        page = doc.new_page()
        for y, value, size in page_lines:
            page.insert_text((54, y), value, fontname="hebo", fontsize=size)
    raw = doc.tobytes()
    doc.close()
    return raw


class ChunkPreviewTests(unittest.TestCase):
    def test_numbered_sections_preserve_every_character(self):
        raw = fixture([
            [(80, "1 Introduction and Overview", 18), (120, "1.1 Scope and Objectives", 14),
             (160, "Some content follows.", 11)],
            [(80, "2 Description of Features", 18), (120, "More content.", 11)],
        ])
        preview = preview_section_chunks(raw, max_chars=35)
        self.assertEqual(preview.style, "numbered")
        self.assertTrue(preview.lossless)
        self.assertFalse(preview.verified)
        self.assertGreater(preview.matched_headings, 1)
        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            for number, page in enumerate(doc, 1):
                actual = "".join(c.content for c in preview.chunks if c.page_start == number)
                self.assertEqual(actual, page.get_text("text", sort=True))

    def test_separated_chapters_get_hierarchy_without_rewriting_text(self):
        raw = fixture([
            [(140, "Chapter 1", 16), (174, "AGP Electrical Design Considerations", 14),
             (210, "Signal Termination", 12), (245, "Explanation of the signals", 10)],
            [(140, "Chapter 2", 16), (174, "Board Design Guidelines", 14)],
        ])
        preview = preview_section_chunks(raw)
        self.assertEqual(preview.style, "separated")
        self.assertTrue(preview.lossless)
        self.assertTrue(any(c.heading and "Chapter 1:" in c.heading for c in preview.chunks))

    def test_page_order_alignment_not_zipped_to_grouped_chapters(self):
        raw = fixture([
            [(80, "1. Introduction", 22)],
            [(80, "1.1 Motivation", 16)],
            [(80, "2. Architectural Context and Scope", 22)],
        ])
        headings = (
            ReviewHeading(1, 1, "1. Introduction", "dotted chapter", "1", "REVIEW REQUIRED"),
            ReviewHeading(3, 1, "2. Architectural Context and Scope", "dotted chapter", "2", "REVIEW REQUIRED"),
            ReviewHeading(2, 2, "1.1 Motivation", "visual y=1", "1.1", "REVIEW REQUIRED"),
        )
        # This is the real ordering mismatch: the aligner returns page order.
        alignments = [
            HeadingAlignment(1, headings[0].heading, headings[0].source, "MATCHED", 0, 1, None),
            HeadingAlignment(2, headings[2].heading, headings[2].source, "MATCHED", 0, 1, None),
            HeadingAlignment(3, headings[1].heading, headings[1].source, "MATCHED", 0, 1, None),
        ]
        with patch("scripts.pdf_chunk_preview.build_heading_review", return_value=ReviewReport("dotted", headings, ())), \
             patch("scripts.pdf_chunk_preview.align_document_headings", return_value=alignments):
            preview = preview_section_chunks(raw)
        self.assertEqual(preview.matched_headings, 3)
        self.assertTrue(preview.lossless)
        page2 = [c for c in preview.chunks if c.page_start == 2]
        self.assertTrue(all("1.1 Motivation" in c.heading for c in page2))
        self.assertFalse(any("2. Architectural" in c.heading for c in page2))

    def test_two_headings_on_one_line_are_skipped_not_crash(self):
        raw = fixture([[(80, "Chapter body", 11)]])
        headings = (
            ReviewHeading(1, 1, "1 First Chapter", "visual", "1", "REVIEW REQUIRED"),
            ReviewHeading(1, 2, "1.1 Other Section", "visual", "1.1", "REVIEW REQUIRED"),
        )
        matches = [
            HeadingAlignment(1, h.heading, h.source, "MATCHED", 0, 1, None)
            for h in headings
        ]
        with patch("scripts.pdf_chunk_preview.build_heading_review", return_value=ReviewReport("numbered", headings, ())), \
             patch("scripts.pdf_chunk_preview.align_document_headings", return_value=matches):
            preview = preview_section_chunks(raw)
        self.assertEqual(preview.matched_headings, 0)
        self.assertEqual(len(preview.skipped_headings), 2)
        self.assertTrue(all("CONFLICTING_ANCHOR" in s for s in preview.skipped_headings))
        self.assertTrue(preview.lossless)
        self.assertTrue(all(c.heading is None for c in preview.chunks))

    def test_empty_page_is_reported(self):
        raw = fixture([[], [(80, "Text on the second page", 11)]])
        preview = preview_section_chunks(raw)
        self.assertEqual(preview.empty_pages, (1,))
        self.assertTrue(preview.lossless)


if __name__ == "__main__":
    unittest.main()
