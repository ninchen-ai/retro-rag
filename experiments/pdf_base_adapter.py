"""Read-only PDF -> common structure v0.1. No headings, chunks, DB or PDF writes."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import quote

import pymupdf

from experiments.validate_pdf_structure import validate


def _source_bbox(box, width, height):
    try:
        x0, y0, x1, y1 = map(float, box)
    except (TypeError, ValueError):
        return None
    if not all(map(math.isfinite, (x0, y0, x1, y1))):
        return None
    eps = 0.05
    if x0 < -eps or y0 < -eps or x1 > width + eps or y1 > height + eps:
        return None
    if x1 - x0 <= eps or y1 - y0 <= eps:
        return None
    return [max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1)]


def build_base_structure(raw_pdf: bytes, *, source_uri: str, filename=None,
                         include_spans=True):
    """Preserve exact PyMuPDF page text; auxiliary spans never replace source text.

    'text_integrity_checked' means extraction parity against the same PDF bytes,
    *not* completeness of visual/OCR or semantic information.
    """
    if not source_uri or not source_uri.strip():
        raise ValueError("source_uri required")
    if not isinstance(raw_pdf, bytes) or not raw_pdf.startswith(b"%PDF-"):
        raise ValueError("Expected raw PDF bytes")

    digest = hashlib.sha256(raw_pdf).hexdigest()
    document_id = "pdf-" + hashlib.sha256(source_uri.encode("utf-8")).hexdigest()[:24]
    pages, spans = [], []
    skipped_boxes = 0

    with pymupdf.open(stream=raw_pdf, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Encrypted PDF not supported")
        if doc.page_count == 0:
            raise ValueError("Empty PDF")
        for page_no, page in enumerate(doc, start=1):
            # Text coordinates are unrotated. page.rect swaps dimensions at 90/270.
            width, height = float(page.cropbox.width), float(page.cropbox.height)
            if width <= 0 or height <= 0:
                raise ValueError(f"Invalid dimensions on PDF page {page_no}")
            pages.append({
                "page_number": page_no, "width_pt": width, "height_pt": height,
                "rotation": int(page.rotation), "text": page.get_text("text"),
                "text_extraction": "pymupdf-text",
            })
            if include_spans:
                order = 0
                for bi, block in enumerate(page.get_text("dict").get("blocks", [])):
                    for li, line in enumerate(block.get("lines", [])):
                        for si, span in enumerate(line.get("spans", [])):
                            if not span.get("text"):
                                continue
                            bbox = _source_bbox(span.get("bbox"), width, height)
                            if bbox is None:
                                skipped_boxes += 1
                                continue
                            spans.append({
                                "span_id": f"p{page_no}-b{bi}-l{li}-s{si}",
                                "page_number": page_no, "text": span["text"],
                                "bbox_pt": bbox, "reading_order": order,
                                "source": "pymupdf",
                            })
                            order += 1

        # Separate second pass checks that JSON source text was not changed by
        # processing; this is not a proof of extraction completeness.
        for page_no, page in enumerate(doc, start=1):
            if pages[page_no - 1]["text"] != page.get_text("text"):
                raise ValueError(f"Text mismatch: page {page_no}")

    warnings = ["PyMuPDF extraction parity verified; visual/OCR completeness not proven."]
    if skipped_boxes:
        warnings.append(
            f"{skipped_boxes} spans had invalid/out-of-bounds boxes and were "
            "excluded from optional geometry; page text is unchanged."
        )
    if not include_spans:
        warnings.append("Optional span geometry disabled; page text unchanged.")

    return {
        "schema_version": "0.1",
        "document": {
            "document_id": document_id, "source_uri": source_uri, "sha256": digest,
            "page_count": len(pages), **({"filename": filename} if filename else {}),
        },
        "pages": pages, "source_spans": spans, "elements": [], "relationships": [],
        "quality": {
            "review_status": "unreviewed", "text_integrity_checked": True,
            "text_integrity_method": "verbatim PyMuPDF text second-pass comparison",
            "warnings": warnings,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path, help="Local PDF (read-only)")
    source.add_argument("--nextcloud-path", help="PDF relative to Nextcloud user")
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--out", required=True, type=Path, help="Local output JSON")
    parser.add_argument("--no-spans", action="store_true")
    args = parser.parse_args()
    if args.pdf:
        if args.pdf.resolve() == args.out.resolve():
            parser.error("Output may not overwrite source PDF")
        raw = args.pdf.read_bytes()
        source_uri, filename = args.pdf.resolve().as_uri(), args.pdf.name
    else:
        from scripts.import_pdf import get_webdav
        password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass(
            "Nextcloud-App-Passwort: "
        )
        raw, _, _ = get_webdav(args.nextcloud_url, args.nextcloud_user,
                              password, args.nextcloud_path)
        source_uri = "nextcloud://" + quote(args.nextcloud_user, safe="") + "/" + quote(args.nextcloud_path, safe="/")
        filename = args.nextcloud_path.rsplit("/", 1)[-1]

    result = build_base_structure(raw, source_uri=source_uri, filename=filename,
                                  include_spans=not args.no_spans)
    errors = validate(result)
    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors[:10]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Seiten: {len(result['pages'])} | Textspans: {len(result['source_spans'])}")
    print(f"SHA256: {result['document']['sha256']}")
    print(f"Schema validiert; Review offen. JSON: {args.out}")


if __name__ == "__main__":
    main()
