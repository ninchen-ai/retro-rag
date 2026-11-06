# PDF-Caption-Adapter v0.1 – read-only Experiment

**Motivation:** Intel-875P besitzt keine Tabellen-Lesezeichen,
aber sichtbare Beschriftungen wie `Figure 6. Configuration Mechanism ...`
und `Table 5. Configuration Address Decoding`.
Der Adapter liest deshalb die Textzeilen **direkt aus dem PDF**
mit PyMuPDF und gleicht Beschriftungskandidaten geometrisch mit
DocLayout-YOLO-Regionen derselben Seite ab.

Das gemeinsame Schema v0.1, das Outline-JSON und die originalen
PDF-Seitentexte bleiben unverändert. Es wird ausschließlich
ein **separater, nicht freigegebener Review-Bericht** unter `/tmp`
geschrieben. Kein Datenbankzugriff, keine Embeddings, keine Inferenz.

## Testbefehle

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_caption_adapter.py' -v
```

## Intel-875P: echte vorhandene Detektionen verwenden

```bash
for page in 35 43; do
  python -m experiments.pdf_caption_adapter \
    --nextcloud-path 'Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf' \
    --outline-json /tmp/875p-outline-v0.1.json \
    --layout-json "/tmp/875p-page${page}-detection/layout_report.json" \
    --image "/tmp/875p-page${page}.png" \
    --page "$page" \
    --out "/tmp/875p-page${page}-captions.json"
done
```

Zum Regressionstest mit der EHCI-Spezifikation:

```bash
python -m experiments.pdf_caption_adapter \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Schnittstellen/USB/ehci-specification-for-usb.pdf' \
  --outline-json /tmp/ehci-outline-v0.1.json \
  --layout-json /tmp/ehci-page21-detection/layout_report.json \
  --image /tmp/ehci-page21.png \
  --page 21 \
  --out /tmp/ehci-page21-captions.json
```

## Verfahren / Grenzen

- Ein nummerierter englischer Beschriftungsbeginn `Table`, `Figure`
  oder `Fig.` am **Anfang einer visuellen PDF-Textzeile** erzeugt
  einen Kandidaten mit originalem Text, Seiten-Box und Block-/Zeilen-ID.
- Der Adapter sucht ausschließlich **unterhalb** der Beschriftung
  nach Regionen derselben Klasse (maximal 40 PDF-Punkte; horizontal
  mindestens 25 % Überlappung der schmaleren Box).
- Das ist nur eine konservative Vorschau. Beschriftungen unterhalb
  einer Abbildung, umbrechende Beschriftungen, Tabellen ohne Nummer,
  andere Sprachen und abweichende Schreibweisen werden noch
  nicht vollständig unterstützt. Die Erkennung kann falsche
  Positiv- und Negativbefunde erzeugen.
- Bei mehreren Kandidaten wird `MULTIPLE_CANDIDATES` ausgegeben,
  **nicht** die geometrisch nächste Region als Wahrheit übernommen.
  So soll Table 5 auf Seite 43 mit gesamter Region und zwei Hälften
  zunächst **mehrdeutig** bleiben.
- Bei einer gemeinsamen Region für mehrere Beschriftungen wird
  `SHARED_REGION_CONFLICT` ausgegeben.
- Der Adapter verwendet den Dokument-SHA256 gegen das Outline-JSON
  und überprüft Seitengröße, Rotation und PNG-Dateinamen gegen den
  Layout-Bericht; er beweist nicht die kryptografische Identität
  des Bildinhalts mit dem Detektorlauf.
- Keine automatische Zuordnung mehrteiliger Tabellen, kein Entfernen
  vermeintlicher Figure/Table-Dubletten, keine Zellfreigabe.

Dieses Modul dient der **strukturellen Belegsammlung**, nicht der
fachlichen Entscheidung, ob eine Region tatsächlich eine Tabelle ist.
