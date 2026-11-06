# PDF-Tabellenzusammensetzung v0.2 – kontrollierter Fortsetzungsvorschlag

**Umfang:** Ein logisches Tabellenobjekt mit mehreren nebeneinander
angeordneten PyMuPDF-Matrizen, die denselben Tabellenkopf besitzen.
**Keine** automatische PDF-, v0.2-, PostgreSQL- oder Nextcloud-Änderung.

## Belegfall Intel 875P – Seite 43 / Table 5

- Logische Tabelle: `v02-p43-logical-1`
- Linker PyMuPDF-Block: `v02-p43-pymupdf-1`
- Rechter PyMuPDF-Block: `v02-p43-pymupdf-2`
- Zwei gleichartige Tabellenüberschriften.
- Linke Werte: `00000` bis `00111`.
- Rechte Werte: `01000` bis `01111`, zusätzlich `1xxxx`.
- Voraussichtliche **abgeleitete** Ansicht: 2 Spalten, 1 Kopfzeile,
  17 Datenzeilen (8 links + 9 rechts).

Die originale leere zehnte Zeile des linken Blocks und die
wiederholte Kopfzeile rechts bleiben **in den unveränderten
`raw_cells` erhalten**. Sie werden nur in der abgeleiteten
Vorschau als `empty_row` beziehungsweise `repeated_header`
gekennzeichnet und ausgeblendet.

### 1. Tests auf Poseidon

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_table_composition*.py' -v
python -m unittest discover -s tests -p 'test_pdf*.py' -v
```

Nur nach erfolgreichen Tests die neuen Browserfunktionen benutzen.

### 2. Kompositionsvorschlag erstellen

Auf Poseidon:

```bash
python -m experiments.pdf_table_composition_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --logical-id v02-p43-logical-1 \
  --regions v02-p43-pymupdf-1 v02-p43-pymupdf-2 \
  --out /tmp/875p-table5-composition-v0.1.json
```

Erzeugt nur ein **separates Vorschlags-JSON**, nicht das v0.2-Original
und keine Entscheidungsdatei.

### 3. Getrennten Ledger für Tabellenzusammensetzungen vorbereiten

**Achtung:** Kompositionsentscheidungen besitzen ein anderes
JSON-Schema und dürfen **nicht** im vorhandenen
`/data/projects-data/retro-rag/reviews/875p` landen.
Dessen Validator würde solche Dateien zurückweisen.

```bash
mkdir -p /data/projects-data/retro-rag/table-compositions/875p
chmod 700 /data/projects-data/retro-rag/table-compositions/875p
```

Der Pfad liegt bereits im Sicherungsumfang von Poseidons
Borg-Skript. Neue Entscheidungen erscheinen erst nach dem
nächsten vollständigen Borg-Lauf in einem Backup-Archiv.

### 4. Interaktiven Reviewserver starten

Vorher den alten Server auf Port 8765 mit `Ctrl+C` beenden.

```bash
python -m experiments.pdf_review_server_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --page 43 \
  --image /tmp/875p-page43.png \
  --ledger-dir /data/projects-data/retro-rag/reviews/875p \
  --composition-json /tmp/875p-table5-composition-v0.1.json \
  --composition-ledger-dir /data/projects-data/retro-rag/table-compositions/875p \
  --port 8765
```

Auf Iris wie bisher den SSH-Lokaltunnel nutzen:

```bash
ssh -N -L 8765:127.0.0.1:8765 nina@poseidon.heinz.home
```

In Iris' Firefox: `http://127.0.0.1:8765/`

Die Seite zeigt jetzt zusätzlich **Tabellen-Zusammensetzung**
mit einer kombinierten zweispaltigen Vorschau, Herkunft jeder
Datenzeile (Tooltip), Informationen zu ausgeblendeten
Vorschauzeilen und eigener Entscheidungsmöglichkeit.

### 5. Review-Regeln

1. Original-PDF und beide originalen PyMuPDF-Zellmatrizen ansehen.
2. Reihenfolge und Interpretation prüfen.
3. `confirmed` oder `rejected` mit konkreter Begründung wählen.
4. **Tabellenentscheidung vorbereiten**: Nur Dry-Run, kein Schreiben.
5. **Tabellenentscheidung verbindlich speichern** und die zweite
   Bestätigung akzeptieren.
6. Erst dadurch entsteht eine **eigene** JSON-Entscheidungsdatei
   unter `/data/projects-data/retro-rag/table-compositions/875p/`.

Die Entscheidung betrifft **nur die Tabellenzusammensetzung**.
Sie bestätigt weder die bisherigen YOLO-Regionen noch bestehende
Relations-Vorschläge. Der aktuelle RAG-Indexer wertet diese
Kompositionsentscheidungen **noch nicht** aus.

### Grenzen

- Nur horizontale Fortsetzungen mit gleicher Kopfzeile und mindestens
  75 % gemeinsamer vertikaler Ausdehnung.
- Kein automatisches Zusammenführen beliebiger Tabellen.
- Keine Änderungen am v0.2-Strukturmodell, an Text, Rohmatrizen
  oder PDF-Originalen.
- Der Server bleibt **nur auf 127.0.0.1**, nicht öffentlich anbieten.
- Die Komposition ist zunächst als Experiment für Page 43 testbar;
  spätere Kapitel-/Chunking- und pgvector-Integration separat.
