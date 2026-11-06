"""Synthetic PDF regression tests for read-only outline proposals."""
import copy
import unittest

import pymupdf

from experiments.pdf_base_adapter import build_base_structure
from experiments.pdf_outline_adapter import (
    add_outline_proposals, classify_outline_title, _group_heading_rectangles, _variants,
)
from experiments.validate_pdf_structure import validate


def pdf_with_outline():
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((72, 110), "1. Introduction", fontsize=14)
    p1.insert_text((72, 150), "1.1 Architecture", fontsize=12)
    p1.insert_text((72, 200), "Figure 1-1. Block Diagram", fontsize=10)
    p1.insert_text((72, 250), "Table 1-1. Values", fontsize=10)
    p2 = doc.new_page()
    p2.insert_text((72, 110), "1.2 Usage", fontsize=12)
    p2.insert_text((72, 160), "Same", fontsize=12)
    p2.insert_text((72, 250), "Same", fontsize=12)
    doc.new_page()  # empty page and no forced text normalization
    doc.set_toc([
        [1, "1. Introduction", 1],
        [2, "1.1 Architecture", 1],
        [3, "Figure 1-1. Block Diagram", 1],
        [3, "Table 1-1. Values", 1],
        [2, "1.2 Usage", 2],
        [2, "Unknown bookmark", 3],
    ])
    result = doc.tobytes()
    doc.close()
    return result


class PdfOutlineAdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw = pdf_with_outline()
        self.base = build_base_structure(
            self.raw, source_uri="nextcloud://nina/testing.pdf",
        )

    def test_output_schema_unchanged_text_and_pending_review(self):
        before = copy.deepcopy(self.base)
        result = add_outline_proposals(self.raw, self.base)
        self.assertEqual(validate(result), [])
        self.assertEqual(self.base, before)
        self.assertEqual(result["pages"], before["pages"])
        self.assertEqual(result["source_spans"], before["source_spans"])
        self.assertEqual(result["document"], before["document"])
        self.assertEqual(len(result["elements"]), 6)
        self.assertTrue(all(x["review"]["status"] in ("proposed", "unclear")
                            for x in result["elements"]))
        self.assertEqual(result["quality"]["review_status"], "unreviewed")

    def test_figure_table_not_promoted_to_headings(self):
        result = add_outline_proposals(self.raw, self.base)
        self.assertEqual([e["element_type"] for e in result["elements"]],
                         ["heading", "heading", "figure", "table", "heading", "heading"])
        self.assertEqual(result["elements"][4]["parent_id"], "outline-00001")
        self.assertEqual(result["elements"][2]["parent_id"], "outline-00002")
        self.assertEqual(result["elements"][3]["parent_id"], "outline-00002")

    def test_missing_title_is_unclear_not_dropped(self):
        result = add_outline_proposals(self.raw, self.base)
        missing = result["elements"][-1]
        self.assertEqual(missing["title_or_text"], "Unknown bookmark")
        self.assertEqual(missing["review"]["status"], "unclear")
        self.assertIn("TEXT_NOT_LOCATED", missing["provenance"][0]["evidence"])
        self.assertEqual(missing["source_span_ids"], [])

    def test_source_hash_rejects_different_pdf(self):
        other = copy.deepcopy(self.base)
        other["document"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            add_outline_proposals(self.raw, other)

    def test_nonempty_base_not_silently_merged(self):
        used = add_outline_proposals(self.raw, self.base)
        with self.assertRaisesRegex(ValueError, "already contains elements"):
            add_outline_proposals(self.raw, used)

    def test_no_bookmarks_keeps_base_unchanged(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "No TOC", fontsize=14)
        raw = doc.tobytes()
        doc.close()
        base = build_base_structure(raw, source_uri="file:///tmp/no-toc.pdf")
        result = add_outline_proposals(raw, base)
        self.assertEqual(result["elements"], [])
        self.assertEqual(validate(result), [])
        self.assertEqual(result["pages"], base["pages"])

    def test_repeated_titles_keep_distinct_ids(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Same", fontsize=12)
        page.insert_text((72, 200), "Same", fontsize=12)
        doc.set_toc([[1, "Same", 1], [1, "Same", 1]])
        raw = doc.tobytes()
        doc.close()
        base = build_base_structure(raw, source_uri="file:///tmp/repeated.pdf")
        result = add_outline_proposals(raw, base)
        self.assertEqual(len(result["elements"]), 2)
        self.assertNotEqual(result["elements"][0]["element_id"],
                            result["elements"][1]["element_id"])
        self.assertEqual(result["pages"], base["pages"])

    def test_wrapped_heading_page46_is_one_occurrence(self):
        # Actual rects from Intel 875P PDF page 46.
        rects = [
            pymupdf.Rect(72.00, 94.16, 94.17, 111.97),
            pymupdf.Rect(137.01, 94.16, 473.78, 111.97),
            pymupdf.Rect(137.04, 111.20, 289.94, 129.01),
        ]
        groups = _group_heading_rectangles(rects)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 3)

    def test_wrapped_heading_page55_is_one_occurrence(self):
        # Actual rects from Intel 875P PDF page 55.
        rects = [
            pymupdf.Rect(80.04, 94.68, 118.94, 110.22),
            pymupdf.Rect(144.92, 94.68, 490.24, 110.22),
            pymupdf.Rect(144.96, 109.68, 211.04, 125.22),
        ]
        groups = _group_heading_rectangles(rects)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 3)

    def test_separate_repeated_titles_remain_two_occurrences(self):
        rects = [
            pymupdf.Rect(137, 94, 250, 112),
            pymupdf.Rect(137, 190, 250, 208),
        ]
        self.assertEqual(len(_group_heading_rectangles(rects)), 2)

    def test_nearby_but_misaligned_labels_remain_separate(self):
        rects = [
            pymupdf.Rect(100, 100, 250, 118),
            pymupdf.Rect(130, 117, 220, 135),
        ]
        self.assertEqual(len(_group_heading_rectangles(rects)), 2)

    def test_ehci_private_use_dash_search_variants(self):
        title = "2.1.1 PWRMGT \uf0be PCI Power Management Interface"
        options = _variants(title)
        self.assertEqual(options[0], title)
        self.assertIn(
            "2.1.1 PWRMGT \uf8e7 PCI Power Management Interface", options
        )
        self.assertNotEqual(options[0], options[1])
        self.assertEqual(title, "2.1.1 PWRMGT \uf0be PCI Power Management Interface")

    def test_en_dash_table_bookmark_is_table(self):
        self.assertEqual(
            classify_outline_title(
                "Table 2\u20133. USBLEGSUP \uf0be USB Legacy Support Extended Capability"
            ), "table"
        )

    def test_private_use_dash_does_not_modify_pdf_base_text(self):
        raw = self.raw
        base = build_base_structure(raw, source_uri="file:///tmp/ehci-sample.pdf")
        before = copy.deepcopy(base["pages"])
        result = add_outline_proposals(raw, base)
        self.assertEqual(result["pages"], before)
        self.assertEqual(result["source_spans"], base["source_spans"])

    def test_bullet_outline_is_list_not_section_parent(self):
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), "1. Topic", fontsize=13)
        page.insert_text((72, 150), "•", fontsize=12)
        page.insert_text((90, 150), "Interrupt Transfer Pre-condition Criteria", fontsize=12)
        page.insert_text((72, 200), "1.1 Following section", fontsize=12)
        doc.set_toc([
            [1, "1. Topic", 1],
            [2, "\uf0b7 Interrupt Transfer Pre-condition Criteria", 1],
            [2, "1.1 Following section", 1],
        ])
        raw = doc.tobytes()
        doc.close()
        base = build_base_structure(raw, source_uri="file:///tmp/list.pdf")
        result = add_outline_proposals(raw, base)
        self.assertEqual(validate(result), [])
        self.assertEqual([e["element_type"] for e in result["elements"]],
                         ["heading", "list", "heading"])
        self.assertEqual(result["elements"][1]["parent_id"], "outline-00001")
        self.assertEqual(result["elements"][2]["parent_id"], "outline-00001")
        self.assertIn("list_bullet=near_title",
                      result["elements"][1]["provenance"][0]["evidence"])
        self.assertEqual(result["pages"], base["pages"])

    def test_missing_visible_bullet_stays_unclear(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((90, 150), "Interrupt Transfer Pre-condition Criteria", fontsize=12)
        doc.set_toc([[1, "\uf0b7 Interrupt Transfer Pre-condition Criteria", 1]])
        raw = doc.tobytes()
        doc.close()
        base = build_base_structure(raw, source_uri="file:///tmp/no-bullet.pdf")
        result = add_outline_proposals(raw, base)
        self.assertEqual(result["elements"][0]["element_type"], "list")
        self.assertEqual(result["elements"][0]["review"]["status"], "unclear")
        self.assertIn("BULLET_NOT_LOCATED",
                      result["elements"][0]["provenance"][0]["evidence"])

    def test_ehci_bullet_is_list_candidate(self):
        self.assertEqual(
            classify_outline_title("\uf0b7 Transfer Type Independent Pre-operations"),
            "list"
        )

    def test_classifier(self):
        self.assertEqual(classify_outline_title("Figure 2-3. PCI Signals"), "figure")
        self.assertEqual(classify_outline_title("Table 2-4. Registers"), "table")
        self.assertEqual(classify_outline_title("Revision History"), "navigation")
        self.assertEqual(classify_outline_title("2.1 Host Interface"), "heading")


if __name__ == "__main__":
    unittest.main()
