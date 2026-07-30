CREATE TABLE IF NOT EXISTS source_stage_runs (
    id uuid PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    stats jsonb NOT NULL DEFAULT '{}',
    started_at timestamptz NOT NULL,
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS source_stage_runs_completed_idx
    ON source_stage_runs (completed_at DESC);

CREATE TABLE IF NOT EXISTS source_candidates (
    id uuid PRIMARY KEY,
    url text NOT NULL UNIQUE,
    source_type text NOT NULL
        CHECK (source_type IN ('organizational', 'preparation', 'service_description')),
    risk_tier text NOT NULL CHECK (risk_tier IN ('low', 'medium', 'medical')),
    owner text NOT NULL,
    service_code text,
    enabled boolean NOT NULL DEFAULT true,
    etag text,
    last_modified text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz,
    last_error text
);

CREATE INDEX IF NOT EXISTS source_candidates_due_idx
    ON source_candidates (enabled, last_checked_at NULLS FIRST, source_type);
CREATE INDEX IF NOT EXISTS source_candidates_service_code_idx
    ON source_candidates (service_code) WHERE service_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS source_versions (
    id uuid PRIMARY KEY,
    candidate_id uuid NOT NULL
        REFERENCES source_candidates(id) ON DELETE CASCADE,
    run_id uuid NOT NULL REFERENCES source_stage_runs(id) ON DELETE CASCADE,
    content_hash text NOT NULL,
    title text NOT NULL,
    extracted_text text NOT NULL,
    sections jsonb NOT NULL,
    quality_issues text[] NOT NULL DEFAULT '{}',
    review_status text NOT NULL
        CHECK (review_status IN ('pending_review', 'quarantined', 'approved', 'rejected')),
    fetched_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (candidate_id, content_hash)
);

CREATE INDEX IF NOT EXISTS source_versions_candidate_fetched_idx
    ON source_versions (candidate_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS source_versions_review_idx
    ON source_versions (review_status, fetched_at);

CREATE TABLE IF NOT EXISTS source_version_reviews (
    id bigserial PRIMARY KEY,
    version_id uuid NOT NULL REFERENCES source_versions(id) ON DELETE CASCADE,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reviewer text NOT NULL,
    reason text NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS source_version_reviews_version_idx
    ON source_version_reviews (version_id, reviewed_at DESC);
