BEGIN;

CREATE TABLE knowledge.pdf_sync_state (
    document_id bigint PRIMARY KEY
        REFERENCES knowledge.document(id) ON DELETE CASCADE,

    etag text NOT NULL,
    file_size bigint NOT NULL,
    last_modified timestamptz,
    synced_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pdf_sync_etag_nonempty_chk
        CHECK (length(btrim(etag)) > 0),

    CONSTRAINT pdf_sync_file_size_chk
        CHECK (file_size > 0)
);

GRANT SELECT, INSERT, UPDATE, DELETE
    ON knowledge.pdf_sync_state TO retro_rag_ingest;

GRANT SELECT
    ON knowledge.pdf_sync_state TO retro_rag_reader;

COMMIT;
