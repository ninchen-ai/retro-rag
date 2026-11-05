"""Read-only diagnostics for ambiguous technical labels on a PDF page.

Prints fragment text, font/position information and independent PyMuPDF
search matches. Does not modify the source PDF or create section anchors.

  python -m experiments.diagnose_pdf_labels --page 43 \
      --label "Added Fan" --label "System Front"
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
from pathlib import Path

import pymupdf


def _rect(rect):
    return [round(float(value), 1) for value in rect]


def diagnose_labels(raw: bytes, page_num: int, labels: list[str]) -> dict:
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if not (1 <= page_num <= len(doc)):
            raise ValueError(f"Invalid PDF page: {page_num}")
        page = doc[page_num - 1]
        words = page.get_text("words")
        spans = [
            {
                "text": span.get("text", ""),
                "bbox": _rect(span["bbox"]),
                "font": span.get("font", ""),
            }
            for block in page.get_text("dict")["blocks"] if block.get("type", 0) == 0
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ]
        output = []
        for label in labels:
            terms = [x.casefold() for x in re.findall(r"[\w]+", label)]
            matches = [_rect(box) for box in page.search_for(label)]
            matched_words = [
                {
                    "text": w[4],
                    "bbox": _rect(w[:4]),
                    "block": w[5],
                    "line": w[6],
                    "word": w[7],
                }
                for w in words
                if any(term in w[4].casefold() for term in terms)
            ]
            matched_spans = [
                span for span in spans
                if any(term in span["text"].casefold() for term in terms)
            ]
            output.append({
                "label": label,
                "search_for_matches": matches,
                "matching_words": matched_words,
                "matching_spans": matched_spans,
            })
        return {
            "pdf_page": page_num,
            "approved": False,
            "labels": output,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=int, default=43)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--pdf", type=Path, help="Local PDF instead of read-only WebDAV")
    parser.add_argument("--pdf-path", default=(
        "Retro-Computing/Referenzwissen/Schnittstellen/AGP/agpdg11a.pdf"
    ))
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    args = parser.parse_args()
    if args.pdf is not None:
        raw = args.pdf.read_bytes()
    else:
        from scripts.import_pdf import get_webdav
        password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass(
            "Nextcloud-App-Passwort: "
        )
        raw, _, _ = get_webdav(
            args.nextcloud_url, args.nextcloud_user, password, args.pdf_path
        )
    print(json.dumps(
        diagnose_labels(raw, args.page, args.label),
        ensure_ascii=False, indent=2
    ))


if __name__ == "__main__":
    main()
