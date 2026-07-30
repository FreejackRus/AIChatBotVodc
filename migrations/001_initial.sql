CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS knowledge_sources (
    id uuid PRIMARY KEY,
    filename text NOT NULL,
    title text NOT NULL,
    url text NOT NULL UNIQUE,
    owner text NOT NULL,
    reviewed_at date NOT NULL,
    expires_at timestamptz,
    content_hash text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    indexed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    position integer NOT NULL,
    content text NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, position)
);

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS redacted_messages (
    id bigserial PRIMARY KEY,
    session_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    redacted_text text NOT NULL,
    redaction_categories text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS redacted_messages_created_at_idx
    ON redacted_messages (created_at);
CREATE INDEX IF NOT EXISTS redacted_messages_session_idx
    ON redacted_messages (session_id);

CREATE TABLE IF NOT EXISTS funnel_events (
    id bigserial PRIMARY KEY,
    session_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS funnel_events_created_at_idx
    ON funnel_events (created_at);
CREATE INDEX IF NOT EXISTS funnel_events_type_idx
    ON funnel_events (event_type, created_at);
