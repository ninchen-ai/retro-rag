"""Align visual chapter headings with unchanged PDF text."""
import unittest

import pymupdf

from scripts.pdf_heading_alignment import align_page_headings, align_document_headings
from scripts.pdf_heading_review import ReviewHeading


def candidate(heading, source="visual", page=1):
    return ReviewHeading(page, 2, heading, source, None, "REVIEW REQUIRED")


class HeadingAlignmentTests(unittest.TestCase):
    def test_same_line(self):
        text = "Running header\n3.2 Transfer Mode Operations\nMore text\n"
        result = align_page_headings(text, [candidate("3.2 Transfer Mode Operations")])[0]
        self.assertEqual((result.status, result.start_line, result.line_count), ("MATCHED", 1, 1))
        self.assertEqual(result.extracted_text, "3.2 Transfer Mode Operations\n")

    def test_split_number_and_title(self):
        text = "4.1.11 \nTime Keeping\nAn AGP3.0 device must...\n"
        result = align_page_headings(text, [candidate("4.1.11 Time Keeping")])[0]
        self.assertEqual((result.status, result.start_line, result.line_count), ("MATCHED", 0, 2))
        self.assertEqual(result.extracted_text, "4.1.11 \nTime Keeping\n")

    def test_separate_chapter_style(self):
        text = "Chapter 1\nAGP Electrical Design Considerations\nBody\n"
        result = align_page_headings(
            text,
            [candidate("Chapter 1: AGP Electrical Design Considerations", "separated chapter label and bold title")],
        )[0]
        self.assertEqual((result.status, result.start_line, result.line_count), ("MATCHED", 0, 2))

    def test_blank_neighbor_must_not_double_count(self):
        text = "Header\n3.2 Transfer Mode Operations\n\nMore text\n"
        matched = align_page_headings(
            text, [candidate("3.2 Transfer Mode Operations")]
        )[0]
        self.assertEqual(matched.status, "MATCHED")
        self.assertEqual(matched.line_count, 1)

    def test_blank_line_before_heading_must_not_double_count(self):
        text = "Header\n\n3.2 Transfer Mode Operations\nBody\n"
        matched = align_page_headings(
            text, [candidate("3.2 Transfer Mode Operations")]
        )[0]
        self.assertEqual(matched.status, "MATCHED")

    def test_subscript_spacing_artifact(self):
        result = align_page_headings(
            "3.6.6.2 Signal swing (VOH) Accuracy\\n",
            [candidate("3.6.6.2 Signal swing (V OH ) Accuracy")],
        )[0]
        self.assertEqual(result.status, "MATCHED_COMPACT")
        self.assertEqual(result.extracted_text, "3.6.6.2 Signal swing (VOH) Accuracy\\n")

    def test_collapsed_word_spacing(self):
        result = align_page_headings(
            "SimulationTechniques\\n",
            [candidate("Simulation Techniques")],
        )[0]
        self.assertEqual((result.status, result.line_count),
                         ("MATCHED_COMPACT", 1))

    def test_separated_chapter_collapsed_title(self):
        result = align_page_headings(
            "Chapter 1\\nAGPElectricalDesignConsiderations\\n",
            [candidate("Chapter 1: AGP Electrical Design Considerations",
                       "separated chapter label and bold title")],
        )[0]
        self.assertEqual((result.status, result.line_count),
                         ("MATCHED_COMPACT", 2))

    def test_compact_multiple_occurrences_remain_ambiguous(self):
        result = align_page_headings(
            "SimulationTechniques\\nSimulation Techniques\\n",
            [candidate("Simulation Techniques")],
        )[0]
        self.assertEqual(result.status, "AMBIGUOUS")

    def test_missing_and_duplicate_are_not_assumed(self):
        self.assertEqual(
            align_page_headings("Other contents\n", [candidate("1 Overview")])[0].status,
            "UNMATCHED",
        )
        self.assertEqual(
            align_page_headings("1 Overview\n1 Overview\n", [candidate("1 Overview")])[0].status,
            "AMBIGUOUS",
        )

    def test_document_alignment_does_not_change_pdf_text(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((54, 80), "1 Introduction and Overview")
        raw = doc.tobytes()
        doc.close()
        result = align_document_headings(raw, [candidate("1 Introduction and Overview")])
        self.assertEqual(result[0].status, "MATCHED")
        with pymupdf.open(stream=raw, filetype="pdf") as original:
            self.assertEqual(result[0].extracted_text, original[0].get_text("text", sort=True))


if __name__ == "__main__":
    unittest.main()
