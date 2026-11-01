import unittest

import pymupdf

from llm_import.pdf_pages import extract_pdf_pages


class TestPDFPages(unittest.TestCase):

    def test_extract_pages(self):
        pdf = pymupdf.open()

        first = pdf.new_page()
        first.insert_text((72, 72), "RADEON 9200 SERIE")

        second = pdf.new_page()
        second.insert_text((72, 72), "Technische Eigenschaften")

        data = pdf.tobytes()
        pdf.close()

        pages = extract_pdf_pages(data)

        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["page"], 1)
        self.assertIn("RADEON 9200", pages[0]["text"])
        self.assertEqual(pages[1]["page"], 2)
        self.assertIn(
            "Technische Eigenschaften",
            pages[1]["text"],
        )

    def test_reject_invalid_pdf(self):
        with self.assertRaises(ValueError):
            extract_pdf_pages(b"not a PDF")


if __name__ == "__main__":
    unittest.main()