from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_quality_policy_compose_and_real_pgvector_migrations():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    migration_check = (ROOT / "scripts/check_migrations.sh").read_text(
        encoding="utf-8"
    )
    development = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "ruff check ." in workflow
    assert "pytest -q" in workflow
    assert "scripts/check_architecture.py" in workflow
    assert "scripts/run_policy_evals.py" in workflow
    assert "docker compose config --quiet" in workflow
    assert "pgvector/pgvector:pg16" in workflow
    assert "scripts/check_migrations.sh" in workflow
    assert 'for pass_number in 1 2' in migration_check
    assert "vector(1024)" in migration_check
    assert "knowledge_source_snapshots" in migration_check
    assert "knowledge_publication_events" in migration_check
    assert "ruff==0.16.0" in development
