-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS documents (
    id        SERIAL PRIMARY KEY,
    source    TEXT        NOT NULL,
    parser    TEXT        NOT NULL,  -- 'docling' | 'markitdown'
    status    TEXT        NOT NULL DEFAULT 'pending',  -- 'pending' | 'processing' | 'completed' | 'failed'
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Chunks table
-- chunk_type: 'table' | 'text'
-- embedding: bge-m3 dense 1024차원 (LOCKED)
CREATE TABLE IF NOT EXISTS chunks (
    id             SERIAL PRIMARY KEY,
    document_id    INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_type     TEXT    NOT NULL,
    content        TEXT    NOT NULL,
    section_header TEXT,
    caption        TEXT,
    page_number    INTEGER,
    embedding      vector(1024),
    sparse_embedding JSONB,
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for dense cosine search
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- GIN trigram index for lexical search
CREATE INDEX IF NOT EXISTS chunks_content_trgm_idx
    ON chunks USING gin (content gin_trgm_ops);
