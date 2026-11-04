"""Read-only PDF chunker unit tests; no database connection needed."""
import unittest

import pymupdf

from scripts.pdf_chapter_chunking import (
    CHUNKER_VERSION, extract_chunks, outline_by_page, split_preserving_text,
)


class PdfChapterChunkingTests(unittest.TestCase):
    @staticmethod
    def make_pdf():
        doc = pymupdf.open()
        for text in ("Introduction text. " * 45,
                     "AGP Fast Writes changes bus transactions. " * 55, ""):
            page = doc.new_page()
            for i, start in enumerate(range(0, len(text), 65)):
                if i >= 35:
                    break
                page.insert_text((42, 60 + i * 15), text[start:start + 65])
        doc.set_toc([[1, "Overview", 1], [1, "BIOS Configuration", 2]])
        raw = doc.tobytes()
        doc.close()
        return raw

    def test_splitting_is_lossless_and_bounded(self):
        for value in (("alpha beta\n\n" * 23) + "final", "x" * 111):
            parts = split_preserving_text(value, max_chars=37)
            self.assertEqual("".join(parts), value)
            self.assertTrue(all(len(part) <= 37 for part in parts))

    def test_page_numbers_and_outline(self):
        raw = self.make_pdf()
        chunks, empty_pages = extract_chunks(raw, max_chars=240)
        self.assertEqual(empty_pages, [3])
        self.assertEqual({c.heading for c in chunks if c.page_start == 1}, {"Overview"})
        self.assertEqual({c.heading for c in chunks if c.page_start == 2}, {"BIOS Configuration"})
        self.assertTrue(all(c.page_start == c.page_end for c in chunks))
        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            for number in (1, 2):
                expected = doc[number - 1].get_text("text", sort=True)
                actual = "".join(c.content for c in chunks if c.page_start == number)
                self.assertEqual(actual, expected)

    def test_without_outline_no_guessing(self):
        doc = pymupdf.open()
        doc.new_page().insert_text((42, 60), "Actual text")
        raw = doc.tobytes()
        doc.close()
        chunks, _ = extract_chunks(raw)
        self.assertIsNone(chunks[0].heading)

    def test_nested_bookmarks(self):
        result = outline_by_page([[1, "BIOS", 1], [2, "Advanced", 2]], 3)
        self.assertEqual(result[2], "BIOS / Advanced")

    def test_invalid_limit(self):
        self.assertEqual(CHUNKER_VERSION, "pdf-outline-v1")
        with self.assertRaises(ValueError):
            split_preserving_text("text", 0)


if __name__ == "__main__":
    unittest.main()
