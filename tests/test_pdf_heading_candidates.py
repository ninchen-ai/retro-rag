"""Candidate detection tests, no database and no Nextcloud needed."""
import unittest

from scripts.pdf_heading_candidates import detect_heading_lines


class HeadingCandidateTests(unittest.TestCase):
    def test_real_agp_chapter_lines(self):
        sample = ("AGP3.0 Interface Specification\nRev. 1.0\n"
                  "3 AGP3.0 Physical Layer Specification\n"
                  "The AGP3.0 Physical Layer Specification defines ...")
        hits = detect_heading_lines(sample, 51)
        self.assertEqual([(h.pdf_page, h.level, h.heading) for h in hits],
                         [(51, 1, "3 AGP3.0 Physical Layer Specification")])

    def test_multi_part_agp_appendix_heading(self):
        sample = ("AGP3.0 Interface Specification\nRev. 1.0\n"
                  "5 Appendix B: Workstation Programming\nModel\n")
        hits = detect_heading_lines(sample, 113)
        self.assertEqual(hits[0].heading, "5 Appendix B: Workstation Programming")
        self.assertEqual(hits[0].confidence, "candidate")

    def test_table_of_contents_dotted_leaders_ignored(self):
        sample = ("Table of Contents\n"
                  "3 AGP3.0 Physical Layer Specification ........... 51\n")
        self.assertEqual(detect_heading_lines(sample, 5), [])

    def test_numbered_sentence_is_not_assumed_heading(self):
        sample = ("1. Read this information before installing.\n"
                  "Table 5: Signal List\n")
        self.assertEqual(detect_heading_lines(sample, 17), [])

    def test_subsection_candidate(self):
        sample = ("AGP3.0 Interface Specification\nRev. 1.0\n"
                  "1.2 Reference Documents\n"
                  "The following documents should be used ...")
        hits = detect_heading_lines(sample, 12)
        self.assertEqual(hits[0].level, 2)

    def test_invalid_page(self):
        with self.assertRaises(ValueError):
            detect_heading_lines("3 AGP3.0 Physical Layer Specification", 0)


if __name__ == "__main__":
    unittest.main()
