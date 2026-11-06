# PDF-Review-Entscheidungen v0.2 – separate JSON-Auditdateien

**Stand:** Experimentell, nur lokale Dateien, nicht PostgreSQL oder Nextcloud.

Die HTML-Review-Vorschau bleibt zunächst **rein lesend**. Eine menschliche
Review-Entscheidung wird über die Kommandozeile **explizit** abgegeben
und als **eigenständige JSON-Datei** in einem Ledger-Ordner abgelegt.
Die v0.2-Strukturdatei und darin enthaltenen Original-PDF-Texte,
Tabellenzellen, Bounding-Boxes, Vorschläge und bisherigen Beziehungen
werden dabei **niemals geändert**.

## 1. Tests

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_review_decisions_v02.py' -v
```

## 2. Reviewziel auswählen

Die verfügbaren IDs lassen sich aus dem **validierten** Intel-Dokument
anzeigen:

```bash
python - <<'PY'
import json
p = "/tmp/875p-multipage-structure-v0.2.json"
d = json.load(open(p, encoding="utf-8"))
for e in d["logical_elements"]:
    print(e["logical_id"], repr(e["label"]))
PY
```

Alle Regionen und Beziehungen besitzen ebenfalls eigene IDs. Eine
HTML-Vorschau kann parallel geöffnet bleiben, um den Zielbereich
mit der Originalseite abzugleichen.

## 3. Erste Entscheidung zunächst ohne Schreiben prüfen

Die **konkrete Ziel-ID** aus Schritt 2 einsetzen:

```bash
python -m experiments.pdf_review_decisions_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --ledger-dir /tmp/875p-review-decisions \
  --target-id 'HIER_DIE_ID_EINTRAGEN' \
  --status confirmed \
  --reviewer nina \
  --reason 'Beschriftung und Region visuell gegen das Original-PDF geprüft'
```

Ohne `--apply` erfolgt **nur eine Vorschau**. Es wird weder ein
Ledger-Ordner noch eine Entscheidung angelegt.

**Erst nach der tatsächlichen Prüfung** den gleichen Befehl mit
`--apply` ausführen. Damit wird eine JSON-Datei mit UUID im
Ledger-Ordner neu angelegt (Dateirechte 0600).

`--status rejected` verwendet denselben Mechanismus.

## 4. Spätere Neubewertung

Jede Entscheidung enthält Zeitpunkt (mit Zeitzone), Reviewperson,
Begründung, Quelle-PDF-SHA256, v0.1-Snapshot-SHA256, exakte
Ziel-ID und Ziel-Fingerprint. Eine frühere Entscheidung wird
niemals überschrieben.

Eine Änderung des Status erfordert
`--expected-current <vorherige-entscheidung-uuid>`. Fehlt diese
Angabe oder stimmt sie nicht mehr, erfolgt ein Abbruch.
Dadurch bleiben Änderungen als **lineare Entscheidungshistorie**
nachvollziehbar; gleichzeitige Schreibzugriffe werden über
eine lokale `flock`-Sperre serialisiert.

Für eine zweite Entscheidung dieselbe `--ledger-dir` verwenden,
den neuen Status und die letzte UUID angeben. Die alte Datei bleibt.

## 5. Sicherheits- und Integritätsgrenzen

- Alle Quellstrukturen werden vor jeder Aktion erneut validiert.
- Bei veränderter PDF-/Snapshot-Version, geändertem Zielinhalt,
  unbekannten Zielen, unlesbaren Datensätzen, doppelten Wurzeln,
  verzweigten Entscheidungsketten oder veralteten Entscheidungen
  wird der Vorgang abgebrochen.
- Der Ledger benötigt ein vertrauenswürdiges lokales Dateisystem
  mit funktionierendem Linux-`flock`. Fremde Prozesse, die direkt
  JSON-Dateien bearbeiten, umgehen den vorgesehenen Workflow;
  dies ist **kein manipulationssicheres Archiv**. Für dauerhafte
  Verwendung gehört das Ledger ins bestehende Borg-Backup.
- `--apply` ist die **explizite Bestätigung der Speicherung**,
  nicht eine semantische Freigabe durch ein LLM.
- Eine bestätigte Entscheidung erzeugt **noch keine** Embeddings,
  keine Chunk-Freigabe und keine Datenbankeinträge.
- Status der ursprünglichen Region/Beziehung in der v0.2-Datei
  bleibt `proposed`; die effektive Entscheidung steht nur im Ledger.
- Das vorhandene HTML zeigt den Ledger noch **nicht** an; der
  nächste UI-Schritt kann ihn zusätzlich nur lesend anzeigen.
- Die implementierte Entscheidungsschnittstelle bietet nur
  `confirmed` und `rejected`, keine automatische Korrektur
  oder Freigabe benachbarter Objekte.

**Tipp:** Im Testmodus `/tmp` benutzen. Für dauerhafte Reviews
später einen Ordner innerhalb deines backupgesicherten
Projekt-Datenbestands wählen.
