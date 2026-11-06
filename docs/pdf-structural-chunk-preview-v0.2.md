# Retro-RAG PDF-Struktur-Chunks – Brücke v0.2 (experimentell)

## Warum kein zweiter PDF-Chunker?

Bereits vorhanden und zu erhalten:

- `scripts/pdf_chapter_chunking.py`: Outline-Hinweise und
  verlustarmes seitenbasiertes Splitten
- `scripts/pdf_section_chunking.py`: überprüfte Titelzeilen als
  Abschnittsgrenzen, nutzt `page.get_text("text", sort=True)`
- `scripts/pdf_chunk_preview.py`: Vorschläge und
  Konflikterkennung für Überschriften
- `scripts/import_pdf.py`: vorhandener separater PDF-Import
  nach PostgreSQL/pgvector, noch nicht an die neuen
  v0.2-Reviews/Tabellenkompositionen angeschlossen

Diese Ansätze benutzen teils unterschiedliche PyMuPDF-Textprofile.
Insbesondere sind `sort=True` und das ursprünglich gespeicherte
`source_v01.pages[].text` **nicht zwangsläufig identisch**.
Das darf beim späteren Einspielen nicht stillschweigend ignoriert werden.

Der neue, schlanke
`experiments/pdf_structural_chunk_preview_v02.py` liest deshalb
**ausschließlich** die unveränderten v0.1-Seitentexte aus dem v0.2-Snapshot.
Er benutzt `split_preserving_text()` aus dem bereits vorhandenen
Chapter-Chunker, bewahrt Leerzeichen und Zeilenumbrüche und weist
für jede Seite nach, dass alle Chunktexte zusammengesetzt
exakt dem Eingabetext entsprechen.

## Tests

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_structural_chunk_preview_v02.py' -v
python -m unittest discover -s tests -p 'test_pdf*.py' -v
```

## Erste Preview mit Intel 875P (keine Freigabe)

```bash
python -m experiments.pdf_structural_chunk_preview_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --max-chars 2500 \
  --out /tmp/875p-structural-chunks-preview.json
```

Die Ausgabe ist eine reine **Text-Chunk-Vorschau** ohne
Kapitelanker. So testen wir die Bewahrung aller ursprünglichen
Seiteninhalte, bevor wir Kapitelgrenzen übernehmen.

Für einen anschließenden Versuch mit einem bereits eindeutig
im Originaltext lokalisierten Outline-Heading kann
`--heading-id outline-00001` wiederholt angegeben werden.
Die exakte ID und Textzeile müssen tatsächlich im Dokument
vorhanden und eindeutig sein; ansonsten verweigert der Adapter
die Grenzzuweisung. **Die Angabe einer ID ist keine Freigabe.**

Die Vorschau markiert sämtliche Chunks ausdrücklich
`proposed`. Sie ist noch kein Indexierungsauftrag und enthält
keine angehängten Tabellenkompositionen.

## Nächste Integrationsschritte

1. Die tatsächlich bestätigten Überschriften/Abschnittsgrenzen
   aus einer nachvollziehbaren Review-Quelle laden statt
   sie nur manuell über CLI-IDs zu wählen.
2. Tabellenkompositionen ausschließlich bei gültiger
   `confirmed`-Entscheidung als separate Wissenseinheiten
   mit Originalquellen anbinden; nicht die 17 Datenzeilen
   noch einmal als unabhängige Tabellen indexieren.
3. Auf Basis dieses einheitlichen Manifests den bereits
   vorhandenen PostgreSQL-/Ollama-Import kontrolliert
   erweitern und in einem Dry-Run gegen die bestehenden
   `knowledge.document`- und `rag.chunk`-Einträge prüfen.
4. Erst nach expliziter Freigabe einen DB-Schreibmodus
   ergänzen und Retrieval-Antworten mit Original-PDF-Seiten
   und Tabelleninhalt testen.

**Schutzgarantien:** Keine automatischen Reviews, keine
PDF-/Nextcloud-/DB-Schreibzugriffe, keine Textnormalisierung
und keine stillen Änderungen an `source_v01` oder
`raw_cells`. Das Originalmodell bleibt maßgeblich.
