# PDF-Outline-Adapter v0.1 – Experiment

Liest die PDF-Lesezeichen mit PyMuPDF und ergänzt das gemeinsame
`pdf_document_structure_v0.1`-JSON um **ungeprüfte Strukturvorschläge**.
Die Originaltexte und `source_spans` bleiben unverändert. Keine
Kapitel-Chunks, Datenbankzugriffe, Embeddings oder Nextcloud-Schreiboperationen.

## Typklassifikation

- `heading`: nicht als andere Art erkannter Bookmark-Eintrag, **nur ein Kandidat**.
- `figure`: `Figure 1-1 ...` / `Fig. ...` – Abbildungs**referenz**.
- `table`: `Table 2-1 ...` – Tabellen**referenz**.
- `navigation`: `Contents`, `Revision History`, `Start` usw.

**Wichtig:** Bei `figure` und `table` ist `bbox_pt` ausdrücklich
ein Anker auf dem Beschriftungstext (oder ein 1-pt-Platzhalter),
**keine erkannte Abbildungs- bzw. Tabellenregion**.
Das Schema v0.1 trennt Anker und vollständige Region noch nicht
sauber. Bei einem späteren Schema-Update sind diese Konzepte
ausdrücklich zu differenzieren. Es werden keine Tabelleninhalte oder
Bilder dadurch automatisch erfasst.

## Positionierung und Review

Mehrere `search_for()`-Rechtecke können zusammen nur **eine**
Überschrift bilden. Der Adapter gruppiert Rechtecke in ungefähr
derselben Zeile. Verschiedene Y-Zeilen gelten als Mehrdeutigkeit.
Die PDF-Sprungzielkoordinate wird als Hint geprüft – sowohl roh
als auch gegen die Seitenhöhe gespiegelt, weil die beobachteten
PDF-Konventionen nicht einheitlich sind. **Keine dieser Varianten
wird pauschal als korrekt angenommen.**

- `review.status = proposed`: passender Textanker nahe dem Sprungziel.
- `review.status = unclear`: Text fehlt, Zielpunkt fehlt/ist
  unplausibel, mehrere Textzeilen passen oder große Abweichung.
- Alle Anker sind Vorschläge; es wird nichts automatisch freigegeben.
- Bei fehlendem Textanker bleibt das Lesezeichen als unsicherer
  1-pt-Marker erhalten. Die entsprechende Herkunft nennt explizit
  den Grund, sodass dies nicht als vorhandene Überschrift gilt.
- Die Bookmark-Hierarchie wird nur über mögliche `heading`-Eltern
  abgebildet; Figuren und Tabellen werden keine Kapitel.
- Ungültige Zielseiten oder leere Bookmark-Titel werden
  mit Warnung gezählt und nicht als geometrisch verortete
  Elemente ausgegeben.

## Testbefehle auf Poseidon

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_outline_adapter.py' -v
```

Intel 875P: bestehendes Basis-JSON verwenden (erneuter Download nur für
Lesezeichen, SHA-256 verhindert die Kombination verschiedener Versionen):

```bash
python -m experiments.pdf_outline_adapter \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Chipsets/875p-chipset-datasheet.pdf' \
  --base-json /tmp/875p-pdf-structure-v0.1.json \
  --out /tmp/875p-outline-v0.1.json

python -m experiments.validate_pdf_structure /tmp/875p-outline-v0.1.json
```

EHCI kann direkt ein Basis-JSON plus Outline-Vorschläge erhalten:

```bash
python -m experiments.pdf_outline_adapter \
  --nextcloud-path 'Retro-Computing/Referenzwissen/Schnittstellen/USB/ehci-specification-for-usb.pdf' \
  --out /tmp/ehci-outline-v0.1.json
```

Die EHCI-Datei ist ein neuer, unabhängiger Test für Figur-Lesezeichen.
USB 1.0 ohne PDF-Lesezeichen sollte 0 Vorschläge liefern und
den vollständigen Basistextexport bewahren.

## Grenzen

- Der Adapter identifiziert weder die richtigen Kapitelgrenzen
  noch die logische Zugehörigkeit aller Figur-/Tabellenverweise.
- Die Klassifikation ist bewusst eine Heuristik. Besonders
  Einträge ohne Nummerierung oder in anderen Sprachen können
  falsch typisiert werden.
- Die Seiten- und Textintegrität des Basisadapters bleibt erhalten,
  doch die Struktur und die korrekte semantische Funktion jeder
  Fundstelle erfordern weiteres Review und Regressionstests.

## EHCI-Kodierungsfall (11/2026)

Die tatsächliche PyMuPDF-Extraktion der EHCI-Seiten 18 und 21 lieferte
`U+F8E7` für den im Druck sichtbaren langen Strich, während die
PDF-Lesezeichen `U+F0BE` verwenden. Die Suchfunktion probiert deshalb
zuerst den **unveränderten** Bookmark-Titel und danach eine explizite
private-use-Zeichenersetzung (`U+F0BE` ↔ `U+F8E7`).
Nur der **Suchstring** wird geändert; `pages[].text`, `source_spans`
und `title_or_text` bleiben unverändert. Die Provenienz vermerkt
`search_variant=private_use_dash`, sofern der Ersatz verwendet wurde.
Es gibt ausdrücklich **keine allgemeine Entfernung aller Sonderzeichen**.

Die Klassifikation erkennt jetzt auch typografische Trennzeichen in
Nummern wie `Table 2–3.` (`U+2013`), damit sie nicht als Heading
eingestuft werden.

Dieser Fix ist derzeit eine überprüfbare Hypothese mit Unit-Tests.
Der reale EHCI-Durchlauf muss zeigen, welche der 32
`TEXT_NOT_LOCATED`-Warnungen verschwinden. Die unklaren Listenpunkte
auf Seite 92 und das isolierte Ellipsenzeichen auf Seite 79 können
separate Probleme sein.
