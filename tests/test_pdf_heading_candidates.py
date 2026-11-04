"""Candidate detection tests, no database and no Nextcloud needed."""
import unittest

from scripts.pdf_heading_candidates import detect_heading_lines, filter_main_chapter_sequence, HeadingCandidate


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

    def test_table_columns_and_clock_label_ignored(self):
        sample = ("5 clocks              4 clocks              12 clocks\n"
                  "9 R-W-D'0       SBA_ENABLE       Description\n"
                  "66 MHz Clock\n")
        self.assertEqual(detect_heading_lines(sample, 26), [])

    def test_main_chapters_must_be_consecutive(self):
        def candidate(page, text):
            return HeadingCandidate(page, 1, text, "fixture", "candidate")
        samples = [
            candidate(11, "1 Introduction and Overview"),
            candidate(26, "5 clocks are required"),
            candidate(42, "1 All other codes Reserved"),
            candidate(16, "2 Description of New Features"),
            candidate(51, "3 AGP3.0 Physical Layer Specification"),
        ]
        samples.sort(key=lambda c: c.pdf_page)
        kept = filter_main_chapter_sequence(samples)
        self.assertEqual([x.pdf_page for x in kept], [11, 16, 51])

    def test_agp_false_chapter_six_register_row(self):
        line = ("6 MST: RZ-IW     htrans#         TARGET ONLY: When ‘0’, "
                "Core-logic can translate host processor")
        self.assertEqual(detect_heading_lines(line, 129), [])

    def test_real_chapter_six_kept(self):
        first = HeadingCandidate(113, 1, "5 Appendix B: Workstation Programming", "fixture", "candidate")
        chapter = detect_heading_lines(
            "AGP3.0 Interface Specification\nRev. 1.0\n"
            "6 Appendix C: Glossary of Terms\n", 143
        )
        self.assertEqual([c.heading for c in chapter], ["6 Appendix C: Glossary of Terms"])
        kept = filter_main_chapter_sequence([
            HeadingCandidate(n, 1, f"{i} Main Chapter Title", "fixture", "candidate")
            for i, n in enumerate((11, 16, 51, 96), start=1)
        ] + [first] + chapter)
        self.assertEqual(kept[-1].pdf_page, 143)

    def test_invalid_page(self):
        with self.assertRaises(ValueError):
            detect_heading_lines("3 AGP3.0 Physical Layer Specification", 0)


if __name__ == "__main__":
    unittest.main()
