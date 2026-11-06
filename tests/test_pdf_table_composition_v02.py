"""Table continuation: both source matrices kept, duplicate header skipped only in preview."""
import copy
import json
from pathlib import Path
import unittest

from experiments.pdf_structure_v02_assemble import assemble
from experiments.pdf_table_composition_v02 import (
    propose_composition, validate_proposal,
)
from test_pdf_structure_v02 import synthetic_reports

BASE = Path(__file__).resolve().parents[1] / (
    "experiments/fixtures/pdf_document_structure_v0.1_example.json"
)


def fixture():
    v01 = json.loads(BASE.read_text(encoding="utf-8"))
    result = assemble(v01, *synthetic_reports(v01))
    tables = [r for r in result["physical_regions"] if "raw_cells" in r]
    assert len(tables) == 2
    tables[0]["bbox_pt"] = [100, 200, 200, 350]
    tables[1]["bbox_pt"] = [210, 200, 310, 350]
    tables[0]["raw_cells"] = [
        ["Address", "IDSEL"],
        ["00000", "0001"], ["00111", "1000"], ["", ""],
    ]
    tables[1]["raw_cells"] = [
        ["Address", "IDSEL"],
        ["01000", "00010000"], ["1xxxx", "00000000"],
    ]
    logical = result["logical_elements"][0]
    logical["element_kind"] = "table"
    caption = next(
        r for r in result["physical_regions"] if r["region_kind"] == "caption"
    )
    caption["page_number"] = tables[0]["page_number"]
    if not any(
        r["from_id"] == logical["logical_id"]
        and r["to_id"] == caption["region_id"]
        and r["relation_type"] == "has_caption"
        for r in result["relationships_v02"]
    ):
        result["relationships_v02"].append({
            "relation_id": "test-table-caption-link",
            "from_id": logical["logical_id"],
            "to_id": caption["region_id"],
            "relation_type": "has_caption",
            "review": {"status": "proposed"},
        })
    return result, logical["logical_id"], [t["region_id"] for t in tables]


class TableCompositionTests(unittest.TestCase):
    def setUp(self):
        self.data, self.logical, self.ids = fixture()
        self.before = copy.deepcopy(self.data)

    def propose(self, ids=None):
        return propose_composition(
            self.data, logical_id=self.logical,
            source_region_ids=self.ids if ids is None else ids,
        )

    def test_preview_is_two_column_continuation(self):
        p = self.propose()
        self.assertEqual(p["review"]["status"], "proposed")
        self.assertEqual(p["composition"], "horizontal_continuation")
        self.assertEqual(p["source_region_ids"], self.ids)
        self.assertEqual([r["cells"] for r in p["preview_rows"]], [
            ["Address", "IDSEL"], ["00000", "0001"], ["00111", "1000"],
            ["01000", "00010000"], ["1xxxx", "00000000"],
        ])
        self.assertEqual(
            [(r["row_index"], r["reason"]) for r in p["preview_excluded_rows"]],
            [(3, "empty_row"), (0, "repeated_header")],
        )
        self.assertEqual(self.data, self.before)

    def test_source_cells_and_provenance_preserved(self):
        p = self.propose()
        self.assertEqual(p["preview_rows"][-1]["region_id"], self.ids[1])
        self.assertEqual(p["preview_rows"][-1]["row_index"], 2)
        self.assertEqual(
            [r["raw_cells"] for r in self.data["physical_regions"]
             if r["region_id"] in self.ids],
            [r["raw_cells"] for r in self.before["physical_regions"]
             if r["region_id"] in self.ids],
        )

    def test_deterministic_identity(self):
        self.assertEqual(self.propose(), self.propose())
        self.assertEqual(validate_proposal(self.data, self.propose()),
                         self.propose())

    def test_reverse_order_rejected(self):
        with self.assertRaisesRegex(ValueError, "adjacent horizontal"):
            self.propose(list(reversed(self.ids)))

    def test_duplicate_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.propose([self.ids[0], self.ids[0]])

    def test_unknown_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.propose([self.ids[0], "does-not-exist"])

    def test_different_headers_rejected(self):
        changed = copy.deepcopy(self.data)
        for r in changed["physical_regions"]:
            if r["region_id"] == self.ids[1]:
                r["raw_cells"][0][0] = "Wrong"
        with self.assertRaisesRegex(ValueError, "Headers differ"):
            propose_composition(
                changed, logical_id=self.logical,
                source_region_ids=self.ids,
            )

    def test_tampered_preview_rejected(self):
        p = self.propose()
        p["preview_rows"][1]["cells"][0] = "forged"
        with self.assertRaisesRegex(ValueError, "altered"):
            validate_proposal(self.data, p)

    def test_figure_cannot_be_target(self):
        changed = copy.deepcopy(self.data)
        changed["logical_elements"][0]["element_kind"] = "figure"
        with self.assertRaisesRegex(ValueError, "logical table"):
            propose_composition(changed, logical_id=self.logical,
                                source_region_ids=self.ids)

    def test_bad_v02_rejected(self):
        changed = copy.deepcopy(self.data)
        changed["source_v01_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Invalid v0.2"):
            propose_composition(changed, logical_id=self.logical,
                                source_region_ids=self.ids)


if __name__ == "__main__":
    unittest.main()
