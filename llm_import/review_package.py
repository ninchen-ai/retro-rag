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