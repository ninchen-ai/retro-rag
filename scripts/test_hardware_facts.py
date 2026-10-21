
#!/usr/bin/env python3
"""Regressionstest für strukturierte Hardwarevergleiche."""

from scripts.hardware_facts import (
    extract_hardware_facts,
    format_hardware_facts,
)


def run_test():
    samples = [
        {
            "key": "model-a",
            "content": """Hardware-/Retro-Computing-Dokument
type: hardware_model
manufacturer: Test
model: Alpha
specs:
  socket: Slot 1
  memory_slots: 4
  expansion_slots:
    pci: 5

# Alpha
Testhardware.
""",
        },
        {
            "key": "model-b",
            "content": """Hardware-/Retro-Computing-Dokument
type: hardware_model
manufacturer: Test
model: Beta
specs:
  socket: Socket 370
  memory_slots: 3
  expansion_slots:
    pci: 6

# Beta
Testhardware.
""",
        },
    ]

    facts = extract_hardware_facts(samples)

    by_model = {
        fact["model"]: fact["specs"]
        for fact in facts
    }

    assert len(facts) == 2
    assert by_model["Alpha"]["socket"] == "Slot 1"
    assert by_model["Beta"]["socket"] == "Socket 370"
    assert by_model["Alpha"]["memory_slots"] == 4
    assert by_model["Beta"]["memory_slots"] == 3
    assert by_model["Alpha"]["expansion_slots"]["pci"] == 5
    assert by_model["Beta"]["expansion_slots"]["pci"] == 6

    output = format_hardware_facts(facts)

    assert "MODELL: Test Alpha" in output
    assert "MODELL: Test Beta" in output

    print("PASS: Hardwaredaten korrekt zugeordnet")


if __name__ == "__main__":
    run_test()
