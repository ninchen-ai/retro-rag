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
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pymupdf

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


def render_page(raw: bytes, page_number: int, dpi: int) -> bytes:
    if page_number < 1:
        raise ValueError("PDF page must be at least 1")
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if page_number > doc.page_count:
            raise ValueError(f"PDF has {doc.page_count} pages; requested {page_number}")
        pix = doc[page_number - 1].get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png")


def query_ollama(png: bytes, *, model: str, url: str, cpu_only: bool,
                 timeout: int) -> dict:
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": 0,
        "options": {
            "temperature": 0,
            "num_ctx": 4096,
            **({"num_gpu": 0} if cpu_only else {}),
        },
        "messages": [{
            "role": "user",
            "content": PROMPT,
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
    message = result.get("message", {}).get("content", "")
    try:
        parsed = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        parsed = {"unparsed_response": message}
    return {
        "response": parsed,
        "total_duration_seconds": result.get("total_duration", 0) / 1e9,
        "load_duration_seconds": result.get("load_duration", 0) / 1e9,
        "eval_count": result.get("eval_count"),
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
    args = parser.parse_args()
    if not (72 <= args.dpi <= 200):
        parser.error("--dpi must be between 72 and 200")
    if args.runs < 1:
        parser.error("--runs must be positive")
    password = os.getenv("NEXTCLOUD_APP_PASSWORD") or getpass.getpass(
        "Nextcloud-App-Passwort: "
    )
    raw, _, _ = get_webdav(args.nextcloud_url, args.nextcloud_user, password,
                           args.pdf_path)
    png = render_page(raw, args.page, args.dpi)
    print(f"PDF-Seite {args.page}, PNG {len(png)} Bytes, "
          f"Modell {args.model}, CPU-only: {not args.allow_gpu}", flush=True)
    for i in range(1, args.runs + 1):
        start = time.perf_counter()
        try:
            result = query_ollama(
                png, model=args.model, url=args.ollama_url,
                cpu_only=not args.allow_gpu, timeout=args.timeout
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            raise SystemExit(f"Ollama request failed: {exc}") from exc
        result["wall_seconds"] = round(time.perf_counter() - start, 2)
        result["run"] = i
        result["approved"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
