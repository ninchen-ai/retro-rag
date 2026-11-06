# PDF v0.2 – Interaktiver Review über lokalen SSH-Tunnel

**Experimentell:** Der Reviewserver bietet eine interaktive Oberfläche,
die den vorhandenen statischen PDF-HTML-Viewer erweitert. Er läuft
**ausschließlich auf `127.0.0.1` auf Poseidon**. Iris verbindet sich
über einen SSH-Lokaltunnel. Apache und Tomcat werden nicht benötigt.

## 1. Tests (Poseidon)

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_review_server_v02.py' -v
python -m unittest discover -s tests -p 'test_pdf*.py' -v
```

Bei Fehlern nicht mit echten Entscheidungen fortfahren.

## 2. Reviewserver auf Poseidon starten

Im **ersten Terminal auf Poseidon**:

```bash
cd ~/projects/retro-rag
source .venv/bin/activate
python -m experiments.pdf_review_server_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --page 43 \
  --image /tmp/875p-page43.png \
  --ledger-dir /data/projects-data/retro-rag/reviews/875p \
  --port 8765
```

Dieser Prozess muss während der Browsernutzung laufen. Der Server
verlangt, dass der Ledger-Ordner bereits existiert; er ändert
weder die PDF-Strukturdatei noch das PDF.

## 3. SSH-Tunnel auf Iris öffnen

**Im lokalen Terminal auf Iris (nicht in der SSH-Shell auf Poseidon):**

```bash
ssh -N -L 8765:127.0.0.1:8765 nina@poseidon.heinz.home
```

Das Terminal bleibt durch den Tunnel belegt. Ein **zweites lokales
Terminal auf Iris** öffnet den grafischen Browser:

```bash
firefox-esr http://127.0.0.1:8765/
```

Der Reviewserver ist damit **nicht im Heimnetz oder Internet offen**.
Bei VPN-Zugriff funktioniert die SSH-Verbindung ebenfalls, sofern
SSH zu Poseidon erlaubt ist. **Keine Portfreigabe in OPNsense anlegen.**

## 4. Explizite Prüfung / Speicherung

1. Region im PDF anklicken oder bei logischen Elementen und
   Beziehungen **„Dieses Element prüfen“ / „Diese Beziehung prüfen“**
   verwenden. Alle Objekte können auch über das Dropdown
   `Review-Objekt` gewählt werden.
2. `confirmed` oder `rejected` wählen; Reviewer und **konkrete
   Begründung** eingeben.
3. Auf **„Entscheidung vorbereiten (ohne Speicherung)“** klicken.
   Der Server validiert die PDF-Version, das Ziel und den aktuellen
   Review-Status. **Bis hierhin keine Speicherung.**
4. Vorschlag, Review-ID und Status prüfen. Danach
   **„Jetzt verbindlich speichern“** wählen und die zusätzliche
   Bestätigungsabfrage akzeptieren.
5. Erst jetzt schreibt der Server mithilfe des bestehenden
   `apply()`-Adapters eine neue JSON-Datei nach
   `/data/projects-data/retro-rag/reviews/875p/`.
   Anschließend wird die Seite aktualisiert.

**Zuerst mit einem noch nicht entschiedenen Objekt testen.**
Figure 3 auf Seite 35 ist bereits bestätigt; eine erneute
Bestätigung ohne Zustandsänderung wird abgelehnt.

### Sicherheitsgarantien und Einschränkungen

- Der Server bindet ausschließlich an IPv4-Loopback
  `127.0.0.1`; Zugriffe mit unbekanntem `Host` oder
  fremdem `Origin` werden abgelehnt.
- Browseranfragen brauchen zusätzlich einen zufälligen
  Sitzungstoken. Preview-Tokens gelten maximal zehn Minuten
  und können nur einmal verwendet werden.
- Veränderungen am Formular **verwerfen** bereits vorbereitete
  Entscheidungen. Auf dem Server werden genau die geprüften
  Formularfelder vor dem Speichern erneut verglichen.
- Geänderte Quelldokument-/Ziel-Fingerprints und veraltete
  Ledgerstände werden vor dem Commit zurückgewiesen.
- Die JSON-Dateien bleiben unabhängig; bestehende Entscheidungen
  werden nicht überschrieben. Frühere Entscheidungen müssen
  bei einer Neubewertung explizit als Vorgänger angegeben sein.
- Die ursprünglichen `review.status = proposed` Einträge bleiben
  in den Extraktionsdaten unverändert. Ein Review betrifft immer
  **nur das einzelne gewählte Objekt**.
- Das Browserfenster selbst kann keine Dateien direkt auf Iris
  oder Poseidon speichern. Der lokale Python-Prozess führt den
  eigentlichen Commit nach expliziter Benutzeraktion aus.
- Das ist ein **privates Homelab-Werkzeug**, kein gehärteter
  öffentlich erreichbarer Multiuser-Dienst. Nicht über
  `0.0.0.0`, Reverse Proxy oder Cloudflare veröffentlichen.
- Der bereits bestätigte Ledger auf BORG-W1 wurde mit
  einem bytegleichen Restore erfolgreich getestet. Neue
  Entscheidungen sind **erst nach dem nächsten Borg-Lauf**
  Bestandteil eines Backup-Archivs.

Stoppen: Auf Poseidon im Serverterminal `Ctrl+C`, auf Iris im
Tunnelterminal ebenfalls `Ctrl+C`.

Die bestehende Offline-Vorschau mit `pdf_review_html_v02.py`
funktioniert weiterhin **rein lesend** und braucht keinen Server.
