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


def render_page(raw: bytes, page_number: int, dpi: int) -> bytes:
    if page_number < 1:
        raise ValueError("PDF page must be at least 1")
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if page_number > doc.page_count:
            raise ValueError(f"PDF has {doc.page_count} pages; requested {page_number}")
        pix = doc[page_number - 1].get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png")


def query_ollama(png: bytes, *, model: str, url: str, cpu_only: bool,
                 timeout: int, prompt: str = PROMPT, num_ctx: int = 4096, num_predict: int | None = None) -> dict:
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
            "images": [base64.b64encode(png).decode("ascii")],
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
    parser.add_argument("--candidate", action="append", default=None,
                        help="Candidate to classify; repeat as needed in targeted mode")
    parser.add_argument("--num-ctx", type=int, default=None)
    parser.add_argument("--num-predict", type=int, default=None)
    args = parser.parse_args()
    if not (72 <= args.dpi <= 200):
        parser.error("--dpi must be between 72 and 200")
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.num_ctx is not None and args.num_ctx < 1024:
        parser.error("--num-ctx must be at least 1024")
    if args.num_predict is not None and args.num_predict < 1:
        parser.error("--num-predict must be positive")
    if args.candidate and args.mode != "targeted":
        parser.error("--candidate requires --mode targeted")
    candidates = tuple(args.candidate or DEFAULT_CANDIDATES.get(args.page, ()))
    if args.mode == "targeted" and not candidates:
        parser.error("No candidates for this page; supply --candidate one or more times")
    prompt = targeted_prompt(candidates) if args.mode == "targeted" else PROMPT
    context = args.num_ctx or (8192 if args.mode == "targeted" else 4096)
    predict = args.num_predict or (512 if args.mode == "targeted" else None)
    password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass(
        "Nextcloud-App-Passwort: "
    )
    raw, _, _ = get_webdav(args.nextcloud_url, args.nextcloud_user, password,
                           args.pdf_path)
    png = render_page(raw, args.page, args.dpi)
    print(f"PDF-Seite {args.page}, PNG {len(png)} Bytes, "
          f"Modell {args.model}, CPU-only: {not args.allow_gpu}, "
          f"Modus: {args.mode}, Kontext: {context}, max. Ausgabe: {predict}", flush=True)
    for i in range(1, args.runs + 1):
        start = time.perf_counter()
        try:
            result = query_ollama(
                png, model=args.model, url=args.ollama_url,
                cpu_only=not args.allow_gpu, timeout=args.timeout,
                prompt=prompt, num_ctx=context, num_predict=predict
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            raise SystemExit(f"Ollama request failed: {exc}") from exc
        result["wall_seconds"] = round(time.perf_counter() - start, 2)
        result["run"] = i
        result["approved"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
