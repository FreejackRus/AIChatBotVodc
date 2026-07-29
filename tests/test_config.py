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
