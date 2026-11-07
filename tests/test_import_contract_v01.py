"""Proposed common import contract: never infers permission to index."""
import copy
import hashlib
import unittest

from experiments.import_contract_v01 import propose_contract, validate_contract
from experiments.import_contract_adapters_v01 import from_pdf_audit_manifest

DOC = {
    "source_system": "nextcloud",
    "source_id": "72",
    "source_uri": "nextcloud://nina/Manuals/a.pdf",
    "source_sha256": "a" * 64,
    "format": "pdf",
    "document_kind": "manual",
    "title": "A",
}


def unit(content="abc", uid="p1"):
    return {
        "unit_id": uid, "unit_kind": "text", "content": content,
        "page_start": 1, "page_end": 1, "source_refs": [uid],
        "metadata": {"source_profile": "source_v01.pages[].text"},
    }


class ImportContractTests(unittest.TestCase):
    def test_read_only_proposal_and_format_independent(self):
        original = copy.deepcopy(DOC)
        result = propose_contract(DOC, [unit()])
        self.assertEqual(validate_contract(result), [])
        self.assertFalse(result["indexing"]["allowed"])
        self.assertEqual(result["review"]["status"], "unreviewed")
        self.assertEqual(result["units"][0]["review_status"], "proposed")
        self.assertEqual(DOC, original)
        self.assertEqual(
            result["units"][0]["content_sha256"],
            hashlib.sha256(b"abc").hexdigest(),
        )

    def test_rejects_forged_index_permission(self):
        result = propose_contract(DOC, [unit()])
        result["indexing"]["allowed"] = True
        self.assertTrue(validate_contract(result))
        result["indexing"]["allowed"] = False
        result["units"][0]["index_disposition"] = "index_now"
        self.assertTrue(validate_contract(result))

    def test_rejects_duplicated_ids_and_changed_content(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            propose_contract(DOC, [unit(), unit()])
        result = propose_contract(DOC, [unit()])
        result["units"][0]["content"] = "tampered"
        self.assertIn(
            "units[0]: content SHA-256 mismatch",
            validate_contract(result),
        )

    def test_whitespace_only_source_preserved(self):
        result = propose_contract(DOC, [unit(" \n")])
        self.assertEqual(result["units"][0]["content"], " \n")
        self.assertEqual(validate_contract(result), [])

    def test_markdown_uses_same_contract(self):
        from experiments.import_contract_adapters_v01 import from_markdown_source
        raw = (b"---\ntype: hardware_model\nid: mb-test\n"
               b"model: CUBX\nmanufacturer: ASUS\ncategory: mainboard\n"
               b"specs: {}\n---\n# CUBX\nReference data.\n")
        result = from_markdown_source(
            raw, source_uri="nextcloud://nina/Hardware/cubx.md", source_id="42"
        )
        self.assertEqual(result["document"]["format"], "markdown")
        self.assertEqual(result["document"]["document_kind"], "hardware_model")
        self.assertEqual(validate_contract(result), [])
        self.assertFalse(result["indexing"]["allowed"])

    def test_pdf_adapter_retains_composition_provenance_and_block(self):
        audit = {
            "import_approved": False,
            "db_writes": False,
            "text_reconstruction_verified": True,
            "index_disposition": "blocked_review_and_dedup_required",
            "document_sha256": "b" * 64,
            "entries": [
                {
                    "unit_type": "source_page_text", "chunk_id": "p1-0",
                    "content": "hello\n", "page_number": 43,
                    "index_disposition": "blocked_possible_table_duplication",
                    "heading_path": [], "heading_id": None,
                },
                {
                    "unit_type": "logical_table_preview", "unit_id": "table-5",
                    "logical_id": "logical-5", "page_number": 43,
                    "index_disposition": "blocked_possible_table_duplication",
                    "composition_status": "confirmed",
                    "composition_decision_id": "valid-review-id",
                    "logical_element_status": "proposed",
                    "source_region_statuses": {"left": "confirmed", "right": "confirmed"},
                    "source_region_ids": ["left", "right"],
                    "rows_with_provenance": [
                        {"cells": ["Address", "IDSEL"], "region_id": "left", "row_index": 0},
                        {"cells": ["00000", "0001"], "region_id": "left", "row_index": 1},
                    ],
                    "related_review_states": [],
                },
            ],
        }
        result = from_pdf_audit_manifest(
            audit, source_uri="nextcloud://nina/manual.pdf",
            source_id="312", title="Manual",
        )
        self.assertEqual(validate_contract(result), [])
        self.assertEqual([u["unit_kind"] for u in result["units"]], ["text", "table"])
        self.assertEqual(
            result["units"][1]["metadata"]["rows_with_provenance"][1]["row_index"], 1
        )
        self.assertTrue(result["units"][0]["metadata"]["possible_table_overlap"])
        self.assertFalse(result["indexing"]["allowed"])


if __name__ == "__main__":
    unittest.main()
