"""Tests for local, self-contained, read-only v0.2 HTML visual review."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from experiments.pdf_review_html_v02 import (
    make_html, page_review_data, png_dimensions,
)
from experiments.pdf_structure_v02_assemble import assemble
from experiments.pdf_review_decisions_v02 import apply
from test_pdf_structure_v02 import synthetic_reports

BASE = (Path(__file__).resolve().parents[1]
        / "experiments/fixtures/pdf_document_structure_v0.1_example.json")


def fixture():
    base = json.loads(BASE.read_text(encoding="utf-8"))
    return assemble(base, *synthetic_reports(base))


def dummy_png(width=612, height=792):
    # The preview tests inspect metadata and embedded assets, not PNG decode.
    return (b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", width, height)
            + bytes([8, 2, 0, 0, 0])
            + b"fake-rest")


class PdfReviewHtmlV02Tests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def test_png_dimensions(self):
        self.assertEqual(png_dimensions(dummy_png()), (612, 792))

    def test_bad_png_rejected(self):
        with self.assertRaisesRegex(ValueError, "PNG"):
            png_dimensions(b"not a png")

    def test_page_review_retains_two_original_matrices(self):
        result = page_review_data(
            self.data, page_number=1,
            image_name="page1.png", image_dimensions=(612, 792),
        )
        regions = [r for r in result["regions"] if "raw_cells" in r]
        self.assertEqual(len(regions), 2)
        self.assertIsNone(regions[0]["raw_cells"][0][1])
        self.assertEqual(regions[1]["raw_cells"][1][1], "g")
        self.assertEqual(len(result["logical_elements"]), 1)
        self.assertTrue(all(r["review"]["status"] == "proposed"
                            for r in result["regions"]))

    def test_works_without_mutating_v02(self):
        before = copy.deepcopy(self.data)
        markup = make_html(
            self.data, page_number=1, png_bytes=dummy_png(),
            image_name="page1.png"
        )
        self.assertEqual(self.data, before)
        self.assertIn("data:image/png;base64,", markup)
        self.assertIn("Verknüpfungen", markup)
        self.assertIn("Original-Zellmatrix", markup)
        self.assertNotIn("<script src=", markup)

    def test_wrong_png_filename_rejected(self):
        with self.assertRaisesRegex(ValueError, "filename"):
            make_html(self.data, page_number=1, png_bytes=dummy_png(),
                      image_name="other.png")

    def test_wrong_image_dimensions_rejected(self):
        with self.assertRaisesRegex(ValueError, "dimensions"):
            make_html(self.data, page_number=1,
                      png_bytes=dummy_png(1200, 1200),
                      image_name="page1.png")

    def test_unsupported_page_without_layout_rejected(self):
        with self.assertRaisesRegex(ValueError, "layout run"):
            page_review_data(self.data, page_number=2,
                             image_name="page2.png",
                             image_dimensions=(612, 792))

    def test_out_of_range_page_rejected(self):
        with self.assertRaisesRegex(ValueError, "page number"):
            page_review_data(self.data, page_number=99,
                             image_name="page1.png",
                             image_dimensions=(612, 792))

    def test_script_tag_in_pdf_text_not_executed(self):
        raw = "</script><img src=x onerror=alert(1)>"
        self.data["logical_elements"][0]["label"] = raw
        markup = make_html(
            self.data, page_number=1, png_bytes=dummy_png(),
            image_name="page1.png"
        )
        self.assertNotIn(raw, markup)
        self.assertIn("\\u003c/script\\u003e", markup)
        self.assertIn("connect-src 'none'", markup)

    def test_review_does_not_add_any_decisions(self):
        result = page_review_data(self.data, page_number=1,
                                  image_name="page1.png",
                                  image_dimensions=(612, 792))
        self.assertEqual(result["review_decisions"], [])
        self.assertEqual(self.data["review_decisions"], [])

    def test_ledger_effective_status_after_explicit_decision(self):
        before = copy.deepcopy(self.data)
        target = self.data["logical_elements"][0]["logical_id"]
        with tempfile.TemporaryDirectory() as tmp:
            decision = apply(
                self.data, Path(tmp) / "ledger",
                target_id=target, status="confirmed", reviewer="nina",
                reason="Originalseite geprüft",
            )
            markup = make_html(
                self.data, page_number=1, png_bytes=dummy_png(),
                image_name="page1.png", ledger_dir=Path(tmp) / "ledger",
            )
        self.assertIn(decision["decision_id"], markup)
        self.assertIn('"effective_reviews"', markup)
        self.assertIn('"status":"confirmed"', markup)
        self.assertEqual(self.data, before)
        self.assertEqual(self.data["logical_elements"][0]["review"]["status"],
                         "proposed")

    def test_without_ledger_never_implies_confirmation(self):
        markup = make_html(
            self.data, page_number=1, png_bytes=dummy_png(),
            image_name="page1.png",
        )
        self.assertIn('"effective_reviews":{}', markup)
        self.assertNotIn('"status":"confirmed"', markup)

    def test_corrupted_ledger_prevents_html_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger"
            decision = apply(
                self.data, ledger, target_id=self.data["logical_elements"][0]["logical_id"],
                status="confirmed", reviewer="nina", reason="checked",
            )
            (ledger / (decision["decision_id"] + ".json")).write_text(
                "invalid json", encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unparseable"):
                make_html(self.data, page_number=1, png_bytes=dummy_png(),
                          image_name="page1.png", ledger_dir=ledger)

    def test_ledger_only_displays_current_page_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger"
            target = self.data["logical_elements"][0]["logical_id"]
            other = self.data["physical_regions"][0]["region_id"]
            apply(self.data, ledger, target_id=target, status="confirmed",
                  reviewer="nina", reason="confirmed")
            # Deciding another on-page region is also reported.
            apply(self.data, ledger, target_id=other, status="rejected",
                  reviewer="nina", reason="wrong detection")
            markup = make_html(self.data, page_number=1, png_bytes=dummy_png(),
                               image_name="page1.png", ledger_dir=ledger)
            self.assertIn('"status":"confirmed"', markup)
            self.assertIn('"status":"rejected"', markup)

    def test_unrelated_document_page_data_not_leaked(self):
        result = page_review_data(self.data, page_number=1,
                                  image_name="page1.png",
                                  image_dimensions=(612, 792))
        self.assertNotIn("source_v01", result)
        self.assertNotIn("source_spans", result)
        self.assertNotIn("pages", result)


if __name__ == "__main__":
    unittest.main()
