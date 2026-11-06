# Retro-RAG PDF-Strukturmodell v0.2 – Implementierung (experimentell)

## Leitprinzip: Originalstruktur bleibt erhalten

v0.2 ist **additiv**, nicht destruktiv. Das komplette v0.1-JSON
liegt unverändert unter `source_v01`, mitsamt Dokument-Hash,
Seiten, Originalextraktionstext, Textspans, v0.1-Elementen und
bestehenden Beziehungen. `source_v01_sha256` schützt den Snapshot
gegen unbemerkte nachträgliche Änderungen innerhalb der v0.2-Datei.

Die Prüfsumme ist ein Integritätsmerkmal **gegen den gespeicherten
Snapshot**, kein Ersatz für die erneute SHA256-Prüfung des PDF.
Auch PyMuPDF-Zellmatrizen sind *Extraktionsergebnisse*, kein Beweis
für fehlerfreie Transkription des visuellen Originals.

Die neuen Sammlungen sind:

| Sammlung | Bedeutung |
|---|---|
| `physical_regions` | Einzelne PDF-Detektorregionen, PyMuPDF-Tabellenmatrizen und Captionbereiche mit eigener ID/Provenienz |
| `logical_elements` | Logische Tabelle/Abbildung als **unbestätigter** Vorschlag |
| `relationships_v02` | Caption-, Region-, Extraktions- und Konfliktbeziehungen (unbestätigt) |
| `review_decisions` | Getrennte, auditierbare Entscheidungen mit Person, Zeit und Dokument-Hash |
| `processing_runs` | Methode/Modell und Quell-PDF-Hash zur Provenienz |
| `quality_v02` | Kennzeichnung, dass die Zusammenführung weiterhin unreviewed ist |

`has_region` und `possible_same_table` beschreiben Vorschläge:
**keine** automatische Verschmelzung mehrteiliger Tabellen.
Insbesondere Intel-875P Table 5 behält linke und rechte
Original-Zellmatrix separat. `raw_cells` enthält die unveränderten
Werte einschließlich `null` und Zeilenumbrüchen.

Die `review`-Status der extrahierten Regionen, logischen
Vorschläge und Beziehungen bleiben `proposed`. Falls später
Menschen entscheiden, erzeugen wir getrennte
`review_decisions`; der Validator verlangt Reviewer, Zeit,
Begründung und passende PDF-Version. Die Entscheidung verändert
**nicht** den Originalvorschlag. Keine Entscheidung führt in
dieser Stufe zu produktiver Indizierung.

## Testen auf Poseidon

```bash
cd ~/projects/retro-rag
git pull --ff-only

python -m unittest discover \
  -s tests \
  -p 'test_pdf_structure_v02.py' -v
```

### A. Existierendes Intel-875P-v0.1 ohne Änderungen upgraden

```bash
python -m experiments.pdf_structure_v02 \
  --v01-json /tmp/875p-outline-v0.1.json \
  --out /tmp/875p-structure-v0.2.json
```

Dadurch entsteht ein gültiges, zunächst leeres v0.2-Modell,
in dem der gesamte v0.1-Snapshot exakt enthalten ist.

### B. Reale Beobachtungen von Seite 43 ergänzen

```bash
python -m experiments.pdf_structure_v02_assemble \
  --v01-json /tmp/875p-outline-v0.1.json \
  --layout-json /tmp/875p-page43-detection/layout_report.json \
  --quality-json /tmp/875p-page43-quality-review.json \
  --caption-json /tmp/875p-page43-captions.json \
  --conflict-json /tmp/875p-page43-conflicts.json \
  --out /tmp/875p-page43-structure-v0.2.json
```

Auch Seite 35 ist mit den entsprechenden Dateien testbar
(die Dateinamen der letzten Stufe entsprechen den vorigen
Experimenten). Diese erste Version erzeugt jeweils **ein
separates Review-Modell für eine Seite**, mit dem vollständigen
v0.1-Dokument als eingebettetem Original-Snapshot. Ein späterer
seitenübergreifender Merge muss auf IDs/Konflikte geprüft werden,
bevor wir ihn implementieren.

## Validierte Schranken

- v0.1-Daten werden erneut nach dem **unveränderten** v0.1-Schema
  und dem Cross-Reference-Validator geprüft.
- v0.1-Snapshot-Fingerprint und Quell-PDF-SHA256 von Adapterläufen,
  Caption-, Qualitäts- und Konfliktbericht müssen übereinstimmen.
- Jede neue ID ist innerhalb des Dokuments eindeutig.
- Region-Koordinaten müssen innerhalb ihrer Quellseite liegen.
- Jede Region referenziert einen bekannten Processing-Run
  mit übereinstimmender Methode; Source-Span-Verweise werden geprüft.
- Beziehungen dürfen keine fehlenden Ziele oder Self-Links haben.
- Manuelle Entscheidungen referenzieren bekannte Ziele und die
  konkrete PDF-Version. Der ursprüngliche Vorschlag bleibt erhalten.

## Grenzen / offener Ausbau

- Nur **einseitige Beobachtungszusammenführung**; kein Merge
  mehrerer Seiten und noch keine mehrseitigen Tabellen.
- Keine automatisierte Semantikentscheidung zu Figure/Table-
  Konflikten oder Table-5-Gesamtregion vs. Teilbereichen.
- Quelle ist der v0.1-Extraktionstext; keine unabhängige OCR-
  Vollständigkeitsprüfung.
- Keine automatische RAG-Chunk-Erstellung, kein PostgreSQL-
  Schema, keine Datenbankschreiboperationen und keine Änderung
  an Nextcloud. v0.1 und alle bisherigen Module bleiben bestehen.

Die neue JSON-Schema-Datei liegt unter
`schemas/pdf_document_structure_v0.2.schema.json`.
Der Validator und Adapter sind
`experiments/pdf_structure_v02.py` und
`experiments/pdf_structure_v02_assemble.py`.
