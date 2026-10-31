#!/usr/bin/env python3
"""Retro-RAG LLM Importer v0.2: schema-driven, offline dry-run only.

Reads a local TXT/MD/PDF; classifies, extracts GPU data with local Ollama,
validates evidence and types, and renders existing Jinja2 template.
Never writes to Nextcloud, PostgreSQL or local source files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen
from llm_import.review import (
    ReviewReport,
    add_legacy_issues,
    evaluate_final_fields,
    ValidationIssue,
    evaluate_final_fields,
    evaluate_final_review,
    separate_legacy_issues,
)

from llm_import.validation import (
    normalize_evidence,
    empty_value,
    value_is_valid,
    verify_value,
        classify_gpu_field_coverage,
)

from llm_import.result import build_import_result
from llm_import.document import extract_document_text
import pymupdf
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from llm_import.source_checks import check_source
from llm_import.normalizers import (
    extract_deterministic_gpu_fields,
    normalize_gpu_identity_and_apis,
    reconcile_deterministic_value,
)
from import_pg import CATEGORIES, parse_md
from llm_import.classification import validate_classification
from contextlib import redirect_stdout
from io import StringIO

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "qwen3.5:4b"
DEFAULT_URL = "http://127.0.0.1:11434/api/chat"
MAX_BYTES = 50 * 1024 * 1024
MAX_CHARS = 18_000
CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": sorted(CATEGORIES | {"unknown"})},
        "manufacturer": {"type": "string"},
        "model": {"type": "string"},
    },
    "required": ["category", "manufacturer", "model"],
    "additionalProperties": False,
}

def read_document_bytes(path: Path) -> tuple[bytes, str]:
    """Liest eine lokale Datei und extrahiert ihren Text."""

    if not path.is_file():
        raise ValueError(f"Datei nicht gefunden: {path}")

    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)

    text = extract_document_text(data, path.name)

    return data, text

def read_document(path: Path) -> str:
    """Kompatibilität mit bestehenden Aufrufern."""

    _, text = read_document_bytes(path)
    return text


def call_ollama(url: str, model: str, system: str, user: str, schema: dict):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    request = Request(url, data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=300) as response:
        result = json.load(response)
    return json.loads(result["message"]["content"]), result


def load_schema(category: str) -> dict:
    file = ROOT / "config" / "llm-schemas" / f"{category}.yaml"
    if not file.is_file():
        raise ValueError(f"Kein Schema für {category}: {file}")
    schema = yaml.safe_load(file.read_text(encoding="utf-8"))
    if schema.get("category") != category or schema.get("document_type") != "hardware_model":
        raise ValueError("Ungültige Schema-Metadaten")
    return schema


def typed_json_type(definition: dict) -> dict:
    typ = definition["type"]
    nullable = definition.get("nullable", False)
    if typ == "list":
        result = {"type": "array", "items": {"type": "string"}}
    elif typ in ("string", "integer", "boolean"):
        result = {"type": typ}
    else:
        raise ValueError(f"Unbekannter Feldtyp: {typ}")
    if nullable:
        result["type"] = [result["type"], "null"]
    return result


def build_extraction_schema(schema: dict) -> dict:
    # Field wrappers carry both value and a literal snippet from source.
    properties = {}
    for name, definition in schema["fields"].items():
        properties[name] = {
            "type": "object",
            "properties": {
                "value": typed_json_type(definition),
                "evidence": {"type": "string"},
            },
            "required": ["value", "evidence"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "specs": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["specs", "warnings"],
        "additionalProperties": False,
    }

def reject_field(specs, evidence_report, name, definition):
    """Verwirft einen LLM-Wert konsistent."""
    value = empty_value(definition)

    specs[name] = value
    evidence_report[name] = {
        "value": value,
        "evidence": "",
        "origin": "rejected",
    }

def validate_specs(data: dict, schema: dict, source: str):
    problems = []
    specs = {}
    evidence_report = {}
    raw_specs = data.get("specs")
    validation_issues = []
    if not isinstance(raw_specs, dict):
        raise ValueError("LLM lieferte specs nicht als Objekt")
    src = normalize_evidence(source)
    for name, definition in schema["fields"].items():
        candidate = raw_specs.get(name)
        if not isinstance(candidate, dict):
            problems.append(f"{name}: fehlt in LLM-Ausgabe")

            validation_issues.append(
                ValidationIssue(
                    code="FIELD_MISSING",
                    field=name,
                    message="Feld fehlt in der LLM-Ausgabe",
                )
            )

            reject_field(specs, evidence_report, name, definition)
            continue
        value = candidate.get("value")
        evidence = candidate.get("evidence", "")
        if not isinstance(evidence, str):
            evidence = ""
        evidence_report[name] = {"value": value, "evidence": evidence}
        if not value_is_valid(value, definition):
            problems.append(
                f"{name}: unzulässiger Datentyp/Wert: {value!r}"
            )

            validation_issues.append(
                ValidationIssue(
                    code="INVALID_VALUE",
                    field=name,
                    message=f"Unzulässiger Datentyp oder Wert: {value!r}",
                )
            )

            reject_field(
                specs,
                evidence_report,
                name,
                definition,
            )
            continue
        if value is None or value == []:
            specs[name] = value

            if evidence.strip():
                problems.append(
                    f"{name}: leerer Wert mit unnötigem Beleg"
                )

                validation_issues.append(
                    ValidationIssue(
                        code="UNEXPECTED_EVIDENCE",
                        field=name,
                        message="Leerer Wert mit unnötigem Quellenbeleg",
                    )
                )

                evidence_report[name] = {
                    "value": value,
                    "evidence": "",
                    "origin": "rejected",
                }

            continue
        # Quellenbelege normalisieren
        normalized = normalize_evidence(evidence)

        # Standardmäßig ist der Beleg ungültig
        evidence_valid = False

        # Mehrere getrennte Zitate bei Listen unterstützen
        quoted_parts = re.findall(
            r'"([^"]+)"',
            evidence
        )

        if definition["type"] == "list" and quoted_parts:
            evidence_valid = all(
                bool(normalize_evidence(part))
                and normalize_evidence(part) in src
                for part in quoted_parts
            )
        else:
            evidence_valid = bool(
                normalized and normalized in src
            )

        if not evidence_valid:
            problems.append(
                f"{name}: wörtlicher Quellenbeleg fehlt"
            )

            validation_issues.append(
                ValidationIssue(
                    code="EVIDENCE_NOT_FOUND",
                    field=name,
                    message="Wörtlicher Quellenbeleg fehlt",
                )
            )

            reject_field(specs, evidence_report, name, definition)
            continue
        check = verify_value(name, value, normalized)
        if check:
            problems.append(check)

            validation_issues.append(
                ValidationIssue(
                    code="VALUE_VERIFICATION_FAILED",
                    field=name,
                    message=check,
                )
            )

            reject_field(specs, evidence_report, name, definition)
            continue
        specs[name] = value
    warnings = data.get("warnings", [])
    if isinstance(warnings, list):
        problems.extend(f"LLM: {w}" for w in warnings if isinstance(w, str) and w.strip())
    else:
        problems.append("warnings ist keine Liste")

        validation_issues.append(
            ValidationIssue(
                code="INVALID_WARNINGS_FORMAT",
                field=None,
                message="LLM warnings muss eine Liste sein",
            )
        )

    # Mindestens eine belegte Spezifikation erforderlich
    if not any(v is not None and v != [] for v in specs.values()):
        problems.append("Keine belegten Spezifikationen")

        validation_issues.append(
            ValidationIssue(
                code="NO_VERIFIED_SPECS",
                field=None,
                message="Keine belegten Spezifikationen vorhanden",
            )
        )
    return specs, problems, evidence_report, validation_issues


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def render_markdown(category: str, manufacturer: str, model: str, specs: dict) -> str:
    meta = {
        "type": "hardware_model",
        "id": slug(f"{category}-{manufacturer}-{model}"),
        "manufacturer": manufacturer,
        "model": model,
        "category": category,
        "specs": specs,
    }
    template_root = ROOT / "templates" / "hardware"
    environment = Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined, autoescape=False,
        trim_blocks=True, lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = environment.get_template(f"{category}.md.j2")
    md = template.render(
        frontmatter=yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip(),
        manufacturer=manufacturer, model=model, specs=specs,
    )
    actual, _body, _title = parse_md(md.encode("utf-8"))
    if actual != meta:
        raise ValueError("Markdown-Frontmatter weicht vom validierten Objekt ab")
    return md

CLASSIFICATION_SYSTEM_PROMPT = (
    "Du klassifizierst technische Hardware-Datenblätter. "
    "Bestimme die Hardwarekategorie anhand der beschriebenen "
    "Funktion und der technischen Eigenschaften. "

    "Verwende exakt die Kategorien des JSON-Schemas. "

    "Beispiele zur Orientierung: "
    "GPU, Graphics Processing Unit, Video Card oder "
    "Graphics Card -> grafikkarte. "
    "Processor oder Central Processing Unit -> cpu. "
    "Motherboard oder Mainboard -> mainboard. "
    "Network Adapter oder Ethernet Card -> netzwerkkarte. "

    "Hersteller und Modell müssen im Dokument belegbar sein. "
    "Unterscheide den Hersteller einer Grafikkarte vom "
    "Hersteller des darauf verbauten Grafikchips. "

    "Nutze unknown nur, wenn sich die Hardwarekategorie "
    "aus dem Dokument nicht zuverlässig bestimmen lässt. "
    "Erfinde keine Modellnummern oder Hersteller. "
    "Antworte ausschließlich im vorgegebenen JSON-Schema."

    "Bei Memory Speed übernimm den angegebenen MHz-Wert "
    "ohne Interpretation als effektiven DDR-Takt. "
    "Grafikchip-Hersteller und Grafikchip-Bezeichnung "
    "sind getrennte Felder. "
    "Beispiel: NVIDIA GeForce 210 bedeutet "
    "gpu_manufacturer NVIDIA und gpu_chip GeForce 210. "
    "Bei api_support verwende Bezeichnungen wie "
    "DirectX 10.1 und OpenGL 3.1, sofern belegt. "
    "Übernimm dokumentierte Abmessungen einschließlich "
    "ihrer Einheit. "
)

def classify_document(
    source: str,
    model: str,
    ollama_url: str,
) -> tuple[dict, dict, list[dict]]:
    """Klassifiziert Hardware und prüft die Quellenidentität."""

    classification, metrics = call_ollama(
        ollama_url,
        model,
        CLASSIFICATION_SYSTEM_PROMPT,
        source,
        CLASSIFY_SCHEMA,
    )

    findings = validate_classification(
        classification,
        source,
    )

    return classification, metrics, findings

def extract_gpu_document(
    source: str,
    category: str,
    manufacturer: str,
    model_name: str,
    model: str,
    ollama_url: str,
):
    """GPU-Extraktion und Validierung (Übergangsfunktion)."""
    # Fachliche Verarbeitung aus dem bisherigen main().
    schema = load_schema(category)
    extraction, er = call_ollama(
        ollama_url, model,
        "Extrahiere die technischen Eigenschaften für eine Retro-Grafikkarte. "
        "Gib für jedes Feld ein Objekt mit value und evidence zurück. "
        "evidence MUSS ein unveränderter, wörtlicher Ausschnitt des Dokuments sein, "
        "ohne zusätzliche Anführungszeichen. "
        "Bei nicht belegbaren Angaben: null (Listen: []) und evidence als leerer String. "
        "Erfinde nichts und ergänze keine Produktvarianten. "
        "Zahlen als Zahlen, Boolesches als true/false, Listen als Listen. "
        "Werte, Einheiten und Namen nicht zu snake_case umschreiben. "
        "WICHTIG: MB ist nicht dasselbe wie MiB. vram_mib nur setzen, wenn MiB "
        "ausdrücklich belegt ist, sonst null mit Warnung. "
        "Nenne erkennbare Widersprüche in warnings.",
        source, build_extraction_schema(schema),
    )
    specs, issues, evidence, validation_issues = validate_specs(extraction, schema, source)
    review = ReviewReport()
    # Unabhängige Sicherheitsprüfung des Quelldokuments
    source_findings = check_source(
        source,
        manufacturer,
        model_name,
    )
    # Felder mit widersprüchlichen Quellenangaben sperren.
    conflicting_fields = {
        finding["field"]
        for finding in source_findings
        if finding["code"] == "CONFLICTING_VALUES"
    }

    if source_findings:
        print("\n===== QUELLEN-SICHERHEITSPRÜFUNG =====")

        for finding in source_findings:
            code = finding["code"]
            field = finding.get("field", "document")

            review.add(
                code=code,
                severity=(
                    "error"
                    if code == "CONFLICTING_VALUES"
                    else "warning"
                ),
                field_name=field,
                message=str(finding),
                details=finding,
            )

            issues.append(
                f"{code}: {field} – {finding}"
            )

            print(f"REVIEW: {code} ({field})")
    # Ab hier neu erzeugte Normalisierungsfehler getrennt erfassen.
    normalization_issue_start = len(issues)
    deterministic = extract_deterministic_gpu_fields(source)

    # Widersprüchliche Felder dürfen keinen Einzelwert behalten.
    for finding in source_findings:
        if finding["code"] != "CONFLICTING_VALUES":
            continue

        field = finding["field"]

        if field in specs:
            specs[field] = None
            evidence[field] = {
                "value": None,
                "evidence": "",
                "origin": "conflict",
                "candidates": finding["values"],
            }

    print("\n===== REGELBASIERTE GEGENPRÜFUNG =====")

    for field, result in deterministic.items():

        if field in conflicting_fields:
            print(
                f"{field}: REVIEW – widersprüchliche "
                "Quellenwerte, automatische Ergänzung gesperrt"
            )
            continue

        candidate = result["value"]
        current = specs.get(field)

        print(
            f"{field}: {candidate} "
            f"[Quelle: {result['evidence']}]"
        )

        if current is None:
            # Fehlende Werte aus eindeutigen Quellen ergänzen.
            specs[field] = candidate

            evidence[field] = {
                "value": candidate,
                "evidence": result["evidence"],
                "origin": "deterministic"
            }

            print("  -> Fehlender Wert ergänzt")

        elif current != candidate:
            # Gleiche Abmessungen mit/ohne Einheit akzeptieren.
            same_dimensions = (
                field == "dimensions_mm"
                and isinstance(current, str)
                and isinstance(candidate, str)
                and re.sub(
                    r"\s+", "",
                    current.casefold().removesuffix("mm")
                )
                == re.sub(
                    r"\s+", "",
                    candidate.casefold().removesuffix("mm")
                )
            )

            if same_dimensions:
                specs[field] = candidate

                evidence[field] = {
                    "value": candidate,
                    "evidence": result["evidence"],
                    "origin": "deterministic"
                }

                print("  -> Darstellung normalisiert")

            else:
                reconcile_deterministic_value(
                    field_name=field,
                    current=current,
                    candidate=candidate,
                    source_evidence=result["evidence"],
                    specs=specs,
                    evidence=evidence,
                    issues=issues,
                )

                print(
                    "  -> REVIEW: Widerspruch, "
                    "Feld gesperrt"
                )

        else:
            print("  -> Übereinstimmung")

    normalize_gpu_identity_and_apis(
        source, specs, evidence, issues
    )

    # Technische Normalisierungsfehler in die zentrale
    # Review-Entscheidung übernehmen.
    for message in issues[normalization_issue_start:]:
        validation_issues.append(
            ValidationIssue(
                code="NORMALIZATION_CONFLICT",
                field=None,
                message=message,
            )
        )

    # Letzte Sicherheitsprüfung nach allen Normalisierungen.
    # Konfliktfelder dürfen niemals mit einem Einzelwert erscheinen.
    for finding in source_findings:
        if finding["code"] != "CONFLICTING_VALUES":
            continue

        field = finding["field"]

        if field not in specs:
            continue

        specs[field] = None

        evidence[field] = {
            "value": None,
            "evidence": "",
            "origin": "conflict",
            "candidates": finding["values"],
        }

    # No need to fabricate claims from a weak model identity.
    md = render_markdown(category, manufacturer, model_name, specs)

    return (
        specs, issues, evidence, validation_issues,
        source_findings, review, md, er,
    )

def process_document(
    source_bytes: bytes,
    filename: str,
    model: str,
    ollama_url: str,
) -> dict:
    """Verarbeitet ein Dokument ohne automatische Speicherung."""

    source = extract_document_text(source_bytes, filename)

    classification, cr, classification_findings = classify_document(
        source=source,
        model=model,
        ollama_url=ollama_url,
    )

    if classification_findings:
        return {
            "schema_version": "1.0",
            "source": {
                "filename": filename,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            },
            "model": model,
            "classification": classification,
            "review": {
                "status": "REVIEW",
                "findings": classification_findings,
            },
            "evidence": {},
            "markdown": None,
            "coverage": {},
            "metrics": {
                "classification": {
                    "total_duration": cr.get("total_duration", 0),
                    "prompt_eval_count": cr.get("prompt_eval_count"),
                    "eval_count": cr.get("eval_count"),
                },
                "extraction": None,
            },
        }
    category = classification["category"]
    manufacturer = classification["manufacturer"]
    model_name = classification["model"]

    diagnostic_output = StringIO()

    with redirect_stdout(diagnostic_output):
        (
            specs,
            issues,
            evidence,
            validation_issues,
            source_findings,
            review,
            md,
            er,
        ) = extract_gpu_document(
            source=source,
            category=category,
            manufacturer=manufacturer,
            model_name=model_name,
            model=model,
            ollama_url=ollama_url,
        )

    central_review = evaluate_final_review(
        validation_issues=validation_issues,
        source_findings=source_findings,
        specs=specs,
        evidence=evidence,
        source=source,
    )

    coverage = classify_gpu_field_coverage(specs)

    metrics = {
        "classification": {
            "total_duration": cr.get("total_duration", 0),
            "prompt_eval_count": cr.get("prompt_eval_count"),
            "eval_count": cr.get("eval_count"),
        },
        "extraction": {
            "total_duration": er.get("total_duration", 0),
            "prompt_eval_count": er.get("prompt_eval_count"),
            "eval_count": er.get("eval_count"),
        },
    }

    return build_import_result(
        source_path=Path(filename),
        source_bytes=source_bytes,
        model=model,
        classification=classification,
        markdown=md,
        review=central_review,
        evidence=evidence,
    )

def print_import_report(result: dict) -> None:
    """Gibt ein strukturiertes Importergebnis auf der Konsole aus."""

    classification = result["classification"]
    review = result["review"]

    print(
        "\nKLASSIFIKATION:",
        json.dumps(classification, ensure_ascii=False),
    )

    if result["markdown"] is not None:
        print("\n===== MARKDOWN-ENTWURF (nicht gespeichert) =====\n")
        print(result["markdown"])
        print("===== PRÜFBERICHT =====")
        print("STATUS:", review["status"])

    print("\n===== ZENTRALER REVIEW-BERICHT =====")
    print("STATUS:", review["status"])

    for finding in review["findings"]:
        print(
            f"[{finding['severity'].upper()}] "
            f"{finding['code']} ({finding.get('field')}): "
            f"{finding['message']}"
        )

    if result.get("coverage"):
        print("\n===== SEMANTISCHE PRÜFABDECKUNG =====")

        for field, status in sorted(result["coverage"].items()):
            print(f"{field}: {status}")

    if result.get("evidence"):
        print("Belege:")
        print(
            json.dumps(
                result["evidence"],
                ensure_ascii=False,
                indent=2,
            )
        )

def main() -> int:
    """CLI-Einstiegspunkt für den lokalen LLM-Import (DRY-RUN)."""

    parser = argparse.ArgumentParser(
        description="Retro-RAG LLM Import – DRY-RUN"
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_URL)
    args = parser.parse_args()

    print(
        f"Quelle: {args.file}\n"
        f"Modell: {args.model}\n"
        "Modus: DRY-RUN"
    )

    if not args.file.is_file():
        raise ValueError(f"Datei nicht gefunden: {args.file}")

    with args.file.open("rb") as handle:
        source_bytes = handle.read(MAX_BYTES + 1)

    result = process_document(
        source_bytes=source_bytes,
        filename=args.file.name,
        model=args.model,
        ollama_url=args.ollama_url,
    )

    print_import_report(result)

    return 2 if result["review"]["status"] == "REVIEW" else 0



if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"FEHLER: {error}", file=sys.stderr)
        sys.exit(1)
