# Universelles PDF-Strukturmodell v0.1

Status: experimentell, Review-First, keine produktive Integration.

## Dateien

- `schemas/pdf_document_structure_v0.1.schema.json`: JSON Schema Draft 2020-12.
- `experiments/validate_pdf_structure.py`: Validierung von Typen, IDs, Koordinaten, Referenzen und Review-Konsistenz.
- `experiments/fixtures/pdf_document_structure_v0.1_example.json`: kleines, synthetisches Beispiel.
- `tests/test_pdf_structure_schema.py`: Regressionstests.

## Datenvertrag

- `document`: stabile ID, Quell-URI (ohne Zugangsdaten), SHA-256 der Originalbytes und Seitenzahl.
- `pages[]`: jede PDF-Seite exakt einmal mit Seitengröße, Rotation und unverändertem Extraktionstext. Leere Seiten bleiben enthalten.
- `source_spans[]`: optionaler Geometrieindex zu extrahierten Textspans; nie Text aufgrund vermeintlicher Duplikate löschen.
- `elements[]`: `heading`, `paragraph`, `table`, `figure`, `caption`, `list`, `navigation`, `other` – stets mit Dokumentposition, Provenienz, Review-Status und optionalen Textspan-Verweisen.
- `relationships[]`: Querverweise wie `caption_of`, `continues`; Elternhierarchie durch `parent_id`, nur auf Heading-Elemente, beliebig tief.
- `quality`: Reviewstatus und ein explizites Flag für separat geprüfte Textintegrität.

Koordinaten `bbox_pt`: `[x0,y0,x1,y1]` in Punkten, oben links. Der Erzeuger muss sie auch bei gedrehten Seiten in denselben Koordinatenraum transformieren. Mehrseitige Objekte bestehen in v0.1 aus einzelnen Regionselementen und `continues`-Beziehungen.

## Sicherheits- und Qualitätsgrenzen

Ein korrektes JSON-Schema **beweist nicht**, dass der PDF-Text vollständig oder die Überschrift korrekt erkannt wurde. Diese Prüfung erfolgt außerhalb des Schemas gegen die Original-PDF-Bytes. `text_integrity_checked` wird vom Validator nicht gesetzt. Unsicherheiten bleiben `proposed` bzw. `unclear`; eine Bestätigung oder Ablehnung braucht einen Reviewer. Der Validator schreibt niemals nach Nextcloud oder PostgreSQL.

`confidence` ist optional und nicht detektorübergreifend kalibriert. Textlose Figuren und Layoutregionen dürfen leere `source_span_ids` haben; das bedeutet nicht Freigabe. Tabellenzellen und Bildsemantik sind bewusst noch nicht modelliert; `table` und `figure` sind derzeit Regionen.

## Tests auf Poseidon

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_structure_schema.py' -v
```

Zur vollständigen JSON-Schema-Prüfung optional in der Entwicklungsumgebung:

```bash
python -m pip install 'jsonschema>=4.20,<5'
python -m experiments.validate_pdf_structure experiments/fixtures/pdf_document_structure_v0.1_example.json
```

Ohne das Zusatzpaket laufen die reinen Standardbibliothek-Integritätstests; die zwei schemaabhängigen Tests werden übersprungen. Die produktiven `requirements.txt` wurden nicht verändert.

## Nächste Ausbaustufe (noch nicht implementiert)

Adapter für PDF-Outline, gedrucktes Inhaltsverzeichnis und Layoutanalyse liefern dasselbe Schema. Eine nachfolgende Zuordnung kombiniert Belege über Text und Position, ohne widersprüchliche Kandidaten stillschweigend zu verwerfen. Erst nach qualifiziertem Review folgt die verlustfreie Chunk-Vorschau. AGP, Intel 875P, DirectX, EHCI, USB 1.0/2.0 und xHCI bilden den unabhängigen Testbestand.
