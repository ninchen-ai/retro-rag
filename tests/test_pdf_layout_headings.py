"""Synthetic layout cases of historic specification PDFs."""
import unittest
import pymupdf
from scripts.pdf_layout_headings import visual_lines, scan_layout_document


class LayoutHeadingTests(unittest.TestCase):
    def test_separate_number_and_title_same_visual_line(self):
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((54, 76), "4.1.11", fontsize=14.2, fontname="hebo")
        p.insert_text((126, 76), "Time Keeping", fontsize=14.2, fontname="hebo")
        p.insert_text((54, 115), "An AGP device tracks periods.", fontsize=11, fontname="helv")
        raw = doc.tobytes()
        doc.close()
        with pymupdf.open(stream=raw, filetype="pdf") as original:
            self.assertTrue(any(line.text == "4.1.11 Time Keeping" for line in visual_lines(original[0])))
        heads = scan_layout_document(raw)
        self.assertEqual([(h.pdf_page, h.heading) for h in heads], [(1, "4.1.11 Time Keeping")])

    def test_heading_beyond_first_fourteen_lines(self):
        doc = pymupdf.open()
        p = doc.new_page()
        for i in range(19):
            p.insert_text((54, 50+i*17), f"Ordinary technical text number {i}.", fontsize=11, fontname="helv")
        p.insert_text((54, 430), "3.2 Transfer Mode Operations", fontsize=18, fontname="hebo")
        raw=doc.tobytes();doc.close()
        self.assertEqual([h.heading for h in scan_layout_document(raw)], ["3.2 Transfer Mode Operations"])

    def test_register_and_contents_not_headings(self):
        doc=pymupdf.open()
        p=doc.new_page()
        p.insert_text((54,54), "Table of Contents", fontname="hebo",fontsize=20)
        p.insert_text((54,95), "3 AGP3.0 Physical Layer Specification ....... 51", fontsize=12, fontname="hebo")
        p=doc.new_page()
        p.insert_text((54,54), "6 MST: RZ-IW htrans TARGET ONLY", fontname="hebo",fontsize=12)
        p.insert_text((54,100), "6 Appendix C: Glossary of Terms", fontname="hebo",fontsize=14)
        raw=doc.tobytes();doc.close()
        self.assertEqual([h.heading for h in scan_layout_document(raw)], ["6 Appendix C: Glossary of Terms"])


if __name__ == "__main__":
    unittest.main()
