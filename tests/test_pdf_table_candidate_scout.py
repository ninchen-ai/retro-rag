"""Tests for document-independent candidate page selection."""
import copy
import unittest

from experiments.pdf_table_candidate_scout import shortlist


def anchor(page, kind="table", status="proposed"):
    return {
        "element_id": f"t{page}", "element_type": kind,
        "page_number": page, "title_or_text": f"Table on page {page}",
        "bbox_pt": [10, 10, 50, 25],
        "review": {"status": status},
    }


def table(rows=3, cols=2):
    return {
        "bbox_pt": [60, 80, 200, 250],
        "rows": rows, "columns": cols,
        "cells": [[f"r{r}c{c}" for c in range(cols)] for r in range(rows)],
    }


class CandidateScoutTests(unittest.TestCase):
    def test_selects_only_pages_with_both_evidence_types(self):
        data = {"elements": [anchor(2), anchor(3), anchor(4, "heading")]}
        page_tables = {2: [table()], 3: [], 4: [table()]}
        saved = copy.deepcopy((data, page_tables))
        report = shortlist(data, page_tables)
        self.assertEqual((data, page_tables), saved)
        self.assertEqual([p["page_number"] for p in report["selected_pages"]], [2])
        self.assertFalse(report["approved"])

    def test_rejected_or_unclear_outline_is_excluded(self):
        report = shortlist(
            {"elements": [anchor(2, status="unclear")]},
            {2: [table()]},
        )
        self.assertEqual(report["selected_pages"], [])

    def test_prefers_more_column_diversity(self):
        data = {"elements": [anchor(2), anchor(3)]}
        report = shortlist(data, {
            2: [table(rows=7, cols=2)],
            3: [table(rows=3, cols=2), table(rows=6, cols=4)],
        }, max_pages=1)
        self.assertEqual(report["selected_pages"][0]["page_number"], 3)
        self.assertEqual(report["total_candidate_pages"], 2)

    def test_short_table_excluded(self):
        report = shortlist(
            {"elements": [anchor(2)]},
            {2: [table(rows=1)]},
        )
        self.assertEqual(report["selected_pages"], [])

    def test_nonempty_cells_do_not_imply_approval(self):
        report = shortlist(
            {"elements": [anchor(2)]},
            {2: [table()]},
        )
        entry = report["selected_pages"][0]
        self.assertEqual(entry["table_summaries"][0]["cell_warnings"], [])
        self.assertFalse(entry["approved"])
        self.assertEqual(entry["status"], "CANDIDATE_ONLY_NOT_MATCHED")

    def test_empty_cell_kept_as_warning(self):
        broken = table()
        broken["cells"][1][0] = None
        report = shortlist({"elements": [anchor(2)]}, {2: [broken]})
        self.assertIn(
            "EMPTY_CELL_R2_C1",
            report["selected_pages"][0]["table_summaries"][0]["cell_warnings"]
        )

    def test_bad_limit_rejected(self):
        with self.assertRaises(ValueError):
            shortlist({"elements": []}, {}, max_pages=0)


if __name__ == "__main__":
    unittest.main()
