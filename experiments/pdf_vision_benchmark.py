"""Read-only PDF vision experiment using the local Ollama HTTP API.

Examples:
  python experiments/pdf_vision_benchmark.py --page 38
  python experiments/pdf_vision_benchmark.py --page 43 --runs 2

No indexing, DB writes, file modifications or automatic review approval.
CPU-only inference is explicitly requested via num_gpu=0.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pymupdf

# Allow direct execution: python experiments/pdf_vision_benchmark.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.import_pdf import get_webdav


DEFAULT_PDF = "Retro-Computing/Referenzwissen/Schnittstellen/AGP/agpdg11a.pdf"

PROMPT = """Analyze this PDF page visually. Your task is DOCUMENT LAYOUT CLASSIFICATION,
not OCR transcription. Distinguish genuine document/section headings from
labels within diagrams and images (for example 'FAN DIRECTION'), figure captions
and body text. Use only what you can see. Return ONLY JSON with this structure:
{
 "page_type": "technical_document_page",
 "elements": [
   {
     "text": "short exact visible label",
     "kind": "section_heading|figure_label|figure_caption|body_text|uncertain",
     "reason": "short visual explanation"
   }
 ],
 "uncertainties": ["short explanation if relevant"]
}
Include relevant visually prominent candidates; do not make up text.
Do not decide whether content is approved for import."""


DEFAULT_CANDIDATES = {
    38: (
        "Recommendations for Thermal Performance",
        "ADD-IN CARD",
        "FAN DIRECTION",
    ),
}


def targeted_prompt(candidates: tuple[str, ...]) -> str:
    """Ask only for visually grounded classification of supplied candidates.

    The target labels are deliberately not supplied; this is a blind check.
    """
    lines = json.dumps(list(candidates), ensure_ascii=False)
    return (
        "Inspect the page image and classify ONLY these exact text candidates: "
        + lines
        + "\nDistinguish section headings from labels INSIDE or NEXT TO technical "
          "drawings, and from figure captions. Bold or uppercase typography "
          "alone does NOT imply a section heading. Judge spatial context. "
          "If unclear, classify uncertain. Do not transcribe other page text. "
          "Return JSON ONLY with an 'elements' array. For EACH candidate "
          "return exactly one object with keys 'text', 'kind', 'reason'; "
          "'kind' must be one of section_heading, figure_label, figure_caption, "
          "body_text, uncertain. Keep each reason under 20 words. "
          "Do not make approval decisions."
    )


def functional_prompt(candidates: tuple[str, ...]) -> str:
    """Test B: functional layout rules, without leaking expected labels."""
    lines = json.dumps(list(candidates), ensure_ascii=False)
    return (
        "You are reviewing the DOCUMENT STRUCTURE of a technical hardware manual. "
        "Inspect the supplied page image and classify ONLY these text candidates: "
        + lines
        + "\nEvaluate what each text element DOES in the document, not how bold, "
          "large, or uppercase it looks. A section_heading introduces a prose "
          "section whose subsequent paragraphs belong to it. A figure_label "
          "names a component, direction, property, or region inside or next to "
          "a technical drawing; a figure_caption describes or numbers an illustration. "
          "Inspect spatial grouping with arrows, drawing borders, components, "
          "nearby captions, and whether explanatory prose or a drawing follows. "
          "Never treat capitalization or bold text alone as sufficient evidence. "
          "If spatial evidence is insufficient, use uncertain. "
          "For each candidate return exactly one JSON object with keys "
          "text, kind, reason. The kind must be one of section_heading, "
          "figure_label, figure_caption, body_text, uncertain. "
          "Give a brief evidence-based reason (max 20 words). "
          "Return ONLY a JSON object with an elements array; do not transcribe "
          "other text or approve any item."
    )


def describe_pdf_layout(raw: bytes, page_number: int,
                        candidates: tuple[str, ...]) -> dict:
    """Read-only layout metadata; no inferred or gold-standard labels.

    Exact PDF text positions and neighboring lines are offered as evidence.
    Candidate matches must be unique to avoid misleading layout hints.
    """
    from scripts.pdf_layout_headings import visual_lines

    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if not (1 <= page_number <= doc.page_count):
            raise ValueError("PDF page number out of range")
        page = doc[page_number - 1]
        lines = visual_lines(page)
        details = []
        for candidate in candidates:
            matches = page.search_for(candidate)
            if len(matches) != 1:
                details.append({
                    "text": candidate,
                    "status": "not_unique_or_missing",
                    "match_count": len(matches),
                })
                continue
            target = matches[0]
            nearby = sorted(
                (
                    line for line in lines
                    if line.y >= target.y1 - 50
                    and line.y <= target.y1 + 105
                    and candidate.casefold() not in line.text.casefold()
                ),
                key=lambda line: (abs(line.y - target.y1), line.y),
            )[:8]
            aligned = [
                line for line in lines
                if abs(line.y - target.y0) < 12
                and candidate.casefold() in line.text.casefold()
            ]
            info = aligned[0] if aligned else None
            details.append({
                "text": candidate,
                "status": "located",
                "bbox_points": [round(v, 1) for v in target],
                "font_size_pt": round(info.size, 1) if info else None,
                "bold": info.bold if info else None,
                "nearby_text_lines": [
                    {"text": line.text[:140], "y": round(line.y, 1)}
                    for line in nearby
                ],
            })
        return {
            "page_size_points": [
                round(page.rect.width, 1), round(page.rect.height, 1)
            ],
            "candidates": details,
        }


def render_page(raw: bytes, page_number: int, dpi: int) -> bytes:
    if page_number < 1:
        raise ValueError("PDF page must be at least 1")
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if page_number > doc.page_count:
            raise ValueError(f"PDF has {doc.page_count} pages; requested {page_number}")
        pix = doc[page_number - 1].get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png")


def render_focus_crop(
    raw: bytes, page_number: int, focus_text: str, dpi: int,
    before_pt: float = 75, after_pt: float = 230,
) -> tuple[bytes, tuple[float, float, float, float]]:
    """Render a PDF rectangle spanning the sought label and nearby diagram.

    Use the whole page width, with context above and below the label.
    The PDF is only read, never modified. Raises if the label is not located.
    """
    if page_number < 1:
        raise ValueError("PDF page must be at least 1")
    if dpi < 72:
        raise ValueError("crop DPI must be at least 72")
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if page_number > doc.page_count:
            raise ValueError("PDF page number out of range")
        page = doc[page_number - 1]
        matches = page.search_for(focus_text)
        if len(matches) != 1:
            raise ValueError(
                f"Expected one match for {focus_text!r} on page {page_number}, "
                f"found {len(matches)}; select a unique --focus label"
            )
        rect = matches[0]
        bound = page.rect
        clip = pymupdf.Rect(
            bound.x0, max(bound.y0, rect.y0 - before_pt),
            bound.x1, min(bound.y1, rect.y1 + after_pt)
        )
        if clip.is_empty:
            raise ValueError("Focus crop rectangle is empty")
        image = page.get_pixmap(dpi=dpi, clip=clip, alpha=False).tobytes("png")
        return image, (clip.x0, clip.y0, clip.x1, clip.y1)


def query_ollama(png: bytes, *, model: str, url: str, cpu_only: bool,
                 timeout: int, prompt: str = PROMPT, num_ctx: int = 4096,
                 num_predict: int | None = None, extra_images: tuple[bytes, ...] = ()) -> dict:
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": 0,
        "options": {
            "temperature": 0,
            "num_ctx": num_ctx,
            **({"num_predict": num_predict} if num_predict is not None else {}),
            **({"num_gpu": 0} if cpu_only else {}),
        },
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [base64.b64encode(img).decode("ascii")
                       for img in (png, *extra_images)],
        }],
    }
    request = Request(
        url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    message_obj = result.get("message") or {}
    message = message_obj.get("content") or ""
    thinking = message_obj.get("thinking") or ""
    try:
        parsed = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        parsed = {"unparsed_response": message}
    return {
        "response_diagnostics": {
            "message_fields": sorted(message_obj.keys()),
            "content_chars": len(message),
            "thinking_chars": len(thinking),
            "empty_content": not bool(message.strip()),
        },
        "response": parsed,
        "total_duration_seconds": result.get("total_duration", 0) / 1e9,
        "load_duration_seconds": result.get("load_duration", 0) / 1e9,
        "eval_count": result.get("eval_count"),
        "done_reason": result.get("done_reason"),
        "eval_duration_seconds": result.get("eval_duration", 0) / 1e9,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=int, default=38, help="1-based PDF page")
    parser.add_argument("--dpi", type=int, default=110)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--model", default="qwen2.5vl:3b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--nextcloud-url", default="http://127.0.0.1:8080")
    parser.add_argument("--nextcloud-user", default="nina")
    parser.add_argument("--pdf-path", default=DEFAULT_PDF)
    parser.add_argument("--allow-gpu", action="store_true",
                        help="Default is CPU-only via num_gpu=0")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--mode", choices=("full", "targeted"), default="full")
    parser.add_argument("--prompt-variant", choices=("baseline", "functional"),
                        default="baseline", help="Functional variant is for targeted mode")
    parser.add_argument("--candidate", action="append", default=None,
                        help="Candidate to classify; repeat as needed in targeted mode")
    parser.add_argument("--num-ctx", type=int, default=None)
    parser.add_argument("--layout-hints", action="store_true",
                        help="Append PyMuPDF coordinates, font, and nearby text as evidence")
    parser.add_argument("--focus-crop", action="store_true",
                        help="Attach magnified cropped image in addition to full page")
    parser.add_argument("--focus", default="FAN DIRECTION",
                        help="Unique PDF text to center the extra crop on")
    parser.add_argument("--crop-dpi", type=int, default=200)
    parser.add_argument("--num-predict", type=int, default=None)
    args = parser.parse_args()
    if not (72 <= args.dpi <= 200):
        parser.error("--dpi must be between 72 and 200")
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.layout_hints and args.mode != "targeted":
        parser.error("--layout-hints requires --mode targeted")
    if args.focus_crop and args.mode != "targeted":
        parser.error("--focus-crop requires --mode targeted")
    if args.focus_crop and not (72 <= args.crop_dpi <= 300):
        parser.error("--crop-dpi must be between 72 and 300")
    if args.num_ctx is not None and args.num_ctx < 1024:
        parser.error("--num-ctx must be at least 1024")
    if args.num_predict is not None and args.num_predict < 1:
        parser.error("--num-predict must be positive")
    if args.prompt_variant == "functional" and args.mode != "targeted":
        parser.error("--prompt-variant functional requires --mode targeted")
    if args.candidate and args.mode != "targeted":
        parser.error("--candidate requires --mode targeted")
    candidates = tuple(args.candidate or DEFAULT_CANDIDATES.get(args.page, ()))
    if args.mode == "targeted" and not candidates:
        parser.error("No candidates for this page; supply --candidate one or more times")
    if args.mode == "full":
        prompt = PROMPT
    elif args.prompt_variant == "functional":
        prompt = functional_prompt(candidates)
    else:
        prompt = targeted_prompt(candidates)
    context = args.num_ctx or (8192 if args.mode == "targeted" else 4096)
    predict = args.num_predict or (512 if args.mode == "targeted" else None)
    password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass(
        "Nextcloud-App-Passwort: "
    )
    raw, _, _ = get_webdav(args.nextcloud_url, args.nextcloud_user, password,
                           args.pdf_path)
    if args.layout_hints:
        layout = describe_pdf_layout(raw, args.page, candidates)
        prompt += ("\nHere is additional factual geometry and nearby text "
                   "extracted from the PDF. These are observations, NOT "
                   "classifications or approval decisions. Interpret them "
                   "against the image rather than treating proximity as proof "
                   "of a heading.\n" + json.dumps(layout, ensure_ascii=False))
        print("Layout-Hinweise:", json.dumps(layout, ensure_ascii=False, indent=2), flush=True)
    png = render_page(raw, args.page, args.dpi)
    extra_images: tuple[bytes, ...] = ()
    if args.focus_crop:
        crop, region = render_focus_crop(
            raw, args.page, args.focus, args.crop_dpi
        )
        extra_images = (crop,)
        prompt += ("\nThe FIRST image is the full page. The SECOND image is a "
                   "magnified crop around one candidate and adjacent content. "
                   "Use both images for spatial context; do not assume "
                   "the focused candidate is a figure label or a heading.")
        print(f"Crop: {args.focus!r}, PDF rectangle {region}, "
              f"{args.crop_dpi} DPI, {len(crop)} bytes", flush=True)
    print(f"PDF-Seite {args.page}, PNG {len(png)} Bytes, "
          f"Modell {args.model}, CPU-only: {not args.allow_gpu}, "
          f"Modus: {args.mode}, Prompt: {args.prompt_variant}, "
          f"Kontext: {context}, max. Ausgabe: {predict}", flush=True)
    for i in range(1, args.runs + 1):
        start = time.perf_counter()
        try:
            result = query_ollama(
                png, model=args.model, url=args.ollama_url,
                cpu_only=not args.allow_gpu, timeout=args.timeout,
                prompt=prompt, num_ctx=context, num_predict=predict,
                extra_images=extra_images
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            raise SystemExit(f"Ollama request failed: {exc}") from exc
        result["wall_seconds"] = round(time.perf_counter() - start, 2)
        result["run"] = i
        result["approved"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
