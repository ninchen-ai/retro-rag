#!/usr/bin/env python3
"""Retro-RAG: LLM-Extraktion gegen Referenzdaten testen."""

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/llm-import/geforce-210-expected.yaml"
SOURCE = ROOT / "testdata/llm-import/geforce-210.txt"
IMPORTER = ROOT / "scripts/import_llm.py"


def main():
    expected = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))

    print("===== RETRO-RAG LLM-BENCHMARK =====", flush=True)
    print("Quelle:", SOURCE.name, flush=True)
    print("Importer:", IMPORTER.name, flush=True)
    print()

    result = subprocess.run(
        [sys.executable, str(IMPORTER), str(SOURCE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )

    output = result.stdout

    if result.returncode not in (0, 2):
        print("Importer fehlgeschlagen:")
        print(output)
        print(result.stderr)
        return 1

    start_marker = "===== MARKDOWN-ENTWURF (nicht gespeichert) ====="
    end_marker = "===== PRÜFBERICHT ====="

    if start_marker not in output or end_marker not in output:
        print("FEHLER: Markdown-Entwurf nicht gefunden")
        print(output)
        return 1

    markdown = output.split(start_marker, 1)[1].split(
        end_marker, 1
    )[0].strip()

    match = re.match(
        r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)",
        markdown,
        re.DOTALL,
    )

    if not match:
        print("FEHLER: YAML-Frontmatter nicht gefunden")
        return 1

    meta = yaml.safe_load(match.group(1))
    specs = meta.get("specs", {})

    passed = 0
    failed = 0

    print("===== IDENTIFIKATION =====")

    for field in ("category", "manufacturer", "model"):
        actual = meta.get(field)
        wanted = expected[field]
        ok = actual == wanted

        print(f"{'OK' if ok else 'FEHLER':7} {field}: {actual!r}")
        passed += int(ok)
        failed += int(not ok)

    print("\n===== TECHNISCHE EIGENSCHAFTEN =====")

    for field, wanted in expected["expected_specs"].items():
        actual = specs.get(field)
        ok = actual == wanted and type(actual) is type(wanted)

        print(f"{'OK' if ok else 'FEHLER':7} {field}")

        if not ok:
            print(f"          Erwartet: {wanted!r}")
            print(f"          Erhalten: {actual!r}")

        passed += int(ok)
        failed += int(not ok)

    print("\n===== UNBEKANNTE FELDER =====")

    for field in expected["expected_unknown"]:
        actual = specs.get(field)

        ok = (
            actual is None
            or actual == []
        )

        print(f"{'OK' if ok else 'FEHLER':7} {field}: {actual!r}")

        passed += int(ok)
        failed += int(not ok)

    status_match = re.search(
        r"STATUS:\s*(\w+)",
        output,
    )
    workflow_status = (
        status_match.group(1)
        if status_match
        else "UNBEKANNT"
    )

    print("\n===== ERGEBNIS =====")
    print(f"Prüfungen bestanden: {passed}")
    print(f"Prüfungen fehlgeschlagen: {failed}")
    print(f"Feldgenauigkeit: {passed / (passed + failed) * 100:.1f}%")
    print(f"Workflow-Status: {workflow_status}")

    if failed:
        print("\nBENCHMARK: NICHT BESTANDEN")
        return 1

    print("\nBENCHMARK: BESTANDEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
