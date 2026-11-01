"""Zielmodellvorgaben für die Extraktion aus Mehrmodell-Dokumenten."""


def build_target_model_instruction(
    manufacturer: str,
    model: str,
) -> str:
    """Erstellt eine eindeutige Zielmodellvorgabe für die LLM-Extraktion."""

    if not manufacturer.strip() or not model.strip():
        raise ValueError("Hersteller und Zielmodell müssen angegeben sein")

    return (
        f"Extrahiere ausschließlich Eigenschaften des Hardwaremodells "
        f"{manufacturer} {model}. "
        "Das Quelldokument kann weitere Modellvarianten enthalten. "
        "Übernimm variantenspezifische Eigenschaften anderer Modelle nicht. "
        "Gemeinsame Eigenschaften dürfen nur übernommen werden, wenn das "
        "Quelldokument ihre Gültigkeit für das Zielmodell belegt. "
        "Bei fehlenden, widersprüchlichen oder nicht eindeutig zuordenbaren "
        "Angaben verwende null beziehungsweise eine leere Liste. "
        "Erfinde keine technischen Eigenschaften."
    )