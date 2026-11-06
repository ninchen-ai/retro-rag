# Dokumentweiter v0.2-Review-Merge v0.1 (experimentell)

Dieses Modul vereinigt **separat assemblierte v0.2-Seitenberichte**
für **dieselbe exakte v0.1-Quellstruktur**. Es überschreibt weder
PDF noch Nextcloud, PostgreSQL, Embeddings oder vorhandene JSON-Eingaben.

**Wichtig:** Dies ist ein dokumentweiter *Beobachtungs-Merge*, keine
semantische Zusammenführung zweier Tabellenblöcke oder eine
automatische Freigabe. Originaldaten und extrahierte Matrizen bleiben
pro Region getrennt.

## Test auf Poseidon

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_structure_v02_merge.py' -v
```

Für die Intel-875P-PDF liegt bereits ein v0.2-Bericht der
Seite 43 vor: `/tmp/875p-page43-structure-v0.2.json`.

### Seite 35 ebenfalls assemblieren

```bash
python -m experiments.pdf_structure_v02_assemble \
  --v01-json /tmp/875p-outline-v0.1.json \
  --layout-json /tmp/875p-page35-detection/layout_report.json \
  --quality-json /tmp/875p-page35-quality-review.json \
  --caption-json /tmp/875p-page35-captions.json \
  --conflict-json /tmp/875p-page35-conflicts.json \
  --out /tmp/875p-page35-structure-v0.2.json
```

### Beide Seiten in ein dokumentweites v0.2-JSON übernehmen

```bash
python -m experiments.pdf_structure_v02_merge \
  --inputs \
    /tmp/875p-page35-structure-v0.2.json \
    /tmp/875p-page43-structure-v0.2.json \
  --out /tmp/875p-multipage-structure-v0.2.json
```

Die Ausgabe meldet Anzahl der Eingabeseiten, physischen
Regionen, logischen Elemente, Beziehungen und den ursprünglichen
v0.1-Snapshot-Fingerprint.

## Sicherheits- und Datenregeln

- Alle Eingaben werden zunächst vollständig nach v0.2-Schema,
  v0.1-Schema und Cross-References geprüft.
- Eingebettete `source_v01` müssen in **Inhalt und SHA-256**
  übereinstimmen; unterschiedliche Dokumentversionen werden
  abgelehnt.
- Jede Eingabe muss über `processing_runs.parameters.page`
  **genau eine Seite** belegen; Duplikatseiten werden abgelehnt.
- Gleiche Regions-/Element-/Beziehungs-/Entscheidungs-/Run-IDs
  aus verschiedenen Eingaben werden **nicht** stillschweigend
  dedupliziert oder umbenannt, sondern führen zum Abbruch.
- Die Arrays werden nach ursprünglicher PDF-Seitennummer sortiert.
  So liefert eine vertauschte CLI-Eingabereihenfolge dasselbe JSON.
- Originale PyMuPDF-Matrizen bleiben unverändert einschließlich
  leerer Zellen und `null`-Werte.
- Bestehende menschliche Review-Entscheidungen werden übertragen,
  nicht neu erzeugt oder auf `review.status` zurückgeschrieben.
- Die fertige Datei wird nach der Vereinigung erneut validiert.

**Integrität:** Der Snapshot-Hash ist der kanonische SHA-256
des JSON-Inhalts. Er belegt *Wertgleichheit* des v0.1-Objekts,
nicht Byte-Gleichheit der ursprünglichen v0.1-JSON-Datei.
Der PDF-SHA-256 bleibt separat in `document.sha256` erhalten.

## Grenzen

Der Merge ist zunächst konservativ: Eine Eingabedatei pro
PDF-Seite; derselbe Seitenbericht kann nicht mehrfach hinzugefügt
werden. Wiederholte Detektorläufe auf einer Seite und
seitenübergreifende logische Tabellenbeziehungen benötigen
später eigene, explizite Versions- und Review-Regeln.

EHCI und Intel 875P müssen in **getrennten** v0.2-Dokumenten
bleiben, da ihre Dokument-Hashes unterschiedlich sind. Die
bestehenden EHCI-Einzelseitenberichte dienen als Regressionstest
für die v0.2-Assemblerfunktion; sie dürfen nicht mit Intel
875P in einer einzigen Dokumentdatei vermischt werden.
