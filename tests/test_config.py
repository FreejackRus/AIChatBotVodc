import pytest

from config import ConfigurationError, Settings


def test_wildcard_cors_is_rejected(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_invalid_timeout_is_rejected(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("REQUEST_TIMEOUT", "not-a-number")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_embedding_dimension_must_match_pgvector_schema(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "768")
    with pytest.raises(ConfigurationError, match="1024"):
        Settings.from_env()


def test_embedding_revision_is_required(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("EMBEDDING_MODEL_REVISION", "")
    with pytest.raises(ConfigurationError, match="REVISION"):
        Settings.from_env()


def test_catalog_audit_url_is_restricted_to_vodc(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("CATALOG_AUDIT_URL", "https://evil.example/prices")
    with pytest.raises(ConfigurationError, match="vodc.ru"):
        Settings.from_env()


def test_source_staging_delay_may_be_zero(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("SOURCE_STAGING_DELAY_MS", "0")

    assert Settings.from_env().source_staging_delay_ms == 0


def test_medangel_paths_cannot_override_the_configured_host(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("MEDANGEL_SERVICES_PATH", "https://evil.example/services")

    with pytest.raises(ConfigurationError, match="API path"):
        Settings.from_env()


def test_booking_redirect_is_restricted_to_vodc(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("VODC_APPOINTMENT_URL", "https://evil.example/collect")

    with pytest.raises(ConfigurationError, match="vodc.ru"):
        Settings.from_env()


def test_production_requires_medangel_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("SIGNING_SECRET", "production-secret")
    monkeypatch.setenv("MEDANGEL_API_URL", "")

    with pytest.raises(ConfigurationError, match="MEDANGEL_API_URL"):
        Settings.from_env()


def test_production_rejects_medangel_placeholder(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("SIGNING_SECRET", "production-secret")
    monkeypatch.setenv(
        "MEDANGEL_API_URL", "https://REPLACE_WITH_TESTED_MEDANGEL_HOST"
    )
    monkeypatch.setenv("MEDANGEL_API_KEY", "REPLACE_WITH_SECRET")

    with pytest.raises(ConfigurationError, match="Placeholder"):
        Settings.from_env()


def test_mis_response_limit_must_be_positive(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "https://vodc.ru")
    monkeypatch.setenv("MIS_MAX_RESPONSE_BYTES", "0")

    with pytest.raises(ConfigurationError, match="MIS_MAX_RESPONSE_BYTES"):
        Settings.from_env()
