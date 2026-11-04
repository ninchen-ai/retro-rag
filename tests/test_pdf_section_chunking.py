"""Verified PDF section chunking: integrity, hierarchy and failure cases."""
import unittest

import pymupdf

from scripts.pdf_section_chunking import extract_verified_section_chunks


class SectionChunkTests(unittest.TestCase):
    @staticmethod
    def fixture():
        document = pymupdf.open()
        for entries in (
            ("Header", "1 Introduction and Overview", "Some introductory text.", "1.1 Reference Documents", "More text."),
            ("Header", "Continuation.", "2 Description of New Features", "AGP discussion."),
            ("Header", "Last page."),
        ):
            page = document.new_page()
            for i, line in enumerate(entries):
                page.insert_text((40, 50 + i * 24), line)
        pdf = document.tobytes()
        document.close()
        return pdf

    def test_exact_reconstruction_and_same_page_sections(self):
        raw = self.fixture()
        verified = {
            1: ["1 Introduction and Overview", "1.1 Reference Documents"],
            2: ["2 Description of New Features"],
        }
        chunks, empty = extract_verified_section_chunks(raw, verified, max_chars=35)
        self.assertEqual(empty, [])
        self.assertTrue(all(len(c.content) <= 35 for c in chunks))
        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            for p in range(1, 4):
                original = doc[p - 1].get_text("text", sort=True)
                reconstructed = "".join(
                    c.content for c in chunks if c.page_start == p
                )
                self.assertEqual(reconstructed, original)
        self.assertTrue(any(
            c.heading == "1 Introduction and Overview / 1.1 Reference Documents"
            for c in chunks
        ))
        self.assertEqual(chunks[-1].heading, "2 Description of New Features")

    def test_unverified_or_ambiguous_anchor_fails(self):
        raw = self.fixture()
        with self.assertRaises(ValueError):
            extract_verified_section_chunks(raw, {1: ["9 Not in this document"]})
        with self.assertRaises(ValueError):
            extract_verified_section_chunks(raw, {9: ["9 Not in this document"]})

    def test_no_verified_headings_keeps_text(self):
        raw = self.fixture()
        chunks, _ = extract_verified_section_chunks(raw, {}, max_chars=120)
        self.assertTrue(all(c.heading is None for c in chunks))


if __name__ == "__main__":
    unittest.main()
