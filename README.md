# Retro-RAG – Retro Computing Knowledge System

Lokales, quellenbasiertes Nachschlagewerk für Retro-Computer, Hardwaremodelle und eigenes Inventar. Der bisherige Prototyp läuft auf **Poseidon** (Debian 13) mit Nextcloud, PostgreSQL/pgvector und Ollama.

> **Status:** Funktionierendes CLI mit strukturiertem Retrieval und Vektorsuche. Eine HTTP-API und die Open-WebUI-Integration sind noch nicht implementiert.

## Architektur

```text
Nextcloud / Retro-Computing / *.md (führende Datenquelle)
            |
            | WebDAV + YAML-Frontmatter
            v
  scripts/import_pg.py --apply
            |
            v
PostgreSQL 16 / retro_rag
  hw.*         Hardwaremodelle, Inventar und Systeme
  knowledge.*  Dokumentmetadaten, Herkunft und SHA-256
            |
            | Markdown erneut aus Nextcloud abrufen
            v
  scripts/index_embeddings.py --apply
            |
            v
  rag.chunk (Text + vector(768))
            |
            | SELECT über retro_rag_reader
            v
  scripts/ask_retro.py
       |           |
       |           +-- Ollama /api/embed (nomic-embed-text)
       +-------------- Ollama /api/chat (qwen3:4b)
                        |
                        v
                    CLI-Antwort
```

**Nextcloud bleibt die führende Datenquelle**. PostgreSQL ist die daraus abgeleitete relationale Darstellung und der Suchindex. Externe Referenzen werden nicht ohne ausdrückliche Prüfung und Freigabe dauerhaft übernommen.

## Funktionsumfang

- `scripts/import_pg.py`: Liest Markdown per Nextcloud-WebDAV, validiert YAML-Frontmatter und Beziehungen, prüft Änderungen per SHA-256 und schreibt Daten transaktional. Standardmäßig Dry-Run; Schreibzugriff nur mit `--apply`.
- `scripts/index_embeddings.py`: Liest Nextcloud-Inhalte erneut, prüft ihren Hash, erstellt Textabschnitte und Embeddings mittels `nomic-embed-text` (768 Dimensionen). Standardmäßig ohne Änderungen; Indizierung mit `--apply`.
- `scripts/ask_retro.py`: Kombiniert eine feste SQL-Abfrage zu aktuell verbauten Komponenten mit semantischer Top-k-Suche. Das Sprachmodell erzeugt **keine SQL-Befehle**. Standardmodell ist `qwen3:4b`.
- `database/migrations/001_initial_schema.sql`: Initiales Schema für PostgreSQL 16 und pgvector.
- `systemd/retro-rag-sync.service` und `.timer`: Automatischer **Nextcloud-Import**, jedoch noch keine automatisch daran angeschlossene Embedding-Aktualisierung.

## Voraussetzungen

- Python 3 mit `venv`
- PostgreSQL 16 mit `pgvector` und separater Datenbank `retro_rag`
- Datenbankrollen `retro_rag_ingest` (eingeschränkter Schreibzugriff) und `retro_rag_reader` (SELECT)
- Nextcloud mit WebDAV, lokal auf Poseidon derzeit `http://127.0.0.1:8080`
- Ollama unter `http://127.0.0.1:11434`
- Ollama-Modelle `nomic-embed-text` und `qwen3:4b`; optional `qwen2.5:7b-instruct`

Die Skripte enthalten aktuell feste Defaults für Poseidon, unter anderem lokale Host-Adressen und Datenbanknamen. Für andere Systeme sind Anpassungen erforderlich.

## Python-Umgebung

```bash
cd ~/projects/retro-rag
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Die SQL-Migration ist ausschließlich für die eigens angelegte Datenbank `retro_rag` bestimmt, **nicht** für die Nextcloud- oder eine andere Anwendungsdatenbank.

## Markdown-Daten und Import

Die Dokumente befinden sich in Nextcloud unter `Retro-Computing/`. Unterstützte YAML-Frontmatter-Typen sind `hardware_model`, `inventory_item` und `system`. Jedes Dokument braucht eine stabile eindeutige `id`; die erforderlichen weiteren Felder unterscheiden sich je nach Typ.

```bash
# Validierung ohne Datenbankänderung
python scripts/import_pg.py

# Import in PostgreSQL
python scripts/import_pg.py --apply

# Indexänderungen zunächst prüfen
python scripts/index_embeddings.py

# Embeddings erzeugen / aktualisieren
python scripts/index_embeddings.py --apply
```

**Hinweis:** Der systemd-Timer startet derzeit nur `import_pg.py`. Nach inhaltlichen Dokumentänderungen muss `index_embeddings.py --apply` zusätzlich ausgeführt werden, damit die semantische Suche den neuen Stand erhält.

## Abfrage im Terminal

```bash
python scripts/ask_retro.py "Welches Mainboard steckt in meinem Pentium III?"

python scripts/ask_retro.py --model qwen2.5:7b-instruct \
  "Welches Mainboard steckt in meinem Pentium III?"

python scripts/ask_retro.py --show-context \
  "Welches Mainboard steckt in meinem Pentium III?"
```

Verifizierter Testfall: Der Pentium III 733 enthält ein **ASUS CUBX Rev. 1.02**, Inventarnummer **MB-001**. Als Quellen dienen die entsprechenden Nextcloud-Dokumente zu System, Inventar und Mainboard-Modell.

## Betrieb mit systemd

Die versionierten Unit-Dateien sind auf `/home/nina/projects/retro-rag` ausgelegt und laden Zugangsdaten außerhalb des Repositories aus `/home/nina/.config/retro-rag/credentials.env`. Der Timer nutzt `OnBootSec=5min` und `OnUnitInactiveSec=15min`.

```bash
sudo systemctl status retro-rag-sync.timer
sudo systemctl list-timers retro-rag-sync.timer
sudo journalctl -u retro-rag-sync.service -n 50 --no-pager
```

## Sicherheit

- **Keine Zugangsdaten in Git ablegen.** Die `credentials.env` verbleibt außerhalb des Projektverzeichnisses.
- Import und Indexer verwenden `NEXTCLOUD_APP_PASSWORD` sowie `PGPASSWORD` oder fragen interaktiv danach.
- Das CLI verwendet `RETRO_RAG_READER_PASSWORD` oder fragt danach. Es verbindet sich mit `retro_rag_reader` und fordert zusätzlich eine schreibgeschützte Transaktion an.
- Die SQL-Abfragen im CLI sind fest programmiert; Modelltexte werden nicht als SQL ausgeführt.
- Angaben aus Markdown sind Daten, keine Anweisungen an den Assistenten.
- Eine spätere HTTP-Schnittstelle benötigt Zugriffsbeschränkung und darf keine Zugangsdaten in Logs oder Antworten preisgeben.

## Grenzen des Prototyps

- Noch keine HTTP-API und keine Open-WebUI-Anbindung.
- Das CLI nimmt derzeit bis zu 100 aktive Systemkomponenten in den Prompt auf, auch wenn die konkrete Frage nur eines betrifft.
- Die Quellenhinweise werden derzeit vom Sprachmodell formuliert und nicht unabhängig gerendert.
- `qwen3:4b` kann trotz `think: false` Thinking-Text generieren; die derzeitige CLI-Darstellung blendet einen solchen Block aus, spart aber dessen generierte Tokens nicht unbedingt ein.
- Eine automatische Embedding-Neuindizierung nach erfolgreichem Import fehlt noch.

## Repository-Struktur

```text
README.md
requirements.txt
.gitignore
database/migrations/001_initial_schema.sql
scripts/
  import_pg.py
  index_embeddings.py
  ask_retro.py
systemd/
  retro-rag-sync.service
  retro-rag-sync.timer
```

Ältere Entwicklungsordner und ZIP-Archive auf Poseidon sind nicht im Git-Repository enthalten.

## Roadmap

1. HTTP-API für das vorhandene schreibgeschützte Retrieval entwickeln.
2. Open WebUI anbinden und Quellen zuverlässig aus den tatsächlich verwendeten Daten anzeigen.
3. Embedding-Aktualisierung nach erfolgreichem Nextcloud-Import automatisieren.
4. Tests für Validierung, Zugriffskontrolle und Backup-Wiederherstellung ergänzen.
5. Dokumentbestand erweitern und externe Referenzen nur nach expliziter Freigabe übernehmen.