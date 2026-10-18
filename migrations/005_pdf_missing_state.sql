-- Vormerkung fehlender Nextcloud-PDFs
CREATE TABLE IF NOT EXISTS knowledge.pdf_missing_state (
    document_id bigint PRIMARY KEY
        REFERENCES knowledge.document(id) ON DELETE CASCADE,
    first_missing_at timestamptz NOT NULL,
    last_checked_at timestamptz NOT NULL,
    CONSTRAINT pdf_missing_state_time_chk
        CHECK (last_checked_at >= first_missing_at)
);

GRANT SELECT, INSERT, UPDATE, DELETE
    ON knowledge.pdf_missing_state TO retro_rag_ingest;

GRANT SELECT
    ON knowledge.pdf_missing_state TO retro_rag_reader;
