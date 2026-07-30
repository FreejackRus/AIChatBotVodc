#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${DATABASE_URL:?DATABASE_URL is required}"
command -v psql >/dev/null

for pass_number in 1 2; do
    for migration in "${project_dir}"/migrations/*.sql; do
        psql -X -v ON_ERROR_STOP=1 "${DATABASE_URL}" -f "${migration}" >/dev/null
    done
    echo "Migration pass ${pass_number} completed"
done

missing_tables="$(
    psql -X -A -t "${DATABASE_URL}" <<'SQL'
WITH expected(name) AS (
    VALUES
        ('knowledge_sources'),
        ('knowledge_chunks'),
        ('knowledge_index_runs'),
        ('catalog_audit_runs'),
        ('catalog_service_observations'),
        ('source_stage_runs'),
        ('source_candidates'),
        ('source_versions'),
        ('source_version_reviews'),
        ('knowledge_source_snapshots'),
        ('knowledge_snapshot_chunks'),
        ('knowledge_source_activations'),
        ('knowledge_publication_runs'),
        ('knowledge_publication_events')
)
SELECT string_agg(name, ', ' ORDER BY name)
FROM expected
WHERE to_regclass('public.' || name) IS NULL;
SQL
)"
if [[ -n "${missing_tables}" ]]; then
    echo "Missing migration tables: ${missing_tables}" >&2
    exit 1
fi

vector_type="$(
    psql -X -A -t "${DATABASE_URL}" <<'SQL'
SELECT format_type(a.atttypid, a.atttypmod)
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
WHERE c.relname = 'knowledge_chunks'
  AND a.attname = 'embedding'
  AND NOT a.attisdropped;
SQL
)"
if [[ "${vector_type}" != "vector(1024)" ]]; then
    echo "Unexpected knowledge_chunks.embedding type: ${vector_type}" >&2
    exit 1
fi

origin_default="$(
    psql -X -A -t "${DATABASE_URL}" <<'SQL'
SELECT column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'knowledge_sources'
  AND column_name = 'origin';
SQL
)"
if [[ "${origin_default}" != "'manual'::text" ]]; then
    echo "Unexpected knowledge_sources.origin default: ${origin_default}" >&2
    exit 1
fi

echo "Migration schema checks passed"
