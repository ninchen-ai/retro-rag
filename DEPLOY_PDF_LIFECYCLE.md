# Retro-RAG PDF-Lebenszyklus — Installation auf Poseidon

Enthält ausschließlich:
- `scripts/sync_pdfs.py`: Zwei vollständige Nextcloud-Scans, zweistufige Deaktivierung (>10 Minuten zwischen getrennten Sync-Läufen), geprüfte Reaktivierung mit Datenbank-Lock, Verarbeitung von Fehlerfällen.
- `scripts/import_pdf.py`: Erneuter Import bei lückenhaftem Chunk-Index statt fälschlichem `SKIP`.
- `tests/test_pdf_lifecycle.py`, `tests/test_pdf_import_structure.py`, `tests/test_pdf_sync_flow.py`.

Alle Beispielbefehle sind auf Poseidon auszuführen. Keine `.env`-Dateien im Archiv.

## Installation mit Backup und pausiertem Timer

```bash
cd ~/projects/retro-rag
sudo systemctl stop retro-rag-sync.timer
# Wenn gerade ein Lauf aktiv ist: dessen Ende abwarten, nicht unter laufendem Import austauschen.
systemctl is-active retro-rag-sync.service

mkdir -p "$HOME/retro-rag-pdf-backup"
tar -czf "$HOME/retro-rag-pdf-backup/pdf-before-$(date +%Y%m%d-%H%M%S).tar.gz" \
  scripts/sync_pdfs.py scripts/import_pdf.py \
  tests/test_pdf_lifecycle.py tests/test_pdf_import_structure.py

# Das heruntergeladene Archiv an seinem tatsächlichen Speicherort angeben:
tar -xzf /PFAD/ZUM/retro-rag-pdf-lifecycle-ready.tar.gz -C ~/projects/retro-rag

python -W error -m py_compile scripts/sync_pdfs.py scripts/import_pdf.py
python -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

**Nicht** mit `--apply` starten, bevor die Tests erfolgreich waren und der Dry-Run plausibel ist.

## Dry-Run

```bash
cd ~/projects/retro-rag
# Passwort-Abfrage erfolgt interaktiv, falls nicht über die Umgebung gesetzt.
.venv/bin/python scripts/sync_pdfs.py
```

Prüfen: die vorhandenen PDFs werden erkannt; die entfernte alte PDF (ID 176) wird nur als fehlend gemeldet; der Dry-Run schreibt nichts.

## Aktivierung

Wenn alle Tests erfolgreich und der Dry-Run plausibel sind:

```bash
sudo systemctl start retro-rag-sync.timer
systemctl list-timers --all | grep retro-rag-sync
```

Den **ersten produktiven Timerlauf** anschließend kontrollieren:

```bash
sudo journalctl -u retro-rag-sync.service -n 100 --no-pager
```

Erwartet: beim ersten Lauf für ID 176 `PENDING`, erst in einem späteren Lauf (mindestens 10 Minuten danach) `DEACTIVATED`, sofern beide Läufe die Abwesenheit bestätigen. ID 177 bleibt aktiv.

## Rollback

```bash
sudo systemctl stop retro-rag-sync.timer
# Vor dem Austausch sicherstellen, dass retro-rag-sync.service nicht mehr läuft.
cd ~/projects/retro-rag
tar -xzf "$HOME/retro-rag-pdf-backup/DATEINAME.tar.gz" -C .
python -m unittest discover -s tests -p 'test_*.py' -v
sudo systemctl start retro-rag-sync.timer
```

Achtung: Ein Dateirückbau macht Datenbank-Lebenszyklusänderungen nicht automatisch rückgängig. Die alten Skripte enthalten keine automatische Lebenszyklusverwaltung.

## Bekannte Grenzen

- Die automatischen SQL-Schreibzugriffe und echte Nextcloud-WebDAV-Läufe können nicht in der Entwicklungsumgebung des Assistenten gegen Poseidon getestet werden. Daher müssen Tests und Dry-Run lokal auf Poseidon laufen.
- Zwei vollständige Scans pro `--apply`-Durchlauf reduzieren das Risiko unvollständiger WebDAV-Antworten. Temporäre, wiederholt konsistente Auslassungen können nicht vollständig ausgeschlossen werden. Der Dateipfad wird deshalb zusätzlich mit Depth 0 geprüft; bei `MATCH` wird nicht deaktiviert.
- Nextcloud-Daten können sich unmittelbar nach einer WebDAV-Prüfung ändern. ETag/Größe/Datei-ID/Pfad werden vor Reaktivierung geprüft und die Datenbankversion innerhalb einer Transaktion gesperrt. Das ist kein atomarer Commit über Nextcloud und PostgreSQL.
- Diese Version verarbeitet maschinenlesbaren PDF-Text, keine OCR/Vision-Extraktion von Zeichnungen.
