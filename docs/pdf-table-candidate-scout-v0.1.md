# Dokumentübergreifender Tabellen-Vergleichstest: Kandidatensuche v0.1

Dieses Experiment sucht in einem **unveränderten Original-PDF**
gezielt Seiten, die **sowohl** vorgeschlagene Tabellen-Lesezeichen
im bestehenden Outline-JSON **als auch** von PyMuPDF auslesbare
Tabellen enthalten. Die Auswahl beruht ausschließlich auf
geometrischen und strukturellen Signalen, **nicht** auf
fest einprogrammierten Hardware-Begriffen wie USBLEGSUP.

## Durchführung

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_table_candidate_scout.py' -v
```

Ein bereits vorhandenes Intel-875P-Basis-JSON kann für das
Lesezeichen-JSON wiederverwendet werden:

```bash
python -m experiments.pdf_outline_adapter \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf' \
  --base-json /tmp/875p-pdf-structure-v0.1.json \
  --out /tmp/875p-outline-v0.1.json
```

Danach die Vorauswahl auf Intel 875P:

```bash
python -m experiments.pdf_table_candidate_scout \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf' \
  --outline-json /tmp/875p-outline-v0.1.json \
  --max-pages 5 \
  --out /tmp/875p-table-candidates.json
```

Die gemeldeten PDF-Seiten sind **Kandidaten**, noch keine
von DocLayout-YOLO geprüften Tabellen. Für einen unabhängigen
Praxistest sollten wir 2–3 unterschiedliche Seiten aus dem Bericht
auswählen, die unverändert als PNG rendern, das vorhandene
`experiments/doclayout_cpu_benchmark.py` darauf laufen lassen und
erst danach den vorhandenen `pdf_table_quality_review` verwenden.

## Auswahlmechanik

- Nur `element_type=table` mit `review.status=proposed`;
  keine Abbildung, Heading- oder unklaren Lesezeichen.
- Nur Seiten mit Tabellen von mindestens 2 Zeilen und 2 Spalten
  im PyMuPDF-Ergebnis.
- Priorisierung: unterschiedliche Spaltenzahlen und mehrere Tabellen,
  anschließend größere Spaltenzahl; Seitennummer als stabiler Tie-Breaker.
- Die vollständigen Zellen werden nicht in die Vorauswahl
  kopiert; nur Struktur-Metadaten und Warnungen.
- Keine *gleiche Seite = gleiche Tabelle*-Annahme. Der eigentliche
  Outline-/Detektor-/PyMuPDF-Abgleich erfolgt erst nach Inferenz.

## Grenzen

- Ein PDF ohne Tabellen-Lesezeichen liefert hier keine Kandidaten,
  selbst wenn es viele Tabellen enthält; spätere Layout-Only-Kandidaten
  benötigen einen separaten Ansatz.
- Die PyMuPDF-Erkennung ist selbst fehlbar; die Vorauswahl ist
  entsprechend nicht vollständig.
- Ein Aufruf liest das gesamte PDF von Nextcloud, analysiert aber
  mit `find_tables()` nur Seiten mit vorgeschlagenen
  Tabellen-Lesezeichen. Originaldatei, DB, Embeddings und
  Struktur-JSON werden nicht verändert.
- Ergebnisse sind **Review-Vorschläge**, keine geprüften Tabellen.
