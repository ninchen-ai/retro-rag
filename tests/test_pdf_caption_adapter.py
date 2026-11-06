"""Synthetic tests for caption discovery and unapproved layout relations."""
import copy
import unittest

import pymupdf

from experiments.pdf_caption_adapter import (
    extract_caption_candidates, match_captions,
)


def caption(text, kind="table", box=None, ident="c0"):
    return {
        "caption_id": ident,
        "text": text,
        "kind": kind,
        "bbox_pt": box or [90, 200, 460, 215],
    }


def region(kind, bbox, index, confidence=.8):
    return {
        "source_detection_index": index,
        "class_name": kind,
        "bbox_pdf_points": bbox,
        "confidence": confidence,
    }


class CaptionAdapterTests(unittest.TestCase):
    def test_figure_and_table_captions_from_pdf_visual_lines(self):
        doc = pymupdf.open()
        p = doc.new_page(width=612, height=792)
        p.insert_text((70, 100), "Figure 6. Configuration Address Mapping")
        p.insert_text((70, 400), "Table 5. Configuration Address Decoding")
        p.insert_text((70, 500), "As shown in Table 5, the mapping changes.")
        raw = doc.tobytes()
        doc.close()
        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            captions = extract_caption_candidates(pdf[0])
        self.assertEqual([c["kind"] for c in captions], ["figure", "table"])
        self.assertEqual([c["number"] for c in captions], ["6", "5"])
        self.assertTrue(all(c["approved"] is False for c in captions))
        self.assertTrue(all(len(c["bbox_pt"]) == 4 for c in captions))

    def test_ehci_en_dash_numbering(self):
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((72, 100), "Table 2-3. USBLEGSUP")
        with pymupdf.open(stream=doc.tobytes(), filetype="pdf") as pdf:
            captions = extract_caption_candidates(pdf[0])
        doc.close()
        self.assertEqual(len(captions), 1)
        self.assertEqual(captions[0]["kind"], "table")

    def test_single_table_region_is_a_proposal(self):
        c = caption("Table 2-3. USBLEGSUP")
        r = region("table", [100, 225, 450, 600], 7)
        original = copy.deepcopy((c, r))
        result = match_captions([c], [r])
        self.assertEqual((c, r), original)
        match = result["caption_matches"][0]
        self.assertEqual(match["status"], "ONE_CANDIDATE")
        self.assertEqual(match["candidate_regions"][0]["detector_region_index"], 7)
        self.assertFalse(result["approved"])

    def test_nearby_wrong_class_rejected(self):
        result = match_captions(
            [caption("Table 5. Decoding")],
            [region("figure", [100, 225, 450, 600], 0)],
        )
        self.assertEqual(result["caption_matches"][0]["status"], "NO_CANDIDATE")

    def test_distant_caption_does_not_match(self):
        result = match_captions(
            [caption("Table 5. Decoding")],
            [region("table", [100, 300, 450, 600], 0)],
        )
        self.assertEqual(result["caption_matches"][0]["status"], "NO_CANDIDATE")

    def test_side_by_side_parts_remain_ambiguous(self):
        result = match_captions(
            [caption("Table 5. Configuration Address Decoding")],
            [
                region("table", [100, 225, 270, 600], 11),
                region("table", [290, 225, 460, 600], 12),
            ],
        )
        match = result["caption_matches"][0]
        self.assertEqual(match["status"], "MULTIPLE_CANDIDATES")
        self.assertEqual(len(match["candidate_regions"]), 2)

    def test_parent_and_parts_remain_ambiguous(self):
        result = match_captions(
            [caption("Table 5. Configuration Address Decoding")],
            [
                region("table", [100, 225, 460, 600], 11),
                region("table", [100, 225, 270, 600], 12),
                region("table", [290, 225, 460, 600], 13),
            ],
        )
        self.assertEqual(result["caption_matches"][0]["status"],
                         "MULTIPLE_CANDIDATES")

    def test_same_region_claimed_twice_stays_conflict(self):
        a = caption("Table 5. A", ident="a")
        b = caption("Table 6. B", ident="b")
        result = match_captions(
            [a, b], [region("table", [100, 225, 450, 600], 1)]
        )
        self.assertEqual([m["status"] for m in result["caption_matches"]],
                         ["SHARED_REGION_CONFLICT", "SHARED_REGION_CONFLICT"])

    def test_caption_below_region_unresolved(self):
        result = match_captions(
            [caption("Figure 1. Test")],
            [region("figure", [100, 30, 450, 180], 0)],
        )
        self.assertEqual(result["caption_matches"][0]["status"], "NO_CANDIDATE")

    def test_empty_candidates_remain_empty(self):
        self.assertEqual(match_captions([], [])["caption_matches"], [])

    def test_invalid_gap_rejected(self):
        with self.assertRaises(ValueError):
            match_captions([], [], max_gap_pt=-1)


if __name__ == "__main__":
    unittest.main()
