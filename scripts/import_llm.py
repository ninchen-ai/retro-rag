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


def read_document(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Datei nicht gefunden: {path}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Datei über 50 MiB")
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        text = path.read_text(encoding="utf-8-sig")
    elif suffix == ".pdf":
        parts = []
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("Passwortgeschützte PDF: Review/OCR nötig")
            for page_number, page in enumerate(doc, 1):
                parts.append(f"[PDF-Seite {page_number}]\n{page.get_text('text', sort=True)}")
        text = "\n".join(parts)
    else:
        raise ValueError("Nur .pdf, .txt und .md unterstützt")
    if not text.strip():
        raise ValueError("Kein Text: Review/OCR erforderlich")
    if len(text) > MAX_CHARS:
        raise ValueError("Mehr als 18.000 Zeichen: abschnittsweise Verarbeitung erforderlich")
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

def main() -> int:
    p = argparse.ArgumentParser(description="Retro-RAG LLM Import v0.2 – nur Dry-Run")
    p.add_argument("file", type=Path)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--ollama-url", default=DEFAULT_URL)
    args = p.parse_args()
    print(f"Quelle: {args.file}\nModell: {args.model}\nModus: DRY-RUN")
    source = read_document(args.file)
    classification, cr = call_ollama(
    args.ollama_url, args.model,
    (
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
    ),
    source,
    CLASSIFY_SCHEMA,
)
    category = classification.get("category")
    manufacturer = classification.get("manufacturer", "")
    model = classification.get("model", "")
    print("\nKLASSIFIKATION:", json.dumps(classification, ensure_ascii=False))
    if category != "grafikkarte":
        print("STATUS: REVIEW – v0.2 unterstützt derzeit nur grafikkarte")
        return 2
    if not all(isinstance(s, str) and s.strip() for s in (manufacturer, model)):
        print("STATUS: REVIEW – Hersteller/Modell fehlt")
        return 2
    if manufacturer.casefold() not in source.casefold() or model.casefold() not in source.casefold():
        print("STATUS: REVIEW – Hersteller/Modell nicht wörtlich im Dokument")
        return 2
    schema = load_schema(category)
    extraction, er = call_ollama(
        args.ollama_url, args.model,
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
        model,
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
    md = render_markdown(category, manufacturer, model, specs)
    print("\n===== MARKDOWN-ENTWURF (nicht gespeichert) =====\n")
    print(md)
    print("===== PRÜFBERICHT =====")
    if issues:
        print("STATUS: REVIEW")
        for item in issues:
            print(" -", item)
    else:
        print("STATUS: STRUKTUR- UND BASISBELEGPRÜFUNG OK")
        print("Keine automatische Freigabe: Fachprüfung und Dublettenprüfung stehen aus.")
        # Noch offene Meldungen in den strukturierten Bericht übernehmen.
    add_legacy_issues(
        review,
        issues,
        source_findings,
    )

    review.print_report()

    final_review = evaluate_final_fields(specs, evidence)

    print("\n===== FINALE FELDKONSISTENZ =====")
    print(f"STATUS: {final_review.status}")

    central_review = evaluate_final_review(
        validation_issues=validation_issues,
        source_findings=source_findings,
        specs=specs,
        evidence=evidence,
        source=source,
    )
    legacy_technical, legacy_llm = separate_legacy_issues(issues)

    #print("\n===== STRUKTURIERTE VALIDIERUNGSFEHLER =====")

    #for issue in validation_issues:
    #    print(
    #        f"{issue.code} "
    #        f"({issue.field}): "
    #        f"resolved={issue.resolved}"
    #    )

    #print("\n===== LEGACY-ABGLEICH (DIAGNOSE) =====")
    #print(f"Technische Legacy-Meldungen: {len(legacy_technical)}")
    #print(f"LLM-Diagnosen: {len(legacy_llm)}")

    for message in legacy_technical:
        print(f"LEGACY_TECHNICAL: {message}")

    print(f"Zentraler Status: {central_review.status}")

    print("\n===== ZENTRALER REVIEW-BERICHT =====")
    print(f"STATUS: {central_review.status}")

    for finding in central_review.findings:
        print(
            f"[{finding.severity.upper()}] "
            f"{finding.code} ({finding.field}): "
            f"{finding.message}"
        )

    coverage = classify_gpu_field_coverage(specs)

    print("\n===== SEMANTISCHE PRÜFABDECKUNG =====")

    for field, status in sorted(coverage.items()):
        print(f"{field}: {status}")

    unverified_fields = [
        field
        for field, status in coverage.items()
        if status == "UNVERIFIED"
    ]

    print(
        f"Nicht abgedeckte, belegte Felder: "
        f"{len(unverified_fields)}"
    )

    print("Belege:")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print("Metriken:")
    for label, raw in (("Klassifikation", cr), ("Extraktion", er)):
        print(f" {label}: {raw.get('total_duration', 0)/1e9:.2f}s; "
              f"Prompt {raw.get('prompt_eval_count', '?')}; "
              f"Output {raw.get('eval_count', '?')}")
    # Technischer Status ausschließlich aus dem zentralen Review-Bericht.
    # Menschliche Freigabe und Dublettenprüfung bleiben erforderlich.
    return 2 if central_review.requires_review else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"FEHLER: {error}", file=sys.stderr)
        sys.exit(1)
