ALTER TABLE source_version_reviews
    ADD COLUMN IF NOT EXISTS reviewer_role text NOT NULL DEFAULT 'content_owner';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'source_version_reviews_role_check'
    ) THEN
        ALTER TABLE source_version_reviews
            ADD CONSTRAINT source_version_reviews_role_check
            CHECK (reviewer_role IN ('content_owner', 'medical_owner'));
    END IF;
END
$$;

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS source_version_id uuid
        REFERENCES source_versions(id) ON DELETE SET NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'knowledge_sources_origin_check'
    ) THEN
        ALTER TABLE knowledge_sources
            ADD CONSTRAINT knowledge_sources_origin_check
            CHECK (origin IN ('manual', 'staged'));
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS knowledge_publication_runs (
    id uuid PRIMARY KEY,
    action text NOT NULL CHECK (action IN ('publish', 'rollback')),
    status text NOT NULL CHECK (status IN ('success', 'failed')),
    actor text NOT NULL,
    stats jsonb NOT NULL DEFAULT '{}',
    completed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_source_snapshots (
    id uuid PRIMARY KEY,
    source_version_id uuid NOT NULL
        REFERENCES source_versions(id) ON DELETE RESTRICT,
    candidate_id uuid NOT NULL REFERENCES source_candidates(id) ON DELETE RESTRICT,
    url text NOT NULL,
    title text NOT NULL,
    owner text NOT NULL,
    reviewed_at date NOT NULL,
    content_hash text NOT NULL,
    embedding_model text NOT NULL,
    embedding_revision text NOT NULL,
    embedding_dimensions integer NOT NULL,
    chunk_size integer NOT NULL,
    chunk_overlap integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (
        source_version_id, embedding_model, embedding_revision,
        embedding_dimensions, chunk_size, chunk_overlap
    )
);

CREATE TABLE IF NOT EXISTS knowledge_snapshot_chunks (
    snapshot_id uuid NOT NULL
        REFERENCES knowledge_source_snapshots(id) ON DELETE CASCADE,
    position integer NOT NULL,
    content text NOT NULL,
    content_hash text NOT NULL,
    embedding vector(1024) NOT NULL,
    PRIMARY KEY (snapshot_id, position)
);

CREATE TABLE IF NOT EXISTS knowledge_source_activations (
    source_id uuid PRIMARY KEY
        REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL
        REFERENCES knowledge_source_snapshots(id) ON DELETE RESTRICT,
    activated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_publication_events (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL
        REFERENCES knowledge_publication_runs(id) ON DELETE CASCADE,
    source_id uuid NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    previous_snapshot_id uuid
        REFERENCES knowledge_source_snapshots(id) ON DELETE RESTRICT,
    snapshot_id uuid NOT NULL
        REFERENCES knowledge_source_snapshots(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_snapshots_url_created_idx
    ON knowledge_source_snapshots (url, created_at DESC);
CREATE INDEX IF NOT EXISTS knowledge_publication_events_source_idx
    ON knowledge_publication_events (source_id, created_at DESC);
