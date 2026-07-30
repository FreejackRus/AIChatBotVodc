import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_knowledge_migration_and_observability_are_wired():
    migration = (ROOT / "migrations/002_knowledge_pipeline.sql").read_text(
        encoding="utf-8"
    )
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prometheus = (ROOT / "ops/prometheus.yml").read_text(encoding="utf-8")
    alerts = (ROOT / "ops/alert-rules.yml").read_text(encoding="utf-8")
    dashboard = json.loads(
        (ROOT / "ops/dashboards/vodc-knowledge.json").read_text(encoding="utf-8")
    )
    embedding = json.loads(
        (ROOT / "config/embedding_model.json").read_text(encoding="utf-8")
    )

    assert "GENERATED ALWAYS AS (to_tsvector('russian', content))" in migration
    assert "knowledge_index_runs" in migration
    assert 'WORKER_METRICS_PORT: 9101' in compose
    assert 'targets: ["worker:9101"]' in prometheus
    assert "VodcKnowledgeIngestionFailed" in alerts
    assert dashboard["uid"] == "vodc-knowledge"
    assert len(dashboard["panels"]) == 5
    assert embedding["dimensions"] == 1024
    assert embedding["document_instruction"] is None
