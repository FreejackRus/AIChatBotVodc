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
