-- Merkt sich mehrfach bestätigte fehlende Nextcloud-PDFs.
-- Es werden keine Dokumente oder Embeddings gelöscht.

CREATE TABLE IF NOT EXISTS knowledge.pdf_missing_state (
    document_id bigint PRIMARY KEY
        REFERENCES knowledge.document(id) ON DELETE CASCADE,

    first_missing_at timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz NOT NULL DEFAULT now(),

    CHECK (last_checked_at >= first_missing_at)
);

COMMENT ON TABLE knowledge.pdf_missing_state IS
    'Status fehlender PDFs für die zweistufige WebDAV-Prüfung';

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE knowledge.pdf_missing_state
TO retro_rag_ingest;

GRANT SELECT
ON TABLE knowledge.pdf_missing_state
TO retro_rag_reader;