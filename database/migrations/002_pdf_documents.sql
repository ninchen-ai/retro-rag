-- Retro-RAG: migration 002 - PDF manuals and page-aware retrieval
-- Apply ONLY to the retro_rag PostgreSQL database, as the schema owner/DBA.
-- Intended for PostgreSQL 16 with migration 001 already applied.
-- Do not rerun: this migration is intentionally versioned, not idempotent.
BEGIN;

-- Previously knowledge.document required Markdown for *all* document kinds.
-- Allow PDF only for manuals; retain .md for existing document types.
ALTER TABLE knowledge.document
    DROP CONSTRAINT document_markdown_chk;

ALTER TABLE knowledge.document
    ADD CONSTRAINT document_file_extension_chk
    CHECK (
        (document_kind = 'manual' AND nextcloud_path ~* '\.pdf$')
        OR
        (document_kind <> 'manual' AND nextcloud_path ~* '\.md$')
    );

-- One-to-one metadata for a PDF stored in Nextcloud. The document row holds
-- the file ID, WebDAV path, SHA-256, provenance and title.
CREATE TABLE knowledge.pdf_metadata (
    document_id bigint PRIMARY KEY
        REFERENCES knowledge.document(id) ON DELETE CASCADE,
    page_count integer NOT NULL CHECK (page_count > 0),
    pdf_version text,
    producer text,
    author text,
    extracted_at timestamptz NOT NULL DEFAULT now(),
    extraction_engine text NOT NULL DEFAULT 'PyMuPDF',
    CONSTRAINT pdf_metadata_engine_nonempty_chk
        CHECK (length(btrim(extraction_engine)) > 0)
);

-- A PDF chunk must refer to a bounded, 1-based physical PDF page range.
-- Markdown chunks retain NULL page references.
ALTER TABLE rag.chunk
    ADD COLUMN page_start integer,
    ADD COLUMN page_end integer;

ALTER TABLE rag.chunk
    ADD CONSTRAINT chunk_page_range_chk CHECK (
        (page_start IS NULL AND page_end IS NULL)
        OR
        (page_start >= 1 AND page_end >= page_start)
    );

CREATE INDEX rag_chunk_document_page_idx
    ON rag.chunk (document_id, page_start, page_end);

-- PDF-Metadaten: Importer darf schreiben, Chatbot nur lesen.
GRANT SELECT, INSERT, UPDATE, DELETE
    ON knowledge.pdf_metadata TO retro_rag_ingest;

GRANT SELECT
    ON knowledge.pdf_metadata TO retro_rag_reader;

COMMIT;
