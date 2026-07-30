from __future__ import annotations

from dataclasses import dataclass

from config import ConfigurationError, Settings

from .adapters.event_store import InMemoryEventStore, PostgresEventStore
from .adapters.knowledge import LocalKnowledgeAdapter, PostgresKnowledgeAdapter
from .adapters.medangel import MedAngelAdapter
from .adapters.mis_cache import InMemoryMISResponseCache, RedisMISResponseCache
from .adapters.model_gateway import VLLMModelGateway
from .adapters.session_store import InMemorySessionStore, RedisSessionStore
from .domain.priorities import ServicePrioritizer
from .orchestrator import DialogOrchestrator
from .ports import EventStore, KnowledgePort, MedAngelPort, ModelPort, SessionStore
from .privacy import PIIRedactor
from .security import ActionTokenSigner


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    sessions: SessionStore
    events: EventStore
    knowledge: KnowledgePort
    model: ModelPort
    medangel: MedAngelPort
    orchestrator: DialogOrchestrator

    async def close(self) -> None:
        for dependency in (
            self.sessions,
            self.events,
            self.knowledge,
            self.model,
            self.medangel,
        ):
            await dependency.close()


def build_container(settings: Settings) -> ApplicationContainer:
    if settings.persistence_required and (
        not settings.redis_url or not settings.database_url
    ):
        raise ConfigurationError("В production обязательны REDIS_URL и DATABASE_URL")

    sessions = (
        RedisSessionStore(settings.redis_url, settings.session_ttl_seconds)
        if settings.redis_url
        else InMemorySessionStore(settings.session_ttl_seconds, settings.max_sessions)
    )
    events = (
        PostgresEventStore(settings.database_url)
        if settings.database_url
        else InMemoryEventStore()
    )
    knowledge = (
        PostgresKnowledgeAdapter(
            settings.database_url,
            settings.embedding_base_url,
            settings.embedding_model,
            settings.embedding_revision,
            settings.embedding_dimensions,
            settings.request_timeout,
            settings.rag_dense_weight,
            settings.rag_min_score,
            settings.rag_candidate_multiplier,
            settings.source_max_age_days,
            settings.rag_excerpt_chars,
            context_boost=settings.rag_context_boost,
        )
        if settings.database_url
        else LocalKnowledgeAdapter(
            settings.source_manifest_path,
            settings.rag_chunk_size,
            settings.rag_chunk_overlap,
            settings.source_max_age_days,
            settings.source_max_bytes,
            settings.rag_excerpt_chars,
            context_boost=settings.rag_context_boost,
        )
    )
    model = VLLMModelGateway(
        settings.model_base_urls,
        settings.chat_model,
        settings.request_timeout,
        settings.model_max_tokens,
    )
    medangel = MedAngelAdapter(
        settings.medangel_api_url,
        settings.medangel_api_key,
        settings.medangel_services_path,
        settings.medangel_doctors_path,
        settings.medangel_slots_path,
        settings.appointment_url,
        settings.request_timeout,
        settings.mis_catalog_cache_seconds,
        settings.mis_slots_cache_seconds,
        health_path=settings.medangel_health_path,
        max_response_bytes=settings.mis_max_response_bytes,
        cache=(
            RedisMISResponseCache(settings.redis_url)
            if settings.redis_url
            else InMemoryMISResponseCache(settings.mis_cache_max_entries)
        ),
    )
    orchestrator = DialogOrchestrator(
        sessions,
        events,
        knowledge,
        model,
        medangel,
        ActionTokenSigner(settings.signing_secret),
        PIIRedactor(),
        settings.rag_top_k,
        ServicePrioritizer.from_file(settings.service_priorities_path),
    )
    return ApplicationContainer(
        settings=settings,
        sessions=sessions,
        events=events,
        knowledge=knowledge,
        model=model,
        medangel=medangel,
        orchestrator=orchestrator,
    )
