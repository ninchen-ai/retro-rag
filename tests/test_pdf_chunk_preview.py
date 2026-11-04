"""Read-only chunk preview retains all page text and never verifies anchors."""
import unittest
import pymupdf

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

    def test_empty_page_is_reported(self):
        raw = fixture([[], [(80, "Text on the second page", 11)]])
        preview = preview_section_chunks(raw)
        self.assertEqual(preview.empty_pages, (1,))
        self.assertTrue(preview.lossless)


if __name__ == "__main__":
    unittest.main()
