# Tabellen-Qualitätsprüfung v0.1 (Review-only)

Verknüpft drei **unabhängige Vorschläge**, ohne Quelle oder
Produktivdaten zu ändern:

1. **Outline:** Tabellen-Beschriftung und ihr Textanker;
2. **DocLayout-YOLO:** vermutete Tabellenregion (Pixel → PDF-Punkte);
3. **PyMuPDF:** Tabellen-Bounding-Box, Zeilen, Spalten und vollständige Zellmatrix.

Die Zuordnung von Beschriftung zur Layoutregion verwendet weiterhin
das getrennt getestete Modul `pdf_table_region_review`. Zusätzlich
wird eine mögliche Zuordnung der Layoutregion zur PyMuPDF-Tabelle
mittels **Intersection over Union** (IoU, Schwelle v0.1: 0,75)
ermittelt. Mehrdeutige Treffer und mehrfach beanspruchte Regionen
bleiben ausdrücklich ungelöst. Es gibt keine automatische Freigabe.

## EHCI-Praxistest

Voraussetzung: vorhandene, bereits getestete Dateien
`/tmp/ehci-outline-v0.1.json`,
`/tmp/ehci-page21.png`,
`/tmp/ehci-page21-detection/layout_report.json`.

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_table_quality_review.py' -v

python -m experiments.pdf_table_quality_review \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Schnittstellen/USB/ehci-specification-for-usb.pdf' \
  --outline-json /tmp/ehci-outline-v0.1.json \
  --layout-json /tmp/ehci-page21-detection/layout_report.json \
  --image /tmp/ehci-page21.png \
  --page 21 \
  --out /tmp/ehci-page21-quality-review.json
```

Das Skript liest das PDF **nur** von WebDAV, prüft die SHA-256 gegen
das Outline-JSON und analysiert Seite 21. Der einzige Schreibvorgang
ist die neue Review-JSON in `/tmp`; Eingaben bleiben unverändert.

## Qualitätskriterien

- IoU und geometrischer Zuordnungsstatus je erkannter Tabellenregion.
- Zeilen-/Spaltenzahl, vollständige PyMuPDF-Zellmatrix (einschließlich
  Zeilenumbrüchen und `None`), keine textuelle Normalisierung.
- Warnungen für fehlende Zeilen, inkonsistente Spaltenanzahl und
  leere Zellen. Leere Zellen können korrekt sein und sind nur Hinweise.
- Eindeutig verknüpfter Outline-Anker nur bei eindeutigem
  Caption→Detektor→PyMuPDF-Pfad.
- Alle Resultate mit `approved: false`.

**Grenzen:** IoU sagt nichts über Richtigkeit der Zellinhalte aus.
PyMuPDF und Detektor könnten denselben Fehler machen. Auch
nichtleere Zellen können gekürzt, falsch zugeordnet oder semantisch
falsch gelesen sein. Für eine fachliche Bestätigung sind Sichtprüfung
und weitere Dokumente erforderlich. Der Bericht bestätigt weder
OCR-Vollständigkeit noch Multi-Page-Tabellen oder verbundene Zellen.
Die Bindung von Bild und Detektorbericht wird über den Dateinamen
geprüft; die Pixelidentität wird nicht kryptografisch nachgewiesen.
Rotierte Seiten sind noch nicht unterstützt.

**Keine** Änderung an Nextcloud-Original, gemeinsamen
Schema-v0.1-Elementen, PostgreSQL, Chunks oder Embeddings.
