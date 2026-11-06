# Dokumentübergreifende Tabellen-Kandidatensuche v0.2

Die Erfahrung mit dem Intel-875P-Datenblatt zeigt: **Tabellen können
vorhanden sein, obwohl es kein einziges Tabellen-Lesezeichen gibt.**
Deshalb ist `--mode all` jetzt der Standard. PyMuPDF untersucht jede
unrotierte PDF-Seite; Lesezeichen ergänzen Kontext, begrenzen aber nicht
mehr die Kandidatensuche.

`--mode outline` erhält das frühere Verhalten für gezielte Diagnosen.
Alle Ergebnisse bleiben ungeprüft; es erfolgt keine Detektor-Inferenz,
keine Veröffentlichung und keine Änderung an Quelle, Datenbank,
Embeddings oder vorhandenem Outline-JSON.

## Intel-875P-Praxistest

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_table_candidate_scout.py' -v

python -m experiments.pdf_table_candidate_scout \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf' \
  --outline-json /tmp/875p-outline-v0.1.json \
  --mode all --max-pages 5 \
  --out /tmp/875p-table-candidates.json
```

Das Skript prüft bei diesem Dokument bis zu 174 Seiten mit PyMuPDF
und berichtet sowohl die Zahl tatsächlich geprüfter Seiten als auch
den Seitenumfang mit Tabellen-Lesezeichen. Es kann daher länger dauern
als die alte Lesezeichen-begrenzte Vorauswahl.

Die Ausgabe zeigt die fünf bevorzugten Seiten, deren tatsächlich
erkannten Tabellen die größte Variation von Spaltenanzahlen und
Tabellenanzahl aufweisen. Ausgabe ohne Kandidaten bedeutet, dass
PyMuPDF mit den Schwellen (mindestens 2 Zeilen, 2 Spalten) nichts
gefunden hat – **nicht** zwingend, dass keine Tabellen existieren.

## Nächster Schritt

Aus der Vorauswahl zwei bis drei unterschiedliche Seiten als PNG
rendern und mit dem bestehenden
`experiments/doclayout_cpu_benchmark.py` auf CPU detektieren.
Danach `experiments/pdf_table_quality_review.py` ausführen.
Ohne Tabellen-Lesezeichen enthält der Qualitätsbericht zwar
Detektor→PyMuPDF-Zuordnungen, aber **keine** erfundene
Caption→Detektor-Zuordnung. Diese Einschränkung ist bewusst und
erfordert eine spätere Caption-Analyse aus Layout und PDF-Text.
