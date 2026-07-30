"""Environment-only configuration shared by the API and maintenance tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Configuration is missing or unsafe."""


def _parse_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} должен быть true или false")


def _parse_int(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} должен быть целым числом") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} должен быть не меньше {minimum}")
    return value


def _parse_float(name: str, default: float, minimum: float = 0.1) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} должен быть числом") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} должен быть не меньше {minimum}")
    return value


def _parse_ratio(name: str, default: float) -> float:
    value = _parse_float(name, default, minimum=0.0)
    if value > 1:
        raise ConfigurationError(f"{name} должен быть в диапазоне от 0 до 1")
    return value


def _validate_http_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"{name} должен быть корректным HTTP(S) URL")
    return value.rstrip("/")


def _optional_http_url(name: str, value: str) -> str | None:
    value = value.strip()
    return _validate_http_url(name, value) if value else None


def _validate_vodc_url(name: str, value: str) -> str:
    normalized = _validate_http_url(name, value)
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
        "vodc.ru",
        "www.vodc.ru",
    }:
        raise ConfigurationError(
            f"{name} должен быть HTTPS URL домена vodc.ru"
        )
    return normalized


def _validate_api_path(name: str, value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            f"{name} должен быть относительным API path, начинающимся с /"
        )
    return normalized


def _csv(name: str, default: str, *, strip_slash: bool = True) -> tuple[str, ...]:
    values = tuple(
        (value.strip().rstrip("/") if strip_slash else value.strip())
        for value in os.getenv(name, default).split(",")
        if value.strip()
    )
    if not values:
        raise ConfigurationError(f"{name} не должен быть пустым")
    return values


@dataclass(frozen=True)
class Settings:
    app_host: str
    app_port: int
    app_debug: bool
    environment: str
    cors_origins: tuple[str, ...]
    trusted_page_hosts: tuple[str, ...]
    model_base_urls: tuple[str, ...]
    chat_model: str
    embedding_base_url: str
    embedding_model: str
    embedding_revision: str
    embedding_dimensions: int
    embedding_batch_size: int
    model_context_tokens: int
    model_max_tokens: int
    source_manifest_path: Path
    service_priorities_path: Path
    rag_chunk_size: int
    rag_chunk_overlap: int
    rag_top_k: int
    rag_dense_weight: float
    rag_min_score: float
    rag_candidate_multiplier: int
    rag_excerpt_chars: int
    source_max_age_days: int
    source_max_bytes: int
    catalog_audit_enabled: bool
    catalog_audit_url: str
    catalog_audit_min_services: int
    catalog_audit_max_bytes: int
    catalog_audit_max_removed_ratio: float
    source_discovery_manifest_path: Path
    source_staging_enabled: bool
    source_staging_batch_size: int
    source_staging_delay_ms: int
    source_staging_max_bytes: int
    request_timeout: float
    health_timeout: float
    session_ttl_seconds: int
    transcript_retention_days: int
    max_message_length: int
    max_request_bytes: int
    rate_limit_requests: int
    rate_limit_window_seconds: int
    max_sessions: int
    redis_url: str | None
    database_url: str | None
    persistence_required: bool
    signing_secret: str
    medangel_api_url: str | None
    medangel_api_key: str | None
    medangel_services_path: str
    medangel_doctors_path: str
    medangel_slots_path: str
    medangel_health_path: str
    appointment_url: str
    mis_catalog_cache_seconds: int
    mis_slots_cache_seconds: int
    mis_cache_max_entries: int
    mis_max_response_bytes: int
    analytics_measurement_id: str | None
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

        origins = _csv(
            "CORS_ORIGINS",
            "http://localhost:5000,http://127.0.0.1:5000",
        )
        if "*" in origins:
            raise ConfigurationError(
                "CORS_ORIGINS='*' запрещён; перечислите доверенные origins"
            )
        for origin in origins:
            _validate_http_url("CORS_ORIGINS", origin)

        source_manifest_path = Path(
            os.getenv("SOURCE_MANIFEST_PATH", "knowledge_base/sources.json")
        ).expanduser()
        if not source_manifest_path.is_absolute():
            source_manifest_path = (
                Path(__file__).resolve().parent / source_manifest_path
            )
        service_priorities_path = Path(
            os.getenv(
                "SERVICE_PRIORITIES_PATH",
                "config/service_priorities.json",
            )
        ).expanduser()
        if not service_priorities_path.is_absolute():
            service_priorities_path = (
                Path(__file__).resolve().parent / service_priorities_path
            )
        source_discovery_manifest_path = Path(
            os.getenv(
                "SOURCE_DISCOVERY_MANIFEST_PATH",
                "knowledge_base/discovery.json",
            )
        ).expanduser()
        if not source_discovery_manifest_path.is_absolute():
            source_discovery_manifest_path = (
                Path(__file__).resolve().parent / source_discovery_manifest_path
            )

        model_urls = _csv("MODEL_BASE_URLS", "http://localhost:8000")
        for model_url in model_urls:
            _validate_http_url("MODEL_BASE_URLS", model_url)

        chunk_size = _parse_int("RAG_CHUNK_SIZE", 1000)
        chunk_overlap = _parse_int("RAG_CHUNK_OVERLAP", 200, minimum=0)
        if chunk_overlap >= chunk_size:
            raise ConfigurationError(
                "RAG_CHUNK_OVERLAP должен быть меньше RAG_CHUNK_SIZE"
            )
        embedding_dimensions = _parse_int("EMBEDDING_DIMENSIONS", 1024)
        if embedding_dimensions != 1024:
            raise ConfigurationError(
                "EMBEDDING_DIMENSIONS должен быть 1024 для текущей схемы pgvector"
            )
        embedding_revision = os.getenv(
            "EMBEDDING_MODEL_REVISION",
            "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        ).strip()
        if not embedding_revision:
            raise ConfigurationError("EMBEDDING_MODEL_REVISION не должен быть пустым")

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("LOG_LEVEL содержит неизвестный уровень")

        environment = os.getenv("APP_ENV", "development").strip().lower()
        if environment not in {"development", "test", "production"}:
            raise ConfigurationError(
                "APP_ENV должен быть development, test или production"
            )
        signing_secret = os.getenv(
            "SIGNING_SECRET", "dev-only-change-before-production"
        )
        if environment == "production" and signing_secret.startswith("dev-only"):
            raise ConfigurationError("SIGNING_SECRET обязан быть заменён в production")
        medangel_api_url = _optional_http_url(
            "MEDANGEL_API_URL", os.getenv("MEDANGEL_API_URL", "")
        )
        if environment == "production" and not medangel_api_url:
            raise ConfigurationError("MEDANGEL_API_URL обязателен в production")
        medangel_api_key = os.getenv("MEDANGEL_API_KEY", "").strip() or None
        if environment == "production" and (
            "replace_with" in (medangel_api_url or "").lower()
            or "replace_with" in (medangel_api_key or "").lower()
        ):
            raise ConfigurationError(
                "Placeholder MEDANGEL_API_URL/MEDANGEL_API_KEY запрещён в production"
            )

        return cls(
            app_host=os.getenv("APP_HOST", "0.0.0.0"),
            app_port=_parse_int("APP_PORT", 5000),
            app_debug=_parse_bool("APP_DEBUG", False),
            environment=environment,
            cors_origins=origins,
            trusted_page_hosts=_csv(
                "TRUSTED_PAGE_HOSTS",
                "vodc.ru,www.vodc.ru,localhost,127.0.0.1",
                strip_slash=False,
            ),
            model_base_urls=model_urls,
            chat_model=os.getenv("CHAT_MODEL", "Qwen3.5-9B").strip(),
            embedding_base_url=_validate_http_url(
                "EMBEDDING_BASE_URL",
                os.getenv("EMBEDDING_BASE_URL", "http://localhost:8001"),
            ),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL", "Qwen3-Embedding-0.6B"
            ).strip(),
            embedding_revision=embedding_revision,
            embedding_dimensions=embedding_dimensions,
            embedding_batch_size=_parse_int("EMBEDDING_BATCH_SIZE", 16),
            model_context_tokens=_parse_int("MODEL_CONTEXT_TOKENS", 8192),
            model_max_tokens=_parse_int("MODEL_MAX_TOKENS", 768),
            source_manifest_path=source_manifest_path,
            service_priorities_path=service_priorities_path,
            rag_chunk_size=chunk_size,
            rag_chunk_overlap=chunk_overlap,
            rag_top_k=_parse_int("RAG_TOP_K", 3),
            rag_dense_weight=_parse_ratio("RAG_DENSE_WEIGHT", 0.8),
            rag_min_score=_parse_ratio("RAG_MIN_SCORE", 0.3),
            rag_candidate_multiplier=_parse_int("RAG_CANDIDATE_MULTIPLIER", 8),
            rag_excerpt_chars=_parse_int("RAG_EXCERPT_CHARS", 800),
            source_max_age_days=_parse_int("SOURCE_MAX_AGE_DAYS", 180),
            source_max_bytes=_parse_int("SOURCE_MAX_BYTES", 2_000_000),
            catalog_audit_enabled=_parse_bool("CATALOG_AUDIT_ENABLED", False),
            catalog_audit_url=_validate_vodc_url(
                "CATALOG_AUDIT_URL",
                os.getenv(
                    "CATALOG_AUDIT_URL",
                    "https://www.vodc.ru/pacientam/platnye/platnye.php",
                ),
            ),
            catalog_audit_min_services=_parse_int(
                "CATALOG_AUDIT_MIN_SERVICES", 1000
            ),
            catalog_audit_max_bytes=_parse_int(
                "CATALOG_AUDIT_MAX_BYTES", 2_000_000
            ),
            catalog_audit_max_removed_ratio=_parse_ratio(
                "CATALOG_AUDIT_MAX_REMOVED_RATIO", 0.2
            ),
            source_discovery_manifest_path=source_discovery_manifest_path,
            source_staging_enabled=_parse_bool("SOURCE_STAGING_ENABLED", False),
            source_staging_batch_size=_parse_int(
                "SOURCE_STAGING_BATCH_SIZE", 25
            ),
            source_staging_delay_ms=_parse_int(
                "SOURCE_STAGING_DELAY_MS", 500, minimum=0
            ),
            source_staging_max_bytes=_parse_int(
                "SOURCE_STAGING_MAX_BYTES", 2_000_000
            ),
            request_timeout=_parse_float("REQUEST_TIMEOUT", 30.0),
            health_timeout=_parse_float("HEALTH_TIMEOUT", 2.0),
            session_ttl_seconds=_parse_int("SESSION_TTL_SECONDS", 7200),
            transcript_retention_days=_parse_int("TRANSCRIPT_RETENTION_DAYS", 90),
            max_message_length=_parse_int("MAX_MESSAGE_LENGTH", 2000),
            max_request_bytes=_parse_int("MAX_REQUEST_BYTES", 65536),
            rate_limit_requests=_parse_int("RATE_LIMIT_REQUESTS", 30),
            rate_limit_window_seconds=_parse_int("RATE_LIMIT_WINDOW_SECONDS", 60),
            max_sessions=_parse_int("MAX_SESSIONS", 1000),
            redis_url=os.getenv("REDIS_URL", "").strip() or None,
            database_url=os.getenv("DATABASE_URL", "").strip() or None,
            persistence_required=_parse_bool(
                "PERSISTENCE_REQUIRED", environment == "production"
            ),
            signing_secret=signing_secret,
            medangel_api_url=medangel_api_url,
            medangel_api_key=medangel_api_key,
            medangel_services_path=_validate_api_path(
                "MEDANGEL_SERVICES_PATH",
                os.getenv("MEDANGEL_SERVICES_PATH", "/services"),
            ),
            medangel_doctors_path=_validate_api_path(
                "MEDANGEL_DOCTORS_PATH",
                os.getenv("MEDANGEL_DOCTORS_PATH", "/doctors"),
            ),
            medangel_slots_path=_validate_api_path(
                "MEDANGEL_SLOTS_PATH",
                os.getenv("MEDANGEL_SLOTS_PATH", "/schedule"),
            ),
            medangel_health_path=_validate_api_path(
                "MEDANGEL_HEALTH_PATH",
                os.getenv("MEDANGEL_HEALTH_PATH", "/health"),
            ),
            appointment_url=_validate_vodc_url(
                "VODC_APPOINTMENT_URL",
                os.getenv(
                    "VODC_APPOINTMENT_URL",
                    "https://vodc.ru/appointment/",
                ),
            ),
            mis_catalog_cache_seconds=_parse_int("MIS_CATALOG_CACHE_SECONDS", 300),
            mis_slots_cache_seconds=_parse_int("MIS_SLOTS_CACHE_SECONDS", 30),
            mis_cache_max_entries=_parse_int("MIS_CACHE_MAX_ENTRIES", 512),
            mis_max_response_bytes=_parse_int(
                "MIS_MAX_RESPONSE_BYTES", 2_000_000
            ),
            analytics_measurement_id=os.getenv("YANDEX_METRIKA_ID", "").strip() or None,
            log_level=log_level,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
