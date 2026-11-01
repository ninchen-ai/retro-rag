"""Menschenlesbare Review-Berichte für LLM-Importentwürfe."""


def _display(value) -> str:
    """Bereitet einen Wert für die Markdown-Ausgabe auf."""
    if value is None or value == "":
        return "Nicht angegeben"

    if isinstance(value, list):
        return ", ".join(str(item) for item in value)

    return str(value)


def render_review_report(result: dict) -> str:
    """Erzeugt einen Markdown-Prüfbericht ohne Schreibzugriff."""

    classification = result.get("classification") or {}
    source = result.get("source") or {}
    review = result.get("review") or {}
    evidence = result.get("evidence") or {}
    evidence_suggestions = result.get("evidence_suggestions") or {}

    manufacturer = classification.get("manufacturer") or "Unbekannt"
    model = classification.get("model") or "Unbekannt"
    status = review.get("status") or "REVIEW"

    lines = [
        f"# Review-Bericht: {manufacturer} {model}",
        "",
        f"**Status:** {status}",
        f"**Quelldatei:** {_display(source.get('filename'))}",
        f"**SHA-256:** {_display(source.get('sha256'))}",
        "",
        "## Extrahierte Eigenschaften",
        "",
    ]

    if not evidence:
        lines.append("Keine extrahierten Quellenbelege vorhanden.")
        lines.append("")

    for field_name, item in evidence.items():
        lines.append(f"### {field_name}")
        lines.append("")

        if isinstance(item, dict):
            lines.append(
                f"**Wert:** {_display(item.get('value'))}"
            )
            lines.append(
                f"**Originalbeleg:** {_display(item.get('evidence'))}"
            )
        else:
            lines.append(f"**Beleg:** {_display(item)}")

        lines.append("")

    lines.extend([
        "## Alternative Quellenbelege",
        "",
    ])

    if not evidence_suggestions:
        lines.append("Keine alternativen Belegvorschläge vorhanden.")
        lines.append("")

    for field_name, item in evidence_suggestions.items():
        lines.append(f"### {field_name}")
        lines.append("")

        if not isinstance(item, dict):
            lines.append("Ungültige Vorschlagsstruktur.")
            lines.append("")
            continue

        lines.append(
            f"**Vorschlagsstatus:** {_display(item.get('status'))}"
        )
        lines.append(
            f"**Modellkontext:** {_display(item.get('model_context'))}"
        )
        lines.append(
            f"**Modellbeleg:** {_display(item.get('model_evidence'))}"
        )
        lines.append(
            f"**Alternative Quellenprüfung:** "
            f"{'Bestanden' if item.get('validation_passed') is True else 'Nicht bestätigt'}"
        )
        lines.append("")

        suggestions = item.get("suggestions") or {}

        for value, suggestion in suggestions.items():
            lines.append(
                f"- **{value}:** {_display(suggestion)}"
            )

        if not suggestions:
            lines.append("Keine geeigneten Alternativen gefunden.")

        lines.append("")

    lines.extend([
        "## Offene Prüfbefunde",
        "",
    ])

    findings = review.get("findings") or []

    if not findings:
        lines.append("Keine Prüfbefunde vorhanden.")
        lines.append("")

    for finding in findings:
        lines.append(
            f"- **{finding.get('severity', 'warning').upper()}** "
            f"`{finding.get('code', 'UNKNOWN')}` "
            f"({finding.get('field') or 'document'}): "
            f"{finding.get('message') or 'Keine Beschreibung'}"
        )

    lines.extend([
        "",
        "## Freigabe",
        "",
        "**Entscheidung:** Ausstehend",
        "",
        "Dieser Bericht enthält automatisch ermittelte Angaben "
        "und Belegvorschläge. Eine fachliche Prüfung und explizite "
        "Bestätigung sind vor der Übernahme erforderlich.",
        "",
    ])

    return "\n".join(lines)