
"""Strukturierte Hardwaredaten aus Markdown-Chunks extrahieren."""

import yaml



def extract_hardware_facts(primary_passages):
    """Extrahiert Hardwaredaten aus den indexierten Markdown-Chunks."""

    facts = []

    for passage in primary_passages:
        content = passage["content"]
        lines = content.splitlines()

        header_lines = []

        for line in lines:
            if line.startswith("# "):
                break
            header_lines.append(line)

        # Leerzeilen und YAML-Trennzeichen entfernen.
        while header_lines and not header_lines[0].strip():
            header_lines.pop(0)

        if header_lines and header_lines[0].strip() == "---":
            header_lines.pop(0)

        # Der bestehende Importer setzt diese Dokumentkennung
        # als erste Zeile vor die YAML-Metadaten.
        if (
            header_lines
            and header_lines[0].strip()
            == "Hardware-/Retro-Computing-Dokument"
        ):
            header_lines.pop(0)

        # Abschließendes YAML-Trennzeichen entfernen.
        while header_lines and (
            not header_lines[-1].strip()
            or header_lines[-1].strip() == "---"
        ):
            header_lines.pop()

        header = "\n".join(header_lines)

        if not header.strip():
            raise ValueError(
                f"Keine YAML-Metadaten in {passage['key']}"
            )

        try:
            metadata = yaml.safe_load(header)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"Ungültige YAML-Metadaten in "
                f"{passage['key']}: {exc}"
            ) from exc

        if not isinstance(metadata, dict):
            raise ValueError(
                f"Ungültige Metadatenstruktur in "
                f"{passage['key']}"
            )

        if metadata.get("type") != "hardware_model":
            continue

        specs = metadata.get("specs") or {}

        if not isinstance(specs, dict):
            raise ValueError(
                f"Ungültige Hardware-Spezifikationen in "
                f"{passage['key']}"
            )

        facts.append({
            "document_key": passage["key"],
            "manufacturer": metadata.get("manufacturer"),
            "model": metadata.get("model"),
            "variant": metadata.get("variant"),
            "specs": specs,
        })

    return facts



def format_hardware_facts(facts):
    """Erstellt einen eindeutig nach Modellen getrennten Kontext."""

    lines = ["STRUKTURIERTE HARDWAREDATEN:"]

    if not facts:
        return ""

    for fact in facts:
        lines.append(
            f"\nMODELL: {fact['manufacturer']} "
            f"{fact['model']} "
            f"{fact['variant'] or ''}"
        )

        lines.append(
            f"QUELLE: {fact['document_key']}"
        )

        specs = fact["specs"]

        for key, value in specs.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    lines.append(
                        f"{key}.{subkey}: {subvalue}"
                    )
            else:
                lines.append(f"{key}: {value}")

    return "\n".join(lines)
