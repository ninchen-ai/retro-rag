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

    def test_numbered_register_subsection_is_not_discarded(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 60), "5.8.4 AGPSTAT: AGP STATUS REGISTER", fontsize=14.2, fontname="hebo")
        page.insert_text((54, 90), "Register fields are described here.", fontsize=11, fontname="helv")
        raw = doc.tobytes()
        doc.close()
        found = scan_layout_document(raw)
        self.assertEqual(
            [item.heading for item in found],
            ["5.8.4 AGPSTAT: AGP STATUS REGISTER"],
        )

    def test_single_word_numbered_subsections(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "3 AGP3.0 Physical Layer Specification", fontsize=22, fontname="hebo")
        page.insert_text((54, 120), "3.1 Overview", fontsize=16, fontname="hebo")
        page.insert_text((54, 160), "3.1.1 Introduction", fontsize=14, fontname="hebo")
        page.insert_text((54, 195), "Normal technical explanation follows.", fontsize=11, fontname="helv")
        raw = doc.tobytes()
        doc.close()
        found = scan_layout_document(raw)
        self.assertEqual(
            [heading.heading for heading in found],
            [
                "3 AGP3.0 Physical Layer Specification",
                "3.1 Overview",
                "3.1.1 Introduction",
            ],
        )
        self.assertTrue(all(h.confidence == "candidate" for h in found))

    def test_short_unbolded_or_measurement_lines_not_promoted(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 70), "3.1 Overview", fontsize=11, fontname="helv")
        page.insert_text((54, 110), "4.1 Specifications", fontsize=16, fontname="hebo")
        page.insert_text((54, 145), "6.0 ns 5", fontsize=11, fontname="helv")
        raw = doc.tobytes()
        doc.close()
        self.assertEqual(
            [h.heading for h in scan_layout_document(raw)],
            ["4.1 Specifications"],
        )

    def test_transfer_rate_prefix_in_heading(self):
        doc = pymupdf.open()
        page = doc.new_page()
        examples = [
            "4.4 1x and 2x Transfer Mode Specifications",
            "4.4.4 1x and 2x Mode Motherboard Specifications",
            "4.4.5 1x and 2x Mode Add-in Card Specifications",
            "4.5 4x Transfer Mode Specifications",
            "4.5.4 4x Mode Motherboard Specification",
            "4.5.5 4x Mode Add-in Card Specifications",
        ]
        for i, title in enumerate(examples):
            page.insert_text((54, 60 + i * 55), title, fontsize=14, fontname="hebo")
        raw = doc.tobytes()
        doc.close()
        self.assertEqual([h.heading for h in scan_layout_document(raw)], examples)

    def test_plain_numeric_table_value_not_a_heading(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 70), "4.4 6.0 ns 5", fontsize=14, fontname="hebo")
        page.insert_text((54, 110), "4.5 4x Transfer Mode Specifications", fontsize=16, fontname="hebo")
        raw = doc.tobytes()
        doc.close()
        self.assertEqual(
            [h.heading for h in scan_layout_document(raw)],
            ["4.5 4x Transfer Mode Specifications"],
        )

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
