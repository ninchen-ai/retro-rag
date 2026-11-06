# PDF-Review-Vorschau v0.2 – lokale HTML-Ansicht

**Status:** Experimentell; **rein lesend** und nur für menschlichen Review.
Der Generator verwendet eine bereits existierende **v0.2-JSON-Datei**
und ein **unannotiertes PNG der konkreten PDF-Seite**. Er schreibt
nur eine neue HTML-Datei, niemals PDF, JSON-Eingabe, Nextcloud oder
PostgreSQL.

## Funktionen

- Vollständiges PNG der Seite mit farbigen PDF-Punkt-Koordinaten-
  Overlays (Tabellen, Abbildungen, Beschriftungen, andere Regionen).
- Regionen ein-/ausblenden und anklicken; zugehörige
  Erkennungsprovenienz und Beziehungen anzeigen.
- Unveränderte PyMuPDF-Zellmatrizen, `null`-Werte,
  Original-Zeilenumbrüche und separate Tabellenblöcke anzeigen.
- Logische Elemente, Beziehungsarten, Konflikt-Hinweise und
  bereits gespeicherte Review-Entscheidungen anzeigen.
- Die Darstellung enthält eine eingebettete PNG-Datei und ein
  eingebettetes, HTML-sicheres JSON. Es werden keine externen
  Ressourcen geladen. HTML/CSS/JS sind in einer einzelnen Datei
  enthalten, damit sie mit `file://` funktioniert.
- Klicks setzen **nur die Auswahl im Browser**, sie speichern
  keine Entscheidungen.

**Sicherheit:** Das generierte HTML enthält das lokale Seitenbild
und die ausgewählten PDF-Inhalte als eingebettete Daten. Es sollte
nicht öffentlich bereitgestellt oder an Unbefugte weitergegeben
werden. Die Content-Security-Policy verbietet externe Verbindungen.
Die Seite ermöglicht keine Review-Freigabe.

## Test

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_review_html_v02.py' -v
```

## Intel 875P – Seite 43

Der dokumentweite v0.2-Merge liegt bereits unter
`/tmp/875p-multipage-structure-v0.2.json`. Die Seite 43 wird
separat ausgewählt:

```bash
python -m experiments.pdf_review_html_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --page 43 \
  --image /tmp/875p-page43.png \
  --out /tmp/875p-page43-review.html
```

Auf **Poseidon** lokal öffnen:

```bash
xdg-open /tmp/875p-page43-review.html
```

Wenn du über **Iris** auf Poseidon arbeitest, kannst du die
fertige HTML-Datei mit `scp` nach Iris kopieren und dort
in Firefox öffnen:

```bash
scp poseidon.heinz.home:/tmp/875p-page43-review.html /tmp/
xdg-open /tmp/875p-page43-review.html
```

## EHCI – Seite 21

```bash
python -m experiments.pdf_review_html_v02 \
  --v02-json /tmp/ehci-page21-structure-v0.2.json \
  --page 21 \
  --image /tmp/ehci-page21.png \
  --out /tmp/ehci-page21-review.html

scp poseidon.heinz.home:/tmp/ehci-page21-review.html /tmp/
xdg-open /tmp/ehci-page21-review.html
```

Die beiden PDFs bleiben getrennte Datensätze.

## Technische Prüfungen und Grenzen

1. Eingabe-JSON muss vollständig dem v0.2-Schema und
   Cross-Reference-Validator entsprechen.
2. PDF-Seite muss existieren und unrotiert sein.
3. Genau ein DocLayout-Verarbeitungslauf für diese Seite muss
   vorhanden sein; aufgezeichneter PNG-Dateiname und PNG-Abmessungen
   müssen zum tatsächlichen Eingabebild passen.
4. Die Positionen werden prozentual aus der PDF-Seitengeometrie
   abgeleitet, unabhängig von der Bildschirmauflösung.
5. **Ungeprüft:** Ein PNG gleicher Größe und gleichen Namens könnte
   falsche Pixel enthalten. Es existiert derzeit kein persistierter
   PNG-SHA256-Beleg im Layoutbericht; visueller Vergleich mit dem
   Original-PDF bleibt erforderlich.
6. Bei überlappenden Detektorrahmen können kleinere Regionen schwer
   anklickbar sein; die Klassenfilter helfen bei der Sichtprüfung.
7. Die Ansicht enthält keine PDF-Neurenderung, keine OCR,
   automatische Klassifizierung, Tabellenrekonstruktion oder
   neue Datenbank-Schnittstelle.
8. Es gibt noch keinen Schreibworkflow für Entscheidungen.
   `confirmed` und `rejected` dürfen nur über einen späteren
   expliziten, auditierbaren Review-Prozess eingetragen werden.

Die JavaScript-Auswahl ist rein lokal; auch beim Öffnen im Browser
werden keinerlei Änderungen in den v0.2-Dateien vorgenommen.
