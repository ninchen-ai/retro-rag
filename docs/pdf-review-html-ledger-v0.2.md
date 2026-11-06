# PDF-Review HTML v0.2 – Ledger-Anzeige (read-only)

Die lokale HTML-Vorschau liest optional die **separaten Review-Entscheidungen**
und zeigt den aktuell wirksamen Status für logische Elemente,
Regionen und Beziehungen an. Die ursprünglichen Extraktionen,
v0.2-Strukturdateien und JSON-Entscheidungsdateien bleiben unverändert.

Der gesamte Ledger wird vor der Darstellung mit
`inspect_ledger()` geprüft. Bei inkonsistenten Einträgen,
verändertem Ziel-Fingerprint, abweichender Dokumentversion oder
ungültiger Entscheidungskette **bricht die HTML-Erzeugung ab**.
Es gibt keine automatische Bestätigung, keinen Webserver
und keine Netzwerk-/Datenbankschreiboperationen.

## Test

```bash
cd ~/projects/retro-rag
git pull --ff-only
python -m unittest discover -s tests -p 'test_pdf_review_html_v02.py' -v
```

## Figure 3: echte bestätigte Entscheidung anzeigen

Die bereits bestätigte Entscheidung
`474d5d41-8acd-488d-a674-02aaf8700569`
liegt in `/tmp/875p-review-decisions/`. Auf **Poseidon**:

```bash
python -m experiments.pdf_review_html_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --page 35 \
  --image /tmp/875p-page35.png \
  --ledger-dir /tmp/875p-review-decisions \
  --out /tmp/875p-page35-review-with-decisions.html
```

Auf **Iris**, außerhalb der SSH-Terminalsitzung:

```bash
scp nina@poseidon.heinz.home:/tmp/875p-page35-review-with-decisions.html /tmp/
firefox-esr file:///tmp/875p-page35-review-with-decisions.html
```

Das logische Element Figure 3 zeigt dann den effektiven
Ledger-Status `confirmed`, Reviewer, Entscheidungszeitpunkt
und Begründung. Die darunterliegende extrahierte Region und
ihre Beziehungen bleiben weiterhin `proposed`, solange keine
**eigenen** Entscheidungen für diese IDs vorliegen.

### Auch Seite 43 mit demselben Ledger anzeigen

```bash
python -m experiments.pdf_review_html_v02 \
  --v02-json /tmp/875p-multipage-structure-v0.2.json \
  --page 43 \
  --image /tmp/875p-page43.png \
  --ledger-dir /tmp/875p-review-decisions \
  --out /tmp/875p-page43-review-with-decisions.html
```

Da die Entscheidung für Figure 3 auf **Seite 35** gilt,
wird auf Seite 43 **kein bestätigter Status erfunden**.

## Datensicherung

`/tmp` ist nur für Tests geeignet: Ein Neustart oder
systematische Bereinigung kann die Dateien löschen. Wir
müssen vor einer dauerhaften Migration zunächst das aktuelle
Borg-Backup-Skript und dessen Include-/Exclude-Regeln prüfen.
**Es wurden keine Sicherungspfade oder Timer verändert.**

Bis die endgültige Zielstruktur geklärt ist, die erste
Review-Entscheidung nicht aus `/tmp` löschen.

Zur Bestandsaufnahme auf Poseidon (nur lesen):

```bash
sudo systemctl cat borg-backup.service
sudo systemctl cat borg-backup.timer
sudo grep -R -nE 'borg create|borgmatic|exclude|include|BACKUP|SOURCE' \
  /usr/local/sbin /usr/local/bin /etc/borg 2>/dev/null
```

Bei anderen Speicherorten des Backup-Skripts
den Dienstpfad aus `systemctl cat` verwenden.
Den tatsächlichen Sicherungsumfang zusätzlich mit
`borg list` bzw. `borg extract --dry-run` prüfen;
eine Konfigurationsangabe allein belegt noch keine
erfolgreiche Wiederherstellung.

## Grenzen

Die HTML-Datei ist eine **statische Momentaufnahme**:
Nach jeder neuen Review-Entscheidung muss die HTML-Datei erneut
generiert werden. Die Ledger-Daten werden nur eingebettet
und ausschließlich angezeigt, nicht aus dem Browser heraus geändert.
Eine umfassende History-Ansicht (alle alten Revisionen pro
Element) ist ein separater Ausbauschritt; zurzeit erscheint
nur die wirksame letzte Entscheidung pro Ziel.
