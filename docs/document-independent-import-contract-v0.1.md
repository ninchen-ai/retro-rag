# Dokumentunabhängiger Importvertrag v0.1 – experimentell

## Architekturentscheidung

**Nextcloud bleibt führende Quelle.** Bestehende produktive Pfade werden
nicht ersetzt:

- `scripts/import_pg.py` validiert und synchronisiert Markdown-
  Hardwaremodell-/Inventar-/Systemdokumente;
- `scripts/index_embeddings.py` indexiert deren Text;
- `scripts/sync_pdfs.py` und `scripts/import_pdf.py` behandeln PDF-
  Dokumente und deren Lebenszyklus;
- `experiments/pdf_import_manifest_v02.py` bündelt PDF-Text,
  Outline-Diagnose und geprüfte Tabellenkompositionen – immer read-only.

Der neue `experiments/import_contract_v01.py` ist der erste
**formatneutrale** Vertrag auf dem Weg zu einer einheitlichen
Pipeline. `experiments/import_contract_adapters_v01.py` enthält
zwei Adapter für bereits vorhandene Formate. Keines der beiden
Module greift auf eine Datenbank zu.

## Gemeinsame Felder

`document`: `source_system`, `source_id`,
`source_uri`, `source_sha256`, `format`,
`document_kind`, `title`.

`units[]`: `unit_id`, `unit_kind` (text/table/figure/metadata),
Original-/Darstellungstext `content`, `content_sha256`,
`source` (Seitenbereich und Ursprungsreferenzen),
`review_status`, `index_disposition`, `metadata`.

`review` und `indexing`: In v0.1 **immer unreviewed/blocked**.
Ein Objekt mit `indexing.allowed=true` wird abgewiesen. Eine
erfolgreiche Schema-/Hash-Prüfung ist **keine Freigabe**.

PDF-Tabellen werden noch **nicht dedupliziert**: Text und
Tabellenvorschau bleiben getrennte, nicht indexierbare
Einheiten mit Provenienz und Prüfstatus. Tabellenzellen im
Originaltext werden nicht entfernt.

Bei Markdown wird **der vorhandene YAML-Validator**
`scripts.import_pg.parse_md` wiederverwendet. Die
bestehenden Domänentypen `hardware_model`,
`inventory_item`, `system` bleiben erhalten.

## Ausprobieren auf Poseidon

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_import_contract_v01.py' -v
```

Das bereits geprüfte Intel-875P-Audit kann lokal in einen
formatneutralen *Vorschlag* transformiert werden:

```bash
python -m experiments.import_contract_adapters_v01 \
  --pdf-audit /tmp/875p-import-audit-manifest-v0.1.json \
  --source-uri 'nextcloud://nina/Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf' \
  --source-id '875p-experiment' \
  --title 'Intel 875P Chipset Datasheet' \
  --out /tmp/875p-common-import-contract-v0.1.json
```

`source-id` in diesem Beispiel ist **nur eine
experimentelle Bezeichnung**, nicht die tatsächliche
Nextcloud-Datei-ID. Für eine produktive Verarbeitung muss
die Identität später aus der verifizierten Nextcloud-
Dateimetadatenkette stammen.

Auch ein beliebiges bereits gültiges lokales
Hardware-Markdown kann so konvertiert werden:

```bash
python -m experiments.import_contract_adapters_v01 \
  --markdown-file /pfad/zum/hardware-model.md \
  --source-uri 'nextcloud://nina/Retro-Computing/...' \
  --source-id 'test-only' \
  --out /tmp/markdown-common-import-contract-v0.1.json
```

### Offene Aufgaben

1. Quellidentität und Hash über Nextcloud-Datei-ID und
   Version verpflichtend prüfen; Adapter-CLI allein stellt
   keine Herkunftsauthentifizierung sicher.
2. Konkretes, versionsgebundenes, revisionsfestes Review-
   und Freigabeformat für einzelne Chunks entwickeln.
3. Bei PDF Tabellenzellen anhand überprüfbarer
   Span-/Zeichenreferenzen zuordnen und die
   Doppelindexierung ausschließen; nie Originaltext löschen.
4. `source_v01`-Textprofil und ältere `sort=True`-
   Extraktion explizit überführen, nicht vermischen.
5. Erst nach Tests und ausdrücklicher Freigabe einen
   transaktionalen Indexierungsadapter ergänzen, der die
   bestehenden Datenbanktabellen nutzt und die aktive
   Pipeline nicht unbemerkt ersetzt.

**Kein produktiver Import, keine Embeddings, keine
Nextcloud-/PostgreSQL-Schreibzugriffe und keine automatische
Freigabe in diesem Entwicklungsschritt.**
