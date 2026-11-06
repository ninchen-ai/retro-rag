"""Regression tests for the document-independent PDF baseline adapter."""
import hashlib
import unittest

import pymupdf

from experiments.pdf_base_adapter import _source_bbox, build_base_structure
from experiments.validate_pdf_structure import validate


def sample_pdf():
    doc = pymupdf.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 100), "Heading Alpha", fontsize=14)
    p.insert_text((72, 130), "Heading Alpha", fontsize=14)
    doc.new_page(width=612, height=792)  # preserve blank page
    rotated = doc.new_page(width=612, height=792)
    rotated.insert_text((72, 100), "Third page", fontsize=12)
    rotated.set_rotation(90)
    raw = doc.tobytes()
    doc.close()
    return raw


class BaseAdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw = sample_pdf()
        self.uri = "nextcloud://nina/test.pdf"

    def test_schema_blank_pages_rotation_and_review(self):
        report = build_base_structure(self.raw, source_uri=self.uri, filename="test.pdf")
        self.assertEqual(validate(report), [])
        self.assertEqual(len(report["pages"]), 3)
        self.assertEqual(report["pages"][1]["text"], "")
        self.assertEqual(report["pages"][2]["rotation"], 90)
        self.assertEqual(
            (report["pages"][2]["width_pt"], report["pages"][2]["height_pt"]),
            (612.0, 792.0),
        )
        self.assertEqual(report["document"]["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(report["elements"], [])
        self.assertEqual(report["relationships"], [])
        self.assertEqual(report["quality"]["review_status"], "unreviewed")
        self.assertTrue(report["quality"]["text_integrity_checked"])

    def test_exact_page_text(self):
        report = build_base_structure(self.raw, source_uri=self.uri)
        with pymupdf.open(stream=self.raw, filetype="pdf") as doc:
            self.assertEqual(
                [page["text"] for page in report["pages"]],
                [page.get_text("text") for page in doc],
            )

    def test_same_text_different_locations_remain_distinct(self):
        report = build_base_structure(self.raw, source_uri=self.uri)
        hits = [s for s in report["source_spans"] if s["text"] == "Heading Alpha"]
        self.assertEqual(len(hits), 2)
        self.assertNotEqual(hits[0]["bbox_pt"], hits[1]["bbox_pt"])

    def test_optional_geometry_never_changes_text(self):
        a = build_base_structure(self.raw, source_uri=self.uri)
        b = build_base_structure(self.raw, source_uri=self.uri, include_spans=False)
        self.assertEqual([p["text"] for p in a["pages"]],
                         [p["text"] for p in b["pages"]])
        self.assertEqual(b["source_spans"], [])
        self.assertEqual(validate(b), [])

    def test_invalid_bounding_boxes_not_accepted(self):
        self.assertIsNone(_source_bbox((-10, 1, 20, 15), 612, 792))
        self.assertIsNone(_source_bbox((1, 1, 1, 15), 612, 792))

    def test_stable_document_id(self):
        a = build_base_structure(self.raw, source_uri=self.uri, include_spans=False)
        b = build_base_structure(self.raw, source_uri=self.uri, include_spans=False)
        self.assertEqual(a["document"]["document_id"], b["document"]["document_id"])


if __name__ == "__main__":
    unittest.main()
