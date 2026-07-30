ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS embedding_model text,
    ADD COLUMN IF NOT EXISTS embedding_revision text,
    ADD COLUMN IF NOT EXISTS embedding_dimensions integer,
    ADD COLUMN IF NOT EXISTS chunk_size integer,
    ADD COLUMN IF NOT EXISTS chunk_overlap integer,
    ADD COLUMN IF NOT EXISTS last_checked_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS content_hash text;

UPDATE knowledge_chunks
SET content_hash = encode(digest(content, 'sha256'), 'hex')
WHERE content_hash IS NULL;

ALTER TABLE knowledge_chunks
    ALTER COLUMN content_hash SET NOT NULL;

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('russian', content)) STORED;

CREATE INDEX IF NOT EXISTS knowledge_chunks_search_gin
    ON knowledge_chunks USING gin (search_vector);

CREATE INDEX IF NOT EXISTS knowledge_sources_active_idx
    ON knowledge_sources (enabled, reviewed_at, expires_at);

CREATE TABLE IF NOT EXISTS knowledge_index_runs (
    id bigserial PRIMARY KEY,
    manifest_hash text NOT NULL,
    embedding_model text NOT NULL,
    embedding_revision text NOT NULL DEFAULT 'unknown',
    stats jsonb NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE knowledge_index_runs
    ADD COLUMN IF NOT EXISTS embedding_revision text NOT NULL DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS knowledge_index_runs_completed_at_idx
    ON knowledge_index_runs (completed_at DESC);
