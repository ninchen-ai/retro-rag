"""Review-only bridge from PDF structure v0.2 to lossless text chunk previews.

Reuses the v0.1 outline hierarchy and existing split_preserving_text helper.
Only EXPLICITLY selected heading IDs may form section boundaries; the IDs
are NOT approvals. Never writes DB, embeddings, PDFs, v0.2, or review ledger.

Critically, source_v01.pages[].text (unsorted original extraction) is the
only text source. Existing scripts/pdf_section_chunking.py uses a different
sort=True extraction and must not be substituted for verbatim v0.1 text.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.pdf_structure_v02 import canonical_sha256, validate_v02
from scripts.pdf_chapter_chunking import split_preserving_text


def _split_lossless(text, max_chars):
    if not text:
        return []
    if not text.strip():
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
    parts = split_preserving_text(text, max_chars)
    if "".join(parts) != text:
        raise ValueError("Source extraction was altered by splitter")
    return parts


def _hierarchy(elements, item):
    ids = {e["element_id"]: e for e in elements}
    chain = []
    seen = set()
    current = item
    while current is not None:
        ident = current["element_id"]
        if ident in seen:
            raise ValueError("Cycle in outline heading hierarchy")
        seen.add(ident)
        if current["element_type"] != "heading":
            raise ValueError("Non-heading outline parent")
        chain.append(current)
        parent = current["parent_id"]
        current = ids.get(parent) if parent else None
        if parent and current is None:
            raise ValueError("Unknown parent outline heading")
    return list(reversed(chain))


def preview(v02, *, selected_heading_ids=(), max_chars=2500):
    """Return a proposed chunk manifest with exact page-text reconstruction."""
    errors = validate_v02(v02)
    if errors:
        raise ValueError("Invalid v0.2: " + "; ".join(errors[:5]))
    if not isinstance(max_chars, int) or max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if isinstance(selected_heading_ids, str):
        raise ValueError("Expected sequence of heading IDs")
    selected = list(selected_heading_ids)
    if len(set(selected)) != len(selected):
        raise ValueError("Duplicate heading selection")
    source = v02["source_v01"]
    elements = source["elements"]
    headings = {e["element_id"]: e for e in elements if e["element_type"] == "heading"}
    by_page = {}
    for hid in selected:
        element = headings.get(hid)
        if element is None:
            raise ValueError(f"Unknown/non-heading selection: {hid}")
        if element["review"]["status"] == "rejected":
            raise ValueError(f"Rejected heading may not be selected: {hid}")
        page_no = element["page_number"]
        text = source["pages"][page_no - 1]["text"]
        title = element["title_or_text"]
        # Exact full line matching; never invent a boundary from placeholder bbox.
        lines = text.splitlines(keepends=True)
        matches = [i for i, line in enumerate(lines) if line.strip() == title]
        if len(matches) != 1:
            raise ValueError(
                f"Heading {hid} must match exactly one complete page-text line; "
                f"matched {len(matches)}"
            )
        by_page.setdefault(page_no, []).append((matches[0], element))

    out = []
    active_heading = None
    skipped_blank_pages = []
    for page in source["pages"]:
        pno = page["page_number"]
        original = page["text"]
        lines = original.splitlines(keepends=True)
        starts = sorted(by_page.get(pno, []), key=lambda pair: pair[0])
        positions = [index for index, _ in starts]
        if len(set(positions)) != len(positions):
            raise ValueError(f"Conflicting heading line positions on page {pno}")
        chunks_for_page = []
        boundaries = [(0, None)] + starts
        boundaries = sorted(boundaries, key=lambda pair: pair[0])
        for i, (start, heading) in enumerate(boundaries):
            if heading is not None:
                active_heading = heading
            stop = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(lines)
            segment = "".join(lines[start:stop])
            hierarchy = (
                [e["title_or_text"] for e in _hierarchy(elements, active_heading)]
                if active_heading else []
            )
            for part in _split_lossless(segment, max_chars):
                chunks_for_page.append({
                    "page_number": pno,
                    "heading_id": active_heading["element_id"] if active_heading else None,
                    "heading_path": hierarchy,
                    "content": part,
                    "text_sha256": canonical_sha256(part),
                    "status": "proposed",
                })
        if "".join(chunk["content"] for chunk in chunks_for_page) != original:
            raise ValueError(f"Page {pno}: source text was not reconstructed exactly")
        if not original.strip():
            skipped_blank_pages.append(pno)
        out.extend(chunks_for_page)
    # Stable generated IDs only; source text is never mutated.
    for i, chunk in enumerate(out):
        chunk["chunk_id"] = f"pdf-chunk-proposal-{i:06d}"
    return {
        "preview_version": "0.1",
        "document_sha256": source["document"]["sha256"],
        "source_v01_sha256": v02["source_v01_sha256"],
        "selected_heading_ids": selected,
        "selected_headings_are_approved": False,
        "source_text_profile": "verbatim source_v01.pages[].text",
        "max_chars": max_chars,
        "empty_or_whitespace_pages": skipped_blank_pages,
        "chunks": out,
        "quality": {
            "status": "unreviewed",
            "lossless_page_text_reconstruction": True,
            "tables_integrated": False,
            "db_writes": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-json", type=Path, required=True)
    parser.add_argument("--heading-id", action="append", default=[],
                        help="Explicit preview-only heading anchor (repeatable)")
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() == args.v02_json.resolve():
        parser.error("Refusing to overwrite v0.2 input")
    data = json.loads(args.v02_json.read_text(encoding="utf-8"))
    report = preview(
        data, selected_heading_ids=args.heading_id, max_chars=args.max_chars
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"Dry-run: {len(report['chunks'])} text chunks; exact source text retained.")
    print("No heading approved; no table merge/DB writes:", args.out)


if __name__ == "__main__":
    main()
