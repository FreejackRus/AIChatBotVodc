from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_audit_is_isolated_and_operationally_wired():
    migration = (ROOT / "migrations/003_catalog_audit.sql").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "app/worker.py").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    alerts = (ROOT / "ops/alert-rules.yml").read_text(encoding="utf-8")
    orchestrator = (ROOT / "app/orchestrator.py").read_text(encoding="utf-8")

    assert "catalog_audit_runs" in migration
    assert "catalog_service_observations" in migration
    assert "catalog_audit_issues" in migration
    assert "VodcCatalogAuditor" in worker
    assert "CATALOG_AUDIT_ENABLED" in compose
    assert "VodcCatalogAuditQuarantined" in alerts
    assert "catalog_service_observations" not in orchestrator
