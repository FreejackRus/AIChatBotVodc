from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_staging_is_review_gated_and_not_connected_to_orchestrator():
    migration = (ROOT / "migrations/004_source_staging.sql").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "app/worker.py").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    orchestrator = (ROOT / "app/orchestrator.py").read_text(encoding="utf-8")
    review_script = (
        ROOT / "scripts/review_source_version.py"
    ).read_text(encoding="utf-8")

    assert "source_candidates" in migration
    assert "source_versions" in migration
    assert "source_version_reviews" in migration
    assert "pending_review" in migration
    assert "SemanticSourceStager" in worker
    assert "SOURCE_STAGING_ENABLED" in compose
    assert "source_versions" not in orchestrator
    assert "quality_issues" in review_script
