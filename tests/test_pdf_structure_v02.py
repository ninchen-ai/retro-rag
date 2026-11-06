"""v0.2 immutable-source, provenance, relationship and review regression tests."""
import copy
import json
from pathlib import Path
import unittest

from experiments.pdf_structure_v02 import (
    canonical_sha256, upgrade_v01, validate_v02,
)
from experiments.pdf_structure_v02_assemble import assemble

BASE = (Path(__file__).resolve().parents[1]
        / "experiments/fixtures/pdf_document_structure_v0.1_example.json")


def load_v01():
    return json.loads(BASE.read_text(encoding="utf-8"))


def synthetic_reports(base):
    h = base["document"]["sha256"]
    layout = {
        "source_image": "page1.png", "model": "test",
        "detections": [
            {"class_name": "table", "bbox_pixels": [100, 200, 450, 450],
             "confidence": .9},
            {"class_name": "table", "bbox_pixels": [100, 200, 270, 450],
             "confidence": .7},
            {"class_name": "table", "bbox_pixels": [280, 200, 450, 450],
             "confidence": .7},
        ],
    }
    quality = {
        "page_number": 1, "document_sha256": h,
        "source_image": "page1.png", "image_size_pixels": [612, 792],
        "pymupdf_tables": [
            {"index": 0, "bbox_pt": [100, 200, 270, 450],
             "rows": 2, "columns": 2, "cells": [["a", None], ["b", "c"]]},
            {"index": 1, "bbox_pt": [280, 200, 450, 450],
             "rows": 2, "columns": 2, "cells": [["d", "e"], ["f", "g"]]},
        ],
        "detector_to_pymupdf": [
            {"detector_region_index": 0, "matches": [], "status": "NO_CANDIDATE"},
            {"detector_region_index": 1, "matches": [
                {"pymupdf_table_index": 0, "iou": 1.0}],
                "status": "ONE_CANDIDATE"},
            {"detector_region_index": 2, "matches": [
                {"pymupdf_table_index": 1, "iou": 1.0}],
                "status": "ONE_CANDIDATE"},
        ],
    }
    captions = {
        "page_number": 1, "document_sha256": h,
        "source_image": "page1.png",
        "caption_candidates": [{
            "caption_id": "block-1-line-0", "kind": "table",
            "text": "Table 5. Configuration Address Decoding",
            "bbox_pt": [100, 170, 300, 190],
        }],
        "caption_matches": [{
            "caption_id": "block-1-line-0", "status": "MULTIPLE_CANDIDATES",
            "candidate_regions": [
                {"detector_region_index": 0},
                {"detector_region_index": 1},
            ],
        }],
    }
    conflicts = {
        "page_number": 1, "document_sha256": h,
        "source_image": "page1.png",
        "review_findings": [{
            "code": "POSSIBLE_MULTIPART_TABLE",
            "detector_region_indices": [1, 2],
        }],
    }
    return layout, quality, captions, conflicts


class V02StructureTests(unittest.TestCase):
    def test_upgrade_keeps_exact_v01_values(self):
        base = load_v01()
        original = copy.deepcopy(base)
        v02 = upgrade_v01(base)
        self.assertEqual(base, original)
        self.assertEqual(v02["source_v01"], base)
        self.assertEqual(v02["source_v01_sha256"], canonical_sha256(base))
        self.assertEqual(validate_v02(v02), [])

    def test_mutated_snapshot_is_rejected(self):
        v02 = upgrade_v01(load_v01())
        v02["source_v01"]["pages"][0]["text"] = "CHANGED"
        self.assertTrue(any("source_v01_sha256" in x
                            for x in validate_v02(v02)))

    def test_assembled_multipart_preserves_both_matrices(self):
        base = load_v01()
        reports = synthetic_reports(base)
        frozen = copy.deepcopy((base, reports))
        v02 = assemble(base, *reports)
        self.assertEqual((base, reports), frozen)
        self.assertEqual(validate_v02(v02), [])
        self.assertEqual(v02["source_v01"], base)
        extracted = [r for r in v02["physical_regions"]
                     if r["evidence"]["method"] == "pymupdf"]
        self.assertEqual(len(extracted), 2)
        self.assertIsNone(extracted[0]["raw_cells"][0][1])
        self.assertEqual(extracted[1]["raw_cells"][1][1], "g")
        self.assertEqual(len(v02["logical_elements"]), 1)
        self.assertTrue(all(
            r["review"]["status"] == "proposed"
            for r in v02["relationships_v02"]
        ))
        self.assertEqual(len(v02["review_decisions"]), 0)
        self.assertTrue(any(
            x["relation_type"] == "possible_same_table"
            for x in v02["relationships_v02"]
        ))

    def test_mismatching_document_hash_is_rejected(self):
        base = load_v01()
        reports = list(synthetic_reports(base))
        reports[2]["document_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            assemble(base, *reports)

    def test_unknown_source_run_is_rejected(self):
        v02 = assemble(load_v01(), *synthetic_reports(load_v01()))
        v02["physical_regions"][0]["evidence"]["run_id"] = "missing"
        self.assertTrue(any("missing processing run" in x
                            for x in validate_v02(v02)))

    def test_unknown_relation_is_rejected(self):
        base = load_v01()
        v02 = assemble(base, *synthetic_reports(base))
        v02["relationships_v02"][0]["to_id"] = "missing"
        self.assertTrue(any("unknown to_id" in x
                            for x in validate_v02(v02)))

    def test_out_of_bounds_geometry_is_rejected(self):
        base = load_v01()
        v02 = assemble(base, *synthetic_reports(base))
        v02["physical_regions"][0]["bbox_pt"][2] = 900
        self.assertTrue(any("bbox outside page" in x
                            for x in validate_v02(v02)))

    def test_no_silent_confirmation_on_import(self):
        base = load_v01()
        v02 = assemble(base, *synthetic_reports(base))
        v02["logical_elements"][0]["review"]["status"] = "confirmed"
        self.assertTrue(any("may only propose" in x
                            for x in validate_v02(v02)))

    def test_decision_requires_source_version(self):
        base = load_v01()
        v02 = assemble(base, *synthetic_reports(base))
        v02["review_decisions"].append({
            "decision_id": "decision-1",
            "target_id": v02["logical_elements"][0]["logical_id"],
            "status": "confirmed",
            "reviewer": "tester",
            "reason": "manually reviewed",
            "decided_at": "2026-11-06T10:00:00+01:00",
            "document_sha256": "b"*64,
        })
        self.assertTrue(any("source version mismatch" in x
                            for x in validate_v02(v02)))

    def test_decision_does_not_mutate_raw_proposal(self):
        base = load_v01()
        v02 = assemble(base, *synthetic_reports(base))
        target = v02["logical_elements"][0]["logical_id"]
        v02["review_decisions"].append({
            "decision_id": "decision-1",
            "target_id": target,
            "status": "confirmed",
            "reviewer": "tester",
            "reason": "checked against original PDF",
            "decided_at": "2026-11-06T10:00:00+01:00",
            "document_sha256": base["document"]["sha256"],
        })
        self.assertEqual(validate_v02(v02), [])
        self.assertEqual(v02["logical_elements"][0]["review"]["status"],
                         "proposed")

    def test_schema_version_required(self):
        v02 = upgrade_v01(load_v01())
        v02["schema_version"] = "0.1"
        self.assertTrue(validate_v02(v02))


if __name__ == "__main__":
    unittest.main()
