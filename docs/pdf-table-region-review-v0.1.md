# PDF-Outline × Tabellenlayout: geometrisches Review-Experiment v0.1

**Ziel:** Einen PDF-Outline-Anker für eine Tabellenüberschrift
(etwa EHCI `Table 2–3. USBLEGSUP`, PDF-Seite 21)
mit einer **separat erkannten Tabellenregion** abgleichen.

Diese beiden Bounding Boxes haben **unterschiedliche Bedeutung**:
Outline = Ort des Tabellentitels; Layout = mutmaßliche Fläche der Tabelle.
Das Schema v0.1 modelliert sie noch nicht als getrennte Feldtypen.
Dieses Experiment erzeugt deshalb ausschließlich einen **separaten
Review-Bericht**, keine Änderung an den bisherigen Struktur-JSONs.

## Voraussetzungen

- Bereits erzeugtes `/tmp/ehci-outline-v0.1.json` aus dem Outline-Adapter.
- Ein **unannotiertes** gerendertes PNG von PDF-Seite 21.
- DocLayout-YOLO-Detektionen für **genau dieses PNG** als JSON,
  im Format `{"source_image":"ehci-page21.png","detections":[{"class_name":"table","bbox_pixels":[x0,y0,x1,y1],"confidence":0.8}]}`.
  Die Zahlen hier sind nur Formatplatzhalter, **keine Messung**.
  Nicht mit leeren oder erfundenen Detektionen als echten Test verwechseln.

Für den ersten Test darf das Layout-JSON auch weitere
Detektionsklassen enthalten; genutzt wird zunächst ausschließlich
`class_name = "table"`. Gerenderte Seite und Detektorinput müssen
identisch sein. Die Quelle der Detektionsboxen ist der bestehende
DocLayout-YOLO-Testworkflow. Dieses Modul **führt keine eigene
KI-Inferenz aus**.

## Unit-Tests

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_table_region_review.py' -v
```

## Layout-Abgleich

Sobald Bild und tatsächlich gemessene Detektionen bereitstehen:

```bash
python -m experiments.pdf_table_region_review \
  --outline-json /tmp/ehci-outline-v0.1.json \
  --image /tmp/ehci-page21.png \
  --layout-json /tmp/ehci-page21-layout.json \
  --page 21 \
  --out /tmp/ehci-page21-table-review.json
```

## Entscheidungskriterien

Ein Tabellenkandidat muss **unter** der Titel-Box liegen,
höchstens 35 PDF-Punkte entfernt und horizontal zu mindestens
30 % der schmaleren Box überlappen.

Die Ausgabe unterscheidet:
- `ONE_CANDIDATE`: genau eine geometrisch passende Region (weiter Review).
- `NO_CANDIDATE`: keine geometrisch plausible Region.
- `MULTIPLE_CANDIDATES`: mehrere mögliche Regionen.
- `SHARED_REGION_CONFLICT`: dieselbe Region wird von mehr als einem Titel beansprucht.

Keine automatische Annahme bei Mehrdeutigkeiten. Die Region wird
**nicht** mit dem Outline-Textanker überschrieben; sie wird in einem
eigenen Feld des Review-Berichts protokolliert.
Regionen ohne einen passenden Outline-Anker werden weiterhin im
Bericht geführt, aber nicht semantisch zugeordnet.

## Grenzen / offene Architekturfragen

- Eine geometrische Zuordnung ist **keine** Tabellenextraktion.
  Registerbits, Zellen, verbundene Zellen und Spalten fehlen weiterhin.
- Mehrseitige Tabellen und Beschriftungen **unterhalb** der Tabelle
  werden in v0.1 nicht automatisch zugeordnet.
- Der erste Adapter unterstützt nur unrotierte Seiten und überprüft
  Bild/Detektionsdatei auf den Dateinamen; den tatsächlichen
  Pixelinhalt oder einen externen Detektorlauf kann er nicht
  kryptografisch verifizieren.
- `confidence` wird nur als Rohwert übernommen, nicht als
  kalibrierte Qualität oder Freigabe interpretiert.
- Original-PDF, Nextcloud, PostgreSQL, Source-Text und
  Outline-JSON bleiben unverändert.
