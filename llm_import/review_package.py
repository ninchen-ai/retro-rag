"""Plant Review-Pakete ohne Datei- oder Netzwerkzugriff."""

import re


def safe_name(value: str) -> str:
    """Erlaubt ausschließlich einfache Dateinamen."""

    if not isinstance(value, str):
        raise ValueError("Dateiname muss ein String sein")

    value = value.strip()

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError(f"Unsicherer Dateiname: {value!r}")

    if value in {".", ".."}:
        raise ValueError("Ungültiger Dateiname")

    return value


def plan_review_package(
    import_result: dict,
    root: str = "Retro-Computing/Import/review",
) -> list[dict]:
    """Erzeugt einen Uploadplan ohne Schreibzugriff."""

    results = import_result.get("results") or []

    if not results:
        raise ValueError("Keine Modellergebnisse vorhanden")

    if root != "Retro-Computing/Import/review":
        raise ValueError("Review-Zielverzeichnis nicht erlaubt")

    source_hashes = {
        (item.get("source") or {}).get("sha256")
        for item in results
    }

    if len(source_hashes) != 1:
        raise ValueError(
            "Modellergebnisse stammen nicht aus derselben Quelle"
        )

    source_hash = source_hashes.pop()

    if not isinstance(source_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", source_hash
    ):
        raise ValueError("Ungültiger SHA-256-Quellhash")

    package_root = f"{root}/{source_hash[:16]}"

    plan = []
    seen_paths = set()

    for item in results:
        classification = item.get("classification") or {}
        model = safe_name(classification.get("model", ""))

        markdown = item.get("markdown")
        review_markdown = item.get("review_markdown")

        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError(
                f"Hardwaresteckbrief fehlt: {model}"
            )

        if not isinstance(review_markdown, str) or not review_markdown.strip():
            raise ValueError(
                f"Review-Bericht fehlt: {model}"
            )

        for filename, content in (
            (f"{model}.md", markdown),
            (f"{model}.review.md", review_markdown),
        ):
            path = f"{package_root}/{model}/{filename}"

            if path in seen_paths:
                raise ValueError(f"Doppelter Zielpfad: {path}")

            seen_paths.add(path)

            plan.append({
                "path": path,
                "content": content,
                "status": "PLANNED",
            })

    return plan

def plan_review_directories(
    file_plan: list[dict],
    root: str = "Retro-Computing/Import/review",
) -> list[str]:
    """Ermittelt benötigte Verzeichnisse in Eltern-Kind-Reihenfolge.

    Keine Netzwerk- oder Schreiboperationen.
    """

    if root != "Retro-Computing/Import/review":
        raise ValueError("Review-Zielverzeichnis nicht erlaubt")

    if not file_plan:
        raise ValueError("Leerer Review-Paketplan")

    directories = set()

    for entry in file_plan:
        if not isinstance(entry, dict):
            raise ValueError("Ungültiger Planeintrag")

        path = entry.get("path")

        if not isinstance(path, str):
            raise ValueError("Ungültiger Dateipfad")

        prefix = root + "/"

        if not path.startswith(prefix):
            raise ValueError("Dateipfad außerhalb des Review-Bereichs")

        parts = path[len(prefix):].split("/")

        if len(parts) != 3:
            raise ValueError("Unerwartete Review-Pfadstruktur")

        source_id, model, filename = parts

        if source_id != safe_name(source_id):
            raise ValueError("Ungültige Paket-ID")

        if not re.fullmatch(r"[0-9a-f]{16}", source_id):
            raise ValueError("Ungültige Paket-ID")

        if model != safe_name(model):
            raise ValueError("Ungültiger Modellname")

        if filename not in {
            f"{model}.md",
            f"{model}.review.md",
        }:
            raise ValueError("Unerwarteter Review-Dateiname")

        directories.add(f"{root}/{source_id}/")
        directories.add(f"{root}/{source_id}/{model}/")

    return sorted(
        directories,
        key=lambda path: (path.count("/"), path),
    )