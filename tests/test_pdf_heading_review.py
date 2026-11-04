"""The common heading review chooses known structures, never approves them."""
import unittest
import pymupdf

from scripts.pdf_heading_review import build_heading_review


def pdf(pages):
    doc = pymupdf.open()
    for lines in pages:
        p = doc.new_page()
        for y, text, size in lines:
            p.insert_text((54, y), text, fontsize=size, fontname="hebo")
    raw = doc.tobytes()
    doc.close()
    return raw


class CombinedReviewTests(unittest.TestCase):
    def test_numbered_style(self):
        raw = pdf([
            [(70, "1 Introduction and Overview", 18)],
            [(70, "2 Description of New Features", 18)],
        ])
        report = build_heading_review(raw)
        self.assertEqual(report.style, "numbered")
        self.assertEqual(len(report.headings), 2)
        self.assertTrue(all(x.status == "REVIEW REQUIRED" for x in report.headings))

    def test_dotted_style(self):
        raw = pdf([
            [(70, "1. Introduction", 22)],
            [(70, "2. Architectural Context and Scope", 22)],
        ])
        report = build_heading_review(raw)
        self.assertEqual(report.style, "dotted")
        self.assertEqual([x.section_number for x in report.headings], ["1", "2"])

    def test_separate_chapter_style(self):
        raw = pdf([
            [(140, "Chapter 1", 16),
             (174, "AGP Electrical Design Considerations", 14),
             (210, "Signal Termination", 12)],
            [(140, "Chapter 2", 16),
             (174, "Board Design Guidelines", 14)],
        ])
        report = build_heading_review(raw)
        self.assertEqual(report.style, "separated")
        self.assertIn("Signal Termination", [x.heading for x in report.headings])
        self.assertTrue(all(x.status == "REVIEW REQUIRED" for x in report.headings))

    def test_empty_document_fallback(self):
        raw = pdf([[]])
        report = build_heading_review(raw)
        self.assertEqual(report.style, "unresolved")
        self.assertTrue(report.warnings)


if __name__ == "__main__":
    unittest.main()
