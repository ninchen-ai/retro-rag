-- Additive storage for multiple embedding models. Apply to retro_rag only after backup and test.
-- Existing rag.chunk, retrieval queries and import jobs remain unchanged.
BEGIN;

CREATE TABLE rag.chunk_embedding (
    chunk_id bigint NOT NULL REFERENCES rag.chunk(id) ON DELETE CASCADE,
    embedding_model text NOT NULL,
    embedding vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, embedding_model),
    CONSTRAINT chunk_embedding_supported_model_chk CHECK (
        embedding_model IN ('nomic-embed-text', 'bge-m3')
    ),
    CONSTRAINT chunk_embedding_dimensions_chk CHECK (
        (embedding_model = 'nomic-embed-text' AND vector_dims(embedding) = 768)
        OR (embedding_model = 'bge-m3' AND vector_dims(embedding) = 1024)
    )
);

-- Keep dimensions and model families separate for vector comparisons.
CREATE INDEX chunk_embedding_nomic_hnsw_idx
    ON rag.chunk_embedding USING hnsw ((embedding::vector(768)) vector_cosine_ops)
    WHERE embedding_model = 'nomic-embed-text';
CREATE INDEX chunk_embedding_bge_m3_hnsw_idx
    ON rag.chunk_embedding USING hnsw ((embedding::vector(1024)) vector_cosine_ops)
    WHERE embedding_model = 'bge-m3';

GRANT SELECT, INSERT, UPDATE, DELETE ON rag.chunk_embedding TO retro_rag_ingest;
GRANT SELECT ON rag.chunk_embedding TO retro_rag_reader;

-- Preserve existing 768-dimensional vectors without re-embedding.
INSERT INTO rag.chunk_embedding (chunk_id, embedding_model, embedding)
SELECT id, 'nomic-embed-text', embedding
FROM rag.chunk
WHERE embedding_model = 'nomic-embed-text'
ON CONFLICT (chunk_id, embedding_model) DO NOTHING;

COMMIT;
