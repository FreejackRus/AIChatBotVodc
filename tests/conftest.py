from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.adapters.event_store import InMemoryEventStore
from app.adapters.session_store import InMemorySessionStore
from app.container import ApplicationContainer
from app.domain.models import Doctor, Service, Slot, SourceRef
from app.orchestrator import DialogOrchestrator
from app.privacy import PIIRedactor
from app.security import ActionTokenSigner


class FakeKnowledge:
    ready = True

    async def search(self, query, limit):
        return [
            SourceRef(
                id="source-1",
                title="Официальная информация ВОККДЦ",
                url="https://vodc.ru/",
                excerpt=f"Подтверждённая информация по запросу: {query}",
                reviewed_at="2026-07-23",
                score=0.95,
            )
        ][:limit]

    async def ping(self):
        return self.ready

    async def close(self):
        return None


class FakeModel:
    ready = True

    def __init__(self):
        self.calls = 0
        self.chunks = ["Подтверждённый ", "ответ."]

    async def stream(self, *, prompt, history, sources):
        self.calls += 1
        for chunk in self.chunks:
            yield chunk

    async def ping(self):
        return self.ready

    async def close(self):
        return None


class FakeMedAngel:
    ready = True

    def __init__(self):
        self.fail = False
        self.search_calls = 0

    def _check(self):
        if self.fail:
            from app.ports import MedAngelUnavailable

            raise MedAngelUnavailable("MIS unavailable")

    async def search_services(self, query):
        self._check()
        self.search_calls += 1
        return [
            Service(
                id="service-1",
                title="МРТ",
                description="Магнитно-резонансная томография",
                price="от 3 000 ₽",
            )
        ]

    async def doctors(self, service_id, branch_id=None):
        self._check()
        return [
            Doctor(
                id="doctor-1",
                title="Иванов И. И.",
                specialty="Врач-рентгенолог",
                service_id=service_id,
                branch_id="branch-1",
            )
        ]

    async def slots(self, service_id, doctor_id=None, branch_id=None):
        self._check()
        return [
            Slot(
                id="slot-1",
                starts_at="2026-08-01T10:00:00+03:00",
                doctor_id=doctor_id or "doctor-1",
                service_id=service_id,
                branch_id=branch_id or "branch-1",
            )
        ]

    async def validate_service(self, service_id):
        return (
            (await self.search_services(service_id))[0]
            if service_id == "service-1"
            else None
        )

    async def validate_doctor(self, doctor_id, service_id):
        return (await self.doctors(service_id))[0] if doctor_id == "doctor-1" else None

    async def validate_slot(self, slot_id, service_id):
        return (
            (await self.slots(service_id, "doctor-1", "branch-1"))[0]
            if slot_id == "slot-1"
            else None
        )

    def booking_url(self, session):
        return (
            "https://vodc.ru/appointment/"
            f"?service_id={session.selection.service_id}"
            f"&doctor_id={session.selection.doctor_id}"
            f"&slot_id={session.selection.slot_id}"
            "&source=ai_chat"
        )

    async def ping(self):
        return self.ready

    async def close(self):
        return None


@pytest.fixture
def api(monkeypatch, tmp_path):
    knowledge_dir = tmp_path / "knowledge_base"
    knowledge_dir.mkdir()
    manifest = knowledge_dir / "sources.json"
    manifest.write_text('{"version": 2, "sources": []}', encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5000")
    monkeypatch.setenv("TRUSTED_PAGE_HOSTS", "localhost,127.0.0.1")
    monkeypatch.setenv("SOURCE_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "100")
    monkeypatch.setenv("MAX_MESSAGE_LENGTH", "100")

    import config

    config.get_settings.cache_clear()
    settings = replace(
        config.get_settings(),
        persistence_required=False,
        session_ttl_seconds=7200,
    )
    sessions = InMemorySessionStore(7200)
    events = InMemoryEventStore()
    knowledge = FakeKnowledge()
    model = FakeModel()
    mis = FakeMedAngel()
    signer = ActionTokenSigner("test-signing-secret")
    orchestrator = DialogOrchestrator(
        sessions,
        events,
        knowledge,
        model,
        mis,
        signer,
        PIIRedactor(),
        settings.rag_top_k,
    )
    container = ApplicationContainer(
        settings=settings,
        sessions=sessions,
        events=events,
        knowledge=knowledge,
        model=model,
        medangel=mis,
        orchestrator=orchestrator,
    )

    from app.main import create_app

    application = create_app(container)
    with TestClient(application, base_url="http://localhost:5000") as client:
        yield {
            "client": client,
            "container": container,
            "events": events,
            "model": model,
            "mis": mis,
        }
    config.get_settings.cache_clear()


@pytest.fixture
def create_session(api):
    def create():
        response = api["client"].post(
            "/api/v1/sessions",
            json={
                "page_context": {
                    "url": "http://localhost:5000/services/mri",
                    "title": "МРТ",
                },
                "client": {
                    "locale": "ru",
                    "timezone": "Europe/Moscow",
                    "privacy_notice_version": "1.0",
                },
            },
        )
        assert response.status_code == 201
        return response.json()

    return create
