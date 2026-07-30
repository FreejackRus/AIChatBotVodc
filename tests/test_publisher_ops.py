from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_controlled_publisher_has_review_snapshot_and_rollback_boundaries():
    migration = (ROOT / "migrations/005_controlled_publisher.sql").read_text(
        encoding="utf-8"
    )
    publisher = (ROOT / "app/publisher.py").read_text(encoding="utf-8")
    ingestion = (ROOT / "app/ingestion.py").read_text(encoding="utf-8")
    cli = (ROOT / "scripts/publish_staged_sources.py").read_text(
        encoding="utf-8"
    )
    review = (ROOT / "scripts/review_source_version.py").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "app/worker.py").read_text(encoding="utf-8")

    assert "knowledge_source_snapshots" in migration
    assert "knowledge_snapshot_chunks" in migration
    assert "knowledge_publication_events" in migration
    assert "reviewer_role" in migration
    assert "previous_snapshot_id" in publisher
    assert "Manual source нельзя перезаписать" in publisher
    assert "WHERE origin = 'manual'" in ingestion
    assert "--apply" in cli
    assert "--rollback-url" in cli
    assert "medical_owner" in review
    assert "ControlledPublisher" not in worker
