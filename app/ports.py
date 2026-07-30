from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from .domain.models import (
    ChatSession,
    Doctor,
    Service,
    Slot,
    SourceRef,
)


class PortUnavailable(RuntimeError):
    """Infrastructure dependency cannot currently fulfill its contract."""


class KnowledgeUnavailable(PortUnavailable):
    pass


class ModelUnavailable(PortUnavailable):
    pass


class MedAngelUnavailable(PortUnavailable):
    pass


class SessionStore(Protocol):
    async def create(self, session: ChatSession) -> None: ...
    async def get(self, session_id: str) -> ChatSession | None: ...
    async def save(self, session: ChatSession) -> None: ...
    async def delete(self, session_id: str) -> None: ...
    async def allow_request(self, key: str, limit: int, window: int) -> bool: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class EventStore(Protocol):
    async def record_message(
        self,
        session_id: str,
        role: str,
        redacted_text: str,
        categories: tuple[str, ...],
    ) -> None: ...
    async def record_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None: ...
    async def cleanup(self, retention_days: int) -> int: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class KnowledgePort(Protocol):
    async def search(self, query: str, limit: int) -> list[SourceRef]: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class ModelPort(Protocol):
    def stream(
        self,
        *,
        prompt: str,
        history: list[dict[str, str]],
        sources: list[SourceRef],
    ) -> AsyncIterator[str]: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class MedAngelPort(Protocol):
    async def search_services(
        self, query: str, *, fresh: bool = False
    ) -> list[Service]: ...
    async def doctors(
        self,
        service_id: str,
        branch_id: str | None = None,
        *,
        fresh: bool = False,
    ) -> list[Doctor]: ...
    async def slots(
        self,
        service_id: str,
        doctor_id: str | None = None,
        branch_id: str | None = None,
        *,
        fresh: bool = False,
    ) -> list[Slot]: ...
    async def validate_service(self, service_id: str) -> Service | None: ...
    async def validate_doctor(
        self,
        doctor_id: str,
        service_id: str,
        branch_id: str | None = None,
    ) -> Doctor | None: ...
    async def validate_slot(
        self,
        slot_id: str,
        service_id: str,
        doctor_id: str | None = None,
        branch_id: str | None = None,
    ) -> Slot | None: ...
    def booking_url(self, session: ChatSession) -> str: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...
