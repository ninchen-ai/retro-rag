#!/usr/bin/env python3
"""Lokaler Retro-RAG LLM-Importer v0.1 – nur Dry-Run."""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

import pymupdf
import yaml

from import_pg import parse_md, CATEGORIES

MODEL = "qwen3.5:4b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": sorted(CATEGORIES | {"unknown"})
        },
        "manufacturer": {"type": "string"},
        "model": {"type": "string"},
        "specs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"}
                },
                "required": ["field", "value", "evidence"],
                "additionalProperties": False
            }
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": [
        "category", "manufacturer", "model",
        "specs", "warnings"
    ],
    "additionalProperties": False
}


def read_document(path):
    if not path.is_file():
        raise ValueError("Datei nicht gefunden")

    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Datei größer als 50 MiB")

    if path.suffix.lower() in (".txt", ".md"):
        text = path.read_text(encoding="utf-8-sig")
    elif path.suffix.lower() == ".pdf":
        pages = []
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise ValueError("PDF ist passwortgeschützt")
            for index, page in enumerate(pdf):
                pages.append(
                    f"\n[PDF-Seite {index + 1}]\n"
                    + page.get_text("text", sort=True)
                )
        text = "\n".join(pages)
    else:
        raise ValueError("Nur PDF, TXT und MD unterstützt")

    if not text.strip():
        raise ValueError("Kein Text extrahiert – OCR erforderlich")

    if len(text) > 18000:
        raise ValueError(
            "Dokument zu lang für v0.1 – "
            "Abschnittsverarbeitung erforderlich"
        )

    return text


def extract_with_llm(text):
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Du extrahierst Retro-Computer-Hardwaredaten. "
                    "Verwende ausschließlich Informationen "
                    "aus dem gelieferten Dokument. "
                    "Erfinde keine Werte. "
                    "Die Kategorie muss einem erlaubten "
                    "Wert entsprechen. "
                    "Nutze unknown bei unklarer Zuordnung. "
                    "Gib für jede Spezifikation einen "
                    "wörtlichen Quellenbeleg in evidence an. "
                    "Bei Unsicherheit ergänze warnings. "
                    "Schreibe technische Feldnamen kurz, "
                    "eindeutig und in snake_case."
                )
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "format": SCHEMA,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "num_ctx": 4096
        }
    }

    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urlopen(request, timeout=300) as response:
        result = json.load(response)

    data = json.loads(result["message"]["content"])
    return data, result


def slug(value):
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return value.strip("-")


def validate_extraction(data, source):
    issues = []

    category = data.get("category")
    if category not in CATEGORIES:
        issues.append("Hardwarekategorie nicht erkannt")

    for field in ("manufacturer", "model"):
        value = data.get(field, "")
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{field} fehlt")
        elif value.casefold() not in source.casefold():
            issues.append(f"{field} nicht im Quelltext belegt")

    specs = {}
    for item in data.get("specs", []):
        field = item["field"]
        value = item["value"]
        evidence = item["evidence"]

        if not re.fullmatch(r"[a-z][a-z0-9_]*", field):
            issues.append(f"Ungültiger Feldname: {field}")
            continue

        if not value.strip() or not evidence.strip():
            issues.append(f"Unvollständige Angabe: {field}")
            continue

        # Überflüssige Anführungszeichen entfernen
        evidence = evidence.strip().strip('"\'').strip()

        # Whitespace vereinheitlichen
        normalized_source = " ".join(source.split()).casefold()
        normalized_evidence = " ".join(evidence.split()).casefold()

        if normalized_evidence not in normalized_source:
            issues.append(f"Quellenbeleg nicht gefunden: {field}")
            continue

        if field in specs:
            issues.append(f"Doppeltes Feld: {field}")
            continue

        specs[field] = value

    if not specs:
        issues.append("Keine belegten Spezifikationen")

    issues.extend(data.get("warnings", []))
    return specs, issues


def render_markdown(data, specs):
    identifier = slug(
        data["category"] + "-" +
        data["manufacturer"] + "-" +
        data["model"]
    )

    meta = {
        "type": "hardware_model",
        "id": identifier,
        "manufacturer": data["manufacturer"],
        "model": data["model"],
        "category": data["category"],
        "specs": specs
    }

    frontmatter = yaml.safe_dump(
        meta,
        allow_unicode=True,
        sort_keys=False
    )

    title = f'{data["manufacturer"]} {data["model"]}'
    lines = [
        "---",
        frontmatter.rstrip(),
        "---",
        "",
        f"# {title}",
        "",
        "## Technische Daten",
        ""
    ]

    for field, value in specs.items():
        lines.append(f"- {field}: {value}")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()

    print(f"Quelldatei: {args.file}")
    print(f"LLM: {MODEL}")
    print("Modus: DRY-RUN\n")

    source = read_document(args.file)
    data, result = extract_with_llm(source)
    specs, issues = validate_extraction(data, source)

    print("\n===== LLM-ROHDATEN =====")
    print(json.dumps(
        data,
        indent=2,
        ensure_ascii=False
    ))
    print("=======================\n")

    # Bei unklarer Klassifikation kein Markdown erzeugen.
    if data.get("category") not in CATEGORIES:
        print("REVIEW: unbekannte Hardwarekategorie")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 2

    markdown = render_markdown(data, specs)

    try:
        parse_md(markdown.encode("utf-8"))
    except Exception as exc:
        issues.append(f"Markdown-Validierung: {exc}")

    print("===== ERZEUGTES MARKDOWN =====")
    print(markdown)

    print("===== VALIDIERUNG =====")
    if issues:
        print("STATUS: REVIEW")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("STATUS: SCHEMA- UND BELEGPRÜFUNG OK")
        print("Noch keine Freigabe für automatischen Upload.")

    print("\n===== MODELLMETRIKEN =====")
    print("Prompt-Tokens:", result.get("prompt_eval_count"))
    print("Output-Tokens:", result.get("eval_count"))
    print(
        "Dauer:",
        round(result.get("total_duration", 0) / 1e9, 2),
        "Sekunden"
    )

    return 2 if issues else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
PY