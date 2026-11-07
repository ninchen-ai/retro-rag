"""Read-only format adapters to the shared *proposed* import contract.

Neither adapter makes an indexing decision. Format-specific source validation
is delegated to existing project modules. Importers are never invoked.
"""
from __future__ import annotations

from experiments.import_contract_v01 import propose_contract
from experiments.pdf_structure_v02 import canonical_sha256


def from_pdf_audit_manifest(pdf_audit, *, source_uri, source_id, title):
    """Convert an already validated v0.2 audit into an unapproved proposal.

    Only original text chunks are carried as text units. Table composition is
    retained as structured metadata with review flags and provenance. Index
    remains blocked on ALL units, avoiding accidental duplicate table storage.
    """
    if pdf_audit.get("import_approved") is not False:
        raise ValueError("Expected blocked PDF audit manifest")
    if pdf_audit.get("db_writes") is not False:
        raise ValueError("Unexpected writable PDF audit")
    if pdf_audit.get("text_reconstruction_verified") is not True:
        raise ValueError("PDF text preservation not verified")
    if pdf_audit.get("index_disposition") != "blocked_review_and_dedup_required":
        raise ValueError("Unexpected PDF indexing disposition")
    units = []
    for entry in pdf_audit["entries"]:
        if entry["unit_type"] == "source_page_text":
            if entry["index_disposition"] not in (
                "not_approved", "blocked_possible_table_duplication"
            ):
                raise ValueError("Unexpected text index disposition")
            units.append({
                "unit_id": entry["chunk_id"],
                "unit_kind": "text",
                "content": entry["content"],
                "page_start": entry["page_number"],
                "page_end": entry["page_number"],
                "source_refs": [entry["chunk_id"]],
                "metadata": {
                    "source_profile": "source_v01.pages[].text",
                    "heading_path": entry["heading_path"],
                    "heading_id": entry["heading_id"],
                    "possible_table_overlap": (
                        entry["index_disposition"] ==
                        "blocked_possible_table_duplication"
                    ),
                },
            })
        elif entry["unit_type"] == "logical_table_preview":
            if entry["index_disposition"] != "blocked_possible_table_duplication":
                raise ValueError("Unexpected table index disposition")
            # Table serialization is not a verified replacement for source text.
            # Pure JSON representation retains row ordering; each cell's original
            # origin remains in source_rows metadata and original audit.
            import json
            rows = entry["rows_with_provenance"]
            content = json.dumps(
                [row["cells"] for row in rows], ensure_ascii=False,
                separators=(",", ":"),
            )
            units.append({
                "unit_id": entry["unit_id"],
                "unit_kind": "table",
                "content": content,
                "page_start": entry["page_number"],
                "page_end": entry["page_number"],
                "source_refs": list(entry["source_region_ids"]),
                "metadata": {
                    "source_profile": "pdf_table_composition_v0.1",
                    "logical_id": entry["logical_id"],
                    "composition_status": entry["composition_status"],
                    "composition_decision_id": entry["composition_decision_id"],
                    "logical_element_status": entry["logical_element_status"],
                    "source_region_statuses": entry["source_region_statuses"],
                    "rows_with_provenance": rows,
                    "related_review_states": entry["related_review_states"],
                    "possible_table_overlap": True,
                },
            })
        else:
            raise ValueError(f"Unsupported PDF audit unit: {entry['unit_type']}")
    return propose_contract({
        "source_system": "nextcloud",
        "source_id": str(source_id),
        "source_uri": source_uri,
        "source_sha256": pdf_audit["document_sha256"],
        "format": "pdf",
        "document_kind": "manual",
        "title": title,
    }, units)


def from_markdown_source(raw, *, source_uri, source_id):
    """Use the *existing* Markdown validator, no reimplementation of YAML.

    This is an import proposal only: existing operational Markdown import and
    vector indexer are not replaced or changed.
    """
    import hashlib
    from scripts.import_pg import parse_md
    meta, body, title = parse_md(raw)
    return propose_contract({
        "source_system": "nextcloud",
        "source_id": str(source_id),
        "source_uri": source_uri,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "format": "markdown",
        "document_kind": meta["type"],
        "title": title,
    }, [{
        "unit_id": str(meta["id"]) + "-body",
        "unit_kind": "text",
        "content": body,
        "page_start": None,
        "page_end": None,
        "source_refs": [str(meta["id"])],
        "metadata": {
            "source_profile": "markdown-yaml-frontmatter-v0.3",
            "frontmatter_sha256": canonical_sha256(meta),
        },
    }])
