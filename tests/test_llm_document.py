import unittest
import pymupdf

from llm_import.document import extract_document_text


class TestDocumentExtraction(unittest.TestCase):

    def test_txt(self):
        text = extract_document_text(
            b"Graphics Processing Unit: NVIDIA GeForce 210",
            "geforce-210.txt",
        )
        self.assertIn("GeForce 210", text)

    def test_markdown_with_bom(self):
        data = b"\xef\xbb\xbf# NVIDIA GeForce 210"

        text = extract_document_text(data, "gpu.md")

        self.assertEqual(text, "# NVIDIA GeForce 210")

    def test_unsupported_file(self):
        with self.assertRaises(ValueError):
            extract_document_text(b"test", "gpu.exe")

    def test_empty_document(self):
        with self.assertRaises(ValueError):
            extract_document_text(b"   ", "empty.txt")

    def test_file_too_large(self):
        with self.assertRaises(ValueError):
            extract_document_text(
                b"x" * (50 * 1024 * 1024 + 1),
                "large.txt",
            )

    def test_pdf_text_extraction(self):
        """Text eines PDFs wird ohne Dateisystemzugriff extrahiert."""

        document = pymupdf.open()

        try:
            page = document.new_page()
            page.insert_text(
                (72, 72),
                "Graphics Processing Unit: NVIDIA GeForce 210",
            )

            pdf_bytes = document.tobytes()

        finally:
            document.close()

        text = extract_document_text(
            pdf_bytes,
            "geforce-210.pdf",
        )

        self.assertIn("NVIDIA GeForce 210", text)
        self.assertIn("[PDF-Seite 1]", text)

    def test_pdf_without_text(self):
        """Ein PDF ohne extrahierbaren Text darf nicht validiert werden."""

        document = pymupdf.open()

        try:
            document.new_page()
            pdf_bytes = document.tobytes()

        finally:
            document.close()

        with self.assertRaisesRegex(ValueError, "Kein Text"):
            extract_document_text(
                pdf_bytes,
                "empty.pdf",
            )

if __name__ == "__main__":
    unittest.main()