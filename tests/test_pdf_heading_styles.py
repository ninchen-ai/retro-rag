"""Non-numbered and dotted-numbering heading style examples."""
import unittest

import pymupdf

from scripts.pdf_heading_styles import scan_alternative_styles


class HeadingStyleTests(unittest.TestCase):
    def test_dotted_chapter(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 140), "1. Introduction", fontsize=22, fontname="hebo")
        page.insert_text((54, 175), "Some explanatory text.", fontsize=10)
        raw = doc.tobytes()
        doc.close()
        self.assertEqual([x.heading for x in scan_alternative_styles(raw)], ["1. Introduction"])

    def test_separated_chapter_and_unnumbered_section(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 150), "Chapter 1", fontsize=16, fontname="hebo")
        page.insert_text((54, 184), "AGP Electrical Design Considerations", fontsize=14, fontname="hebo")
        page.insert_text((54, 216), "AGP Electrical Requirements", fontsize=12, fontname="hebo")
        page.insert_text((54, 250), "Some normal running text.", fontsize=10)
        raw = doc.tobytes()
        doc.close()
        headings = [x.heading for x in scan_alternative_styles(raw)]
        self.assertIn("Chapter 1: AGP Electrical Design Considerations", headings)
        self.assertIn("AGP Electrical Requirements", headings)

    def test_preface_chapter_previews_not_subsections(self):
        doc = pymupdf.open()
        intro = doc.new_page()
        intro.insert_text((54, 100), "Chapter 1: AGP Electrical Design Considerations", fontsize=12, fontname="hebo")
        intro.insert_text((54, 128), "Document Structure and Outline", fontsize=12, fontname="hebo")
        chapter = doc.new_page()
        chapter.insert_text((54, 140), "Chapter 1", fontsize=16, fontname="hebo")
        chapter.insert_text((54, 174), "AGP Electrical Design Considerations", fontsize=14, fontname="hebo")
        chapter.insert_text((54, 205), "AGP Electrical Requirements", fontsize=12, fontname="hebo")
        raw = doc.tobytes()
        doc.close()
        hits = scan_alternative_styles(raw)
        self.assertTrue(all(h.pdf_page >= 2 for h in hits))
        self.assertIn("AGP Electrical Requirements", [h.heading for h in hits])

    def test_no_unnumbered_guess_without_separated_chapter(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "Signal Overshoots and Undershoots", fontsize=12, fontname="hebo")
        raw = doc.tobytes()
        doc.close()
        self.assertEqual(scan_alternative_styles(raw), [])


if __name__ == "__main__":
    unittest.main()
