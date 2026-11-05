"""Audit PDF bookmarks against page text positions without creating chunk anchors.

This checks whether a bookmark destination is geometrically near the
corresponding heading. A search result may have several rectangles for one
heading, so the number of rectangles is not treated as the occurrence count.

This first experiment supports unrotated pages. For other page rotations the
coordinate convention must be checked rather than assuming an inversion.

Example:
  python -m experiments.pdf_bookmark_anchor_audit \
    --pdf-path Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf
"""
from __future__ import annotations

import argparse
from collections import Counter
import getpass
import json
import os
from pathlib import Path
import re
from statistics import median

import pymupdf


def title_variants(title: str) -> list[str]:
    """Also consider root headings stored as 'Introduction 1'."""
    variants = [title]
    match = re.fullmatch(r"(.+?)\s+([1-9]\d?)", title.strip())
    if match:
        variants.append(f"{match.group(2)} {match.group(1)}")
    return variants


def bookmark_target_y(page: pymupdf.Page, dest: dict) -> float | None:
    """Convert bottom-origin TOC coordinates observed in this specific PDF."""
    point = dest.get("to")
    if point is None or page.rotation != 0:
        return None
    return float(page.rect.height - point.y)


def audit_bookmarks(raw_pdf: bytes, *, tolerance_pt: float = 12.0) -> dict:
    if tolerance_pt <= 0:
        raise ValueError("tolerance_pt must be positive")
    entries = []
    with pymupdf.open(stream=raw_pdf, filetype="pdf") as doc:
        for level, title, page_number, dest in doc.get_toc(simple=False):
            entry = {
                "level": level, "title": title, "pdf_page": page_number,
                "status": None, "target_y_pt": None,
                "best_text_y_pt": None, "delta_y_pt": None,
                "search_rectangles": 0,
            }
            if not 1 <= page_number <= doc.page_count:
                entry["status"] = "INVALID_PAGE"
                entries.append(entry)
                continue
            page = doc[page_number - 1]
            target_y = bookmark_target_y(page, dest)
            if target_y is None:
                entry["status"] = "UNSUPPORTED_DESTINATION"
                entries.append(entry)
                continue
            entry["target_y_pt"] = round(target_y, 1)
            rects = []
            for variant in title_variants(title):
                rects = page.search_for(variant)
                if rects:
                    break
            entry["search_rectangles"] = len(rects)
            if not rects:
                entry["status"] = "TEXT_NOT_FOUND"
                entries.append(entry)
                continue
            # Use the nearest source-text rectangle, not a concatenated bbox.
            nearest = min(rects, key=lambda r: abs(float(r.y0) - target_y))
            delta = abs(float(nearest.y0) - target_y)
            entry["best_text_y_pt"] = round(float(nearest.y0), 1)
            entry["delta_y_pt"] = round(delta, 1)
            entry["status"] = "NEAR_TARGET" if delta <= tolerance_pt else "DISTANT_FROM_TARGET"
            entries.append(entry)

    statuses = Counter(e["status"] for e in entries)
    deltas = [e["delta_y_pt"] for e in entries if e["delta_y_pt"] is not None]
    return {
        "approved": False,
        "bookmark_count": len(entries),
        "tolerance_pt": tolerance_pt,
        "status_counts": dict(sorted(statuses.items())),
        "median_delta_y_pt": median(deltas) if deltas else None,
        "max_delta_y_pt": max(deltas) if deltas else None,
        "issues": [e for e in entries if e["status"] != "NEAR_TARGET"],
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="Use local PDF instead of Nextcloud")
    parser.add_argument("--pdf-path", default="Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf")
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--tolerance", type=float, default=12.0)
    parser.add_argument("--out", type=Path, default=Path("/tmp/retro-bookmark-audit.json"))
    args = parser.parse_args()
    if args.pdf:
        raw_pdf = args.pdf.read_bytes()
    else:
        from scripts.import_pdf import get_webdav
        password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass("Nextcloud-App-Passwort: ")
        raw_pdf, _, _ = get_webdav(
            args.nextcloud_url, args.nextcloud_user, password, args.pdf_path
        )
    report = audit_bookmarks(raw_pdf, tolerance_pt=args.tolerance)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in ("entries", "issues")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Abweichende Lesezeichen: {len(report['issues'])}")
    for entry in report["issues"][:25]:
        print(f"S. {entry['pdf_page']}: {entry['title']} | {entry['status']} | Δy={entry['delta_y_pt']}")
    print(f"Bericht: {args.out}")


if __name__ == "__main__":
    main()
