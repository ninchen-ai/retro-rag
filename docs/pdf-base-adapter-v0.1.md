# PyMuPDF-Basisadapter v0.1 – experimentell

Der Adapter erzeugt aus lokalen PDF-Dateien oder einer via WebDAV gelesenen Nextcloud-PDF ein JSON nach `schemas/pdf_document_structure_v0.1.schema.json`. **Es werden keine Überschriften, Kapitel, Tabellenzellen oder Chunks erkannt, keine Embeddings erzeugt und keine produktiven Daten verändert.**

## Beispiel auf Poseidon

Zuerst die kleinen synthetischen Tests:

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_base_adapter.py' -v
```

Anschließend das Intel-875P-Datenblatt über die bestehende, ausschließlich lesende WebDAV-Funktion abrufen:

```bash
python -m experiments.pdf_base_adapter \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf' \
  --out /tmp/875p-pdf-structure-v0.1.json

python -m experiments.validate_pdf_structure \
  /tmp/875p-pdf-structure-v0.1.json
```

Für sehr große PDFs optional `--no-spans`; der vollständige extrahierte Seitentext bleibt trotzdem erhalten, nur der geometrische Zusatzindex fehlt. Lokale Dateien können alternativ mit `--pdf /pfad/datei.pdf` gelesen werden. Die Ausgabe wird ausschließlich an den expliziten lokalen `--out`-Pfad geschrieben.

## Qualitätsgrenzen

- `pages[].text` übernimmt `page.get_text("text")` unverändert, einschließlich Leerzeilen und aller leeren Seiten. Eine zweite Extraktion derselben Originalbytes bestätigt die Übereinstimmung.
- `text_integrity_checked: true` bestätigt **nur die Übereinstimmung beider PyMuPDF-Läufe**, nicht die Vollständigkeit von PDF-Vektorzeichnungen, Tabellenstrukturen, gescannten Bildern oder einer OCR. Die separat dokumentierte visuelle Vollständigkeitsprüfung fehlt noch.
- Der optionale Span-Index enthält **keine zerstörerische Deduplikation**. Ein geometrisch unbrauchbarer Textspan wird mit einer Warnung ausgelassen, niemals aus `pages[].text` gelöscht.
- Die `bbox_pt`-Koordinaten sind in PyMuPDFs unrotierter Textkoordinatenebene; die `rotation` steht separat pro Seite. Eine allgemein gültige Umrechnung für nachfolgende Bilddetektoren wird erst mit den Adapter-Integrationen umgesetzt.
- `elements` und `relationships` bleiben leer; `quality.review_status` ist `unreviewed`.
- Das Beispiel dient als technischer Export-/Validierungstest, **nicht** als produktiver Import.

Vor dem Aufbau universeller Kapitel- und Abbildungsadapter sollten wir den Basisadapter an Intel 875P, DirectX und USB-Dokumenten testen, insbesondere Laufzeit, Dateigröße, leere Seiten und Seitenrotationen.
