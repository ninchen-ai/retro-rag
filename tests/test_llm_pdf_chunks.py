import unittest

from llm_import.pdf_chunks import chunk_pdf_pages


class TestPDFChunks(unittest.TestCase):

    def test_groups_pages(self):
        pages = [
            {"page": 1, "text": "A" * 100},
            {"page": 2, "text": "B" * 100},
            {"page": 3, "text": "C" * 100},
        ]

        chunks = chunk_pdf_pages(pages, max_chars=205)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["pages"], [1, 2])
        self.assertEqual(chunks[1]["pages"], [3])
        self.assertEqual(len(chunks[0]["text"]), 202)

    def test_skips_empty_pages(self):
        pages = [
            {"page": 1, "text": "Einführung"},
            {"page": 2, "text": "   "},
            {"page": 3, "text": "SMARTGART"},
        ]

        chunks = chunk_pdf_pages(pages, max_chars=100)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["pages"], [1, 3])

    def test_rejects_oversized_page(self):
        pages = [
            {"page": 1, "text": "A" * 101},
        ]

        with self.assertRaises(ValueError):
            chunk_pdf_pages(pages, max_chars=100)

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            chunk_pdf_pages([], max_chars=0)

    def test_empty_input(self):
        self.assertEqual(chunk_pdf_pages([]), [])

    def test_preserves_page_order(self):
        pages = [
            {"page": number, "text": "X" * 80}
            for number in range(1, 11)
        ]

        chunks = chunk_pdf_pages(pages, max_chars=170)

        actual = [
            page
            for chunk in chunks
            for page in chunk["pages"]
        ]

        self.assertEqual(actual, list(range(1, 11)))


if __name__ == "__main__":
    unittest.main()