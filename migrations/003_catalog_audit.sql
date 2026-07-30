CREATE TABLE IF NOT EXISTS catalog_audit_runs (
    id uuid PRIMARY KEY,
    source_url text NOT NULL,
    final_url text NOT NULL,
    status text NOT NULL
        CHECK (status IN ('success', 'quarantined', 'unchanged', 'failed')),
    content_hash text,
    etag text,
    last_modified text,
    row_count integer NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    service_count integer NOT NULL DEFAULT 0 CHECK (service_count >= 0),
    issue_count integer NOT NULL DEFAULT 0 CHECK (issue_count >= 0),
    stats jsonb NOT NULL DEFAULT '{}',
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS catalog_audit_runs_source_completed_idx
    ON catalog_audit_runs (source_url, completed_at DESC);
CREATE INDEX IF NOT EXISTS catalog_audit_runs_status_completed_idx
    ON catalog_audit_runs (status, completed_at DESC);

CREATE TABLE IF NOT EXISTS catalog_service_observations (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL
        REFERENCES catalog_audit_runs(id) ON DELETE CASCADE,
    service_code text NOT NULL,
    name text NOT NULL,
    price_text text NOT NULL,
    price_min_rub integer CHECK (price_min_rub IS NULL OR price_min_rub >= 0),
    category_path text[] NOT NULL DEFAULT '{}',
    detail_url text,
    row_hash text NOT NULL
);

CREATE INDEX IF NOT EXISTS catalog_observations_run_code_idx
    ON catalog_service_observations (run_id, service_code);
CREATE INDEX IF NOT EXISTS catalog_observations_code_idx
    ON catalog_service_observations (service_code);

CREATE TABLE IF NOT EXISTS catalog_audit_issues (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL
        REFERENCES catalog_audit_runs(id) ON DELETE CASCADE,
    code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('warning', 'critical')),
    service_code text,
    details jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS catalog_audit_issues_run_idx
    ON catalog_audit_issues (run_id);
CREATE INDEX IF NOT EXISTS catalog_audit_issues_severity_idx
    ON catalog_audit_issues (severity, created_at DESC);
