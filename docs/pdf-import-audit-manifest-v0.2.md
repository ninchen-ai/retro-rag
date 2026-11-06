# PDF-Import: gemeinsames Audit-Manifest v0.2

## Ziel

Die bestehenden Komponenten verbinden, **ohne** die Pipeline neu zu bauen:

- `scripts/pdf_heading_alignment.py`: bereits implementierte
  Überschriftenzuordnung, auch für zweizeilige PDF-Titel;
- `experiments/pdf_structural_chunk_preview_v02.py`:
  seitentextgetreue, derzeit noch nicht freigegebene Textchunk-Vorschau;
- `experiments/pdf_review_decisions_v02.py`:
  geprüfter Ledger für physische Regionen, logische Elemente und Beziehungen;
- `experiments/pdf_table_composition_review_v02.py`:
  separater Ledger der ausdrücklich bestätigten Tabellenzusammensetzungen;
- `scripts/import_pdf.py`: existierender PostgreSQL/pgvector-Importer,
  **hier nicht aufgerufen oder verändert**.

`experiments/pdf_import_manifest_v02.py` vereinigt diese
Informationen in einem JSON-**Audit-Manifest**, kein produktiver Import.

### Wichtig: Sicherheitsgrenze der Dublettenprüfung

Die Seite 43 enthält den ursprünglichen extrahierten PDF-Text **und**
die bestätigte Table-5-Komposition. Der Text kann Tabellenzellen bereits
enthalten. Einfaches Auslassen der Seite wäre Datenverlust, und
automatisches Herauslöschen von Tabellenwerten aus dem Seitentext wäre
ohne verifizierte Span-/Zeichenpositionen riskant.

Deshalb markiert das Manifest die Textchunks der betroffenen Seite und
die gesonderte Tabellen-Wissenseinheit als
`blocked_possible_table_duplication`. Die übrigen Textchunks bleiben
`not_approved`. **Keiner** darf automatisch indexiert werden.

Die Tabellen-Wissenseinheit enthält die im Ledger geprüfte
Kompositionsentscheidung, die beiden Ursprungsregionen, Originalzeilen-
Referenzen und ausgesparte Vorschauzeilen.

**Confirmed composition** bedeutet nicht automatisch:
- logisches Tabellenobjekt bestätigt,
- sämtliche Caption- und Regionsbeziehungen bestätigt,
- Tabelle ohne Dopplung indexierbar,
- Gesamt-PDF importfreigegeben.

### Heading-Diagnose

Die vorhandene Funktion `align_page_headings()` wird auf
`source_v01.pages[].text` angewendet, mit den schon im
`pdf_outline_adapter` vorgesehenen Titelvarianten.

Das Ergebnis (`heading_alignment_audit`) enthält die Kandidaten,
Positionsdiagnosen und Statuszahlen. Auch ein `MATCHED`
ist **nur eine Zuordnungshilfe**, noch keine Kapitel-Freigabe.

Wichtig: Das gespeicherte v0.1-Profil enthält unsortierten PyMuPDF-
Seitentext. Einige ältere Chunker nutzen `sort=True`. Ein
`start_line` aus einem anderen Extraktionsprofil darf nicht
unbesehen übernommen werden.

## Auf Poseidon testen

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_import_manifest_v02.py' -v
```

## Intel-875P-Audit-Manifest erzeugen

```bash
python -m experiments.pdf_import_manifest_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --review-ledger-dir /data/projects-data/retro-rag/reviews/875p \
  --composition-json /tmp/875p-table5-composition-v0.1.json \
  --composition-ledger-dir /data/projects-data/retro-rag/table-compositions/875p \
  --max-chars 2500 \
  --out /tmp/875p-import-audit-manifest-v0.1.json
```

Danach kannst du eine kurze Zusammenfassung rein lesend ausgeben:

```bash
python - <<'PY'
import json
from pathlib import Path
p=Path('/tmp/875p-import-audit-manifest-v0.1.json')
d=json.loads(p.read_text(encoding='utf-8'))
print('Text-Chunks:', d['text_chunk_count'])
print('Tabelle:', d['table_composition_decision_status'])
print('Überschriften:', d['heading_alignment_audit']['status_counts'])
print('Blocker:', [b['code'] for b in d['blockers']])
print('Index freigegeben:', d['import_approved'])
PY
```

**Erwartung:** Bestehende bestätigte Komposition wird sichtbar,
`import_approved == False`, Textrekonstruktion stimmt.

## Noch offen bis zum wirklichen Import

1. **Revisionsfeste Heading-Freigaben** und Übernahme eindeutiger
   Abschnittsanker ins Manifest.
2. **Geprüfte Zeichen-/Span-Zuordnung** der Tabellentexte, um
   Doppelindexierung zu verhindern und trotzdem den Originaltext
   vollständig zu bewahren.
3. Durchgehende Review-Gates und später ein explizit autorisierter
   Indexierungsmodus im vorhandenen Importer.
4. End-to-End-Test Retrieval / Quellenstellen / Tabellenantworten.

Das Manifest ist ein Testartefakt; es führt weder Ollama-API-Aufrufe
noch PostgreSQL-/Nextcloud-Schreiboperationen durch.
