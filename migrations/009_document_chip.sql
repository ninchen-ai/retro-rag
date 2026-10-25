BEGIN;

CREATE TABLE IF NOT EXISTS knowledge.document_chip (
    document_id BIGINT NOT NULL
        REFERENCES knowledge.document(id)
        ON DELETE CASCADE,

    chip_id INTEGER NOT NULL
        REFERENCES hw.chip(id)
        ON DELETE CASCADE,

    relation TEXT NOT NULL
        CHECK (relation IN (
            'datasheet',
            'reference',
            'errata'
        )),

    PRIMARY KEY (document_id, chip_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_document_chip_chip
    ON knowledge.document_chip (chip_id);

COMMIT;
