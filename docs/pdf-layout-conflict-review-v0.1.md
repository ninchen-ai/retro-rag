# PDF Layout-Konflikte: Review-Experiment v0.1

Ergänzt die geprüften PDF-Tabellenberichte um **nicht freigegebene**
Konflikthinweise für Fälle wie Intel-875P, PDF-Seiten 35 und 43.

## Drei wesentliche Signale

- `FIGURE_TABLE_CLASS_CONFLICT`: DocLayout-YOLO markiert denselben
  Bereich sowohl als Abbildung als auch als Tabelle (IoU ≥ 0,75).
- `OVERLAPPING_TABLE_REGIONS`: Zwei als Tabelle markierte
  Detektorboxen überdecken mindestens 80 % der kleineren Box.
- `POSSIBLE_MULTIPART_TABLE`: Zwei nicht überlappende Tabellenboxen
  liegen seitlich maximal 12 pt auseinander und überschneiden sich
  vertikal auf mindestens 75 % der kürzeren Höhe.

Zusätzlich weist `PYMUPDF_TABLE_IN_FIGURE` darauf hin, dass eine
PyMuPDF-Tabelle mindestens 80 % innerhalb eines Detektor-Bildbereichs
liegt. Dies ist **kein Beweis**, dass die Extraktion falsch ist.
Eine Region darf mehrere unterschiedliche Hinweise erhalten.
Alle Originaldetections, Zellen und Layoutberichte bleiben unverändert;
**keine automatische Unterdrückung, Umklassifikation oder Zusammenführung**.

## Tests

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_layout_conflict_review.py' -v
```

## Intel-875P: vorhandene Berichte wiederverwenden

```bash
for page in 35 43; do
  python -m experiments.pdf_layout_conflict_review \
    --outline-json /tmp/875p-outline-v0.1.json \
    --quality-json "/tmp/875p-page${page}-quality-review.json" \
    --layout-json "/tmp/875p-page${page}-detection/layout_report.json" \
    --out "/tmp/875p-page${page}-conflicts.json"
done
```

Das Skript verwendet die Original-PDF-Seitendimensionen aus dem
Outline-JSON, vergleicht den Dokument-SHA-256 mit dem Qualitätsbericht
und prüft den Bildnamen. Keine Nextcloud-Abfrage und keine
Modell-Inferenz notwendig. Der einzige Schreibvorgang erzeugt
separate JSONs in `/tmp`.

Die geometrischen Schwellen sind konservative
**Experimentparameter**, keine kalibrierten Wahrscheinlichkeiten.
Bei der visuellen Nachprüfung insbesondere die Differenz zwischen
Figure 6 und Table 5 auf Seite 43 berücksichtigen. Bei Table 5
können linke und rechte Blöcke einer logischen Tabelle entsprechen;
das entscheidet diese Stufe nicht.

## Einschränkungen

- Mehrdeutigkeiten dürfen sich überlagern und führen nicht zu
  eigenständigen Fehlerzahlen.
- Eine nahe Nachbarschaft ist kein Beleg für dieselbe logische
  Tabelle.
- Klassenbezeichnungen kommen aus der tatsächlichen
  DocLayout-YOLO-Ausgabe; andere Modelle können andere Namen
  verwenden.
- Nach wie vor keine Validierung der Zelltranskription,
  Multi-Page-Zuordnung oder automatischen Freigabe.
