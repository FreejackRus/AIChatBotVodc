from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
import weakref
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime
from typing import Any, TypeVar
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from ..domain.models import ChatSession, Doctor, Service, Slot
from ..metrics import MIS_CACHE, MIS_REQUEST_SECONDS, MIS_REQUESTS
from ..ports import MedAngelUnavailable
from .mis_cache import InMemoryMISResponseCache, MISResponseCache

T = TypeVar("T")
MOSCOW = ZoneInfo("Europe/Moscow")

# httpx logs the complete URL, including the service-search query, at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _cache_key(resource: str, path: str, params: Mapping[str, str]) -> str:
    # The Redis key must not reveal a user's search text.
    canonical = f"{resource}\n{path}\n{urlencode(sorted(params.items()))}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _string(
    item: Mapping[str, Any],
    *keys: str,
    required: bool = False,
    max_length: int = 1000,
) -> str | None:
    value: Any = None
    for key in keys:
        if key in item and item[key] is not None:
            value = item[key]
            break
    if value is None:
        if required:
            raise ValueError(f"missing {keys[0]}")
        return None
    if not isinstance(value, (str, int)):
        raise TypeError(f"invalid {keys[0]}")
    normalized = str(value).strip()
    if not normalized:
        if required:
            raise ValueError(f"invalid {keys[0]}")
        return None
    if len(normalized) > max_length or any(
        ord(char) < 32 for char in normalized
    ):
        raise ValueError(f"invalid {keys[0]}")
    return normalized


def _price(item: Mapping[str, Any]) -> str | None:
    value = item.get("price")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError("invalid price")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("invalid price")
    normalized = str(value).strip()
    if not normalized or len(normalized) > 100:
        raise ValueError("invalid price")
    return normalized


def _moscow_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid starts_at") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("starts_at must include timezone")
    return parsed.astimezone(MOSCOW).isoformat()


def _deduplicate(items: list[T], identity: Callable[[T], str]) -> list[T]:
    unique: dict[str, T] = {}
    for item in items:
        entity_id = identity(item)
        previous = unique.get(entity_id)
        if previous is not None and previous != item:
            raise ValueError(f"conflicting duplicate id: {entity_id}")
        unique[entity_id] = item
    return list(unique.values())


class MedAngelAdapter:
    """Fail-closed anti-corruption layer around the read-only MIS contract."""

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        services_path: str,
        doctors_path: str,
        slots_path: str,
        appointment_url: str,
        timeout: float,
        catalog_ttl: int,
        slots_ttl: int,
        *,
        health_path: str = "/health",
        max_response_bytes: int = 2_000_000,
        cache: MISResponseCache | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.services_path = services_path
        self.doctors_path = doctors_path
        self.slots_path = slots_path
        self.health_path = health_path
        self.max_response_bytes = max_response_bytes
        self.appointment_url = appointment_url
        self.catalog_ttl = catalog_ttl
        self.slots_ttl = slots_ttl
        self.cache = cache or InMemoryMISResponseCache()
        self._owns_http = http_client is None
        self.http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0))
        )
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request_items(
        self, resource: str, path: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        if not self.base_url:
            raise MedAngelUnavailable("MIS API не настроен")
        last_error: Exception | None = None
        started = time.perf_counter()
        try:
            for attempt in range(3):
                try:
                    async with self.http.stream(
                        "GET",
                        f"{self.base_url}{path}",
                        params=params,
                        headers=self._headers(),
                    ) as response:
                        response.raise_for_status()
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > self.max_response_bytes:
                                raise ValueError("response is too large")
                    body = json.loads(content)
                    items = (
                        body.get("items", body.get("data"))
                        if isinstance(body, dict)
                        else body
                    )
                    if not isinstance(items, list) or not all(
                        isinstance(item, dict) for item in items
                    ):
                        raise ValueError("invalid response envelope")
                    return items
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    if status != 429 and status < 500:
                        break
                except (TypeError, ValueError) as exc:
                    last_error = exc
                    break
                if attempt < 2:
                    await asyncio.sleep(0.2 * (2**attempt))
            MIS_REQUESTS.labels(resource, "error").inc()
            raise MedAngelUnavailable("MIS временно недоступна") from last_error
        finally:
            MIS_REQUEST_SECONDS.labels(resource).observe(time.perf_counter() - started)

    async def _load(
        self,
        resource: str,
        path: str,
        params: dict[str, str],
        ttl: int,
        parser: Callable[[list[dict[str, Any]]], T],
        cache_payload: Callable[[T], list[dict[str, Any]]],
        *,
        fresh: bool,
    ) -> T:
        key = _cache_key(resource, path, params)
        if fresh:
            MIS_CACHE.labels(resource, "bypass").inc()
        else:
            cached = await self.cache.get(key)
            if cached is not None:
                MIS_CACHE.labels(resource, "hit").inc()
                try:
                    return parser(cached)
                except (TypeError, ValueError) as exc:
                    raise MedAngelUnavailable(
                        "Кеш MIS содержит некорректную схему"
                    ) from exc
            MIS_CACHE.labels(resource, "miss").inc()

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if not fresh:
                cached = await self.cache.get(key)
                if cached is not None:
                    MIS_CACHE.labels(resource, "hit_after_wait").inc()
                    try:
                        return parser(cached)
                    except (TypeError, ValueError) as exc:
                        raise MedAngelUnavailable(
                            "Кеш MIS содержит некорректную схему"
                        ) from exc
            raw_items = await self._request_items(resource, path, params)
            try:
                parsed = parser(raw_items)
            except (TypeError, ValueError) as exc:
                MIS_REQUESTS.labels(resource, "schema_error").inc()
                raise MedAngelUnavailable("MIS вернула некорректную схему") from exc
            MIS_REQUESTS.labels(resource, "success").inc()
            if not fresh:
                await self.cache.set(key, cache_payload(parsed), ttl)
            return parsed

    @staticmethod
    def _parse_services(items: list[dict[str, Any]]) -> list[Service]:
        result = []
        for item in items:
            result.append(
                Service(
                    id=_string(item, "id", "service_id", required=True, max_length=128)
                    or "",
                    title=_string(item, "title", "name", required=True, max_length=300)
                    or "",
                    description=_string(item, "description", max_length=2000) or "",
                    price=_price(item),
                    branch_id=_string(item, "branch_id", max_length=128),
                    updated_at=_string(item, "updated_at", max_length=64),
                )
            )
        return _deduplicate(result, lambda item: item.id)[:5]

    @staticmethod
    def _parse_doctors(
        items: list[dict[str, Any]], service_id: str, branch_id: str | None
    ) -> list[Doctor]:
        result = []
        for item in items:
            item_service = _string(item, "service_id", max_length=128)
            item_branch = _string(item, "branch_id", max_length=128)
            if item_service and item_service != service_id:
                raise ValueError("doctor belongs to another service")
            if branch_id and item_branch and item_branch != branch_id:
                raise ValueError("doctor belongs to another branch")
            result.append(
                Doctor(
                    id=_string(item, "id", "doctor_id", required=True, max_length=128)
                    or "",
                    title=_string(item, "title", "name", required=True, max_length=300)
                    or "",
                    specialty=_string(item, "specialty", max_length=300) or "",
                    branch_id=item_branch or branch_id,
                    service_id=service_id,
                )
            )
        return _deduplicate(result, lambda item: item.id)[:5]

    @staticmethod
    def _parse_slots(
        items: list[dict[str, Any]],
        service_id: str,
        doctor_id: str | None,
        branch_id: str | None,
    ) -> list[Slot]:
        result = []
        for item in items:
            item_service = _string(item, "service_id", max_length=128)
            item_doctor = _string(item, "doctor_id", max_length=128) or doctor_id
            item_branch = _string(item, "branch_id", max_length=128)
            if item_service and item_service != service_id:
                raise ValueError("slot belongs to another service")
            if not item_doctor:
                raise ValueError("slot has no doctor")
            if doctor_id and item_doctor != doctor_id:
                raise ValueError("slot belongs to another doctor")
            if branch_id and item_branch and item_branch != branch_id:
                raise ValueError("slot belongs to another branch")
            starts_at = _string(
                item, "starts_at", "start", required=True, max_length=64
            )
            result.append(
                Slot(
                    id=_string(item, "id", "slot_id", required=True, max_length=128)
                    or "",
                    starts_at=_moscow_datetime(starts_at or ""),
                    doctor_id=item_doctor,
                    service_id=service_id,
                    branch_id=item_branch or branch_id,
                )
            )
        return _deduplicate(result, lambda item: item.id)[:8]

    async def search_services(
        self, query: str, *, fresh: bool = False
    ) -> list[Service]:
        return await self._load(
            "services",
            self.services_path,
            {"query": query},
            self.catalog_ttl,
            self._parse_services,
            lambda services: [asdict(service) for service in services],
            fresh=fresh,
        )

    async def doctors(
        self,
        service_id: str,
        branch_id: str | None = None,
        *,
        fresh: bool = False,
    ) -> list[Doctor]:
        params = {"service_id": service_id}
        if branch_id:
            params["branch_id"] = branch_id
        return await self._load(
            "doctors",
            self.doctors_path,
            params,
            self.catalog_ttl,
            lambda items: self._parse_doctors(items, service_id, branch_id),
            lambda doctors: [asdict(doctor) for doctor in doctors],
            fresh=fresh,
        )

    async def slots(
        self,
        service_id: str,
        doctor_id: str | None = None,
        branch_id: str | None = None,
        *,
        fresh: bool = False,
    ) -> list[Slot]:
        params = {"service_id": service_id}
        if doctor_id:
            params["doctor_id"] = doctor_id
        if branch_id:
            params["branch_id"] = branch_id
        return await self._load(
            "slots",
            self.slots_path,
            params,
            self.slots_ttl,
            lambda items: self._parse_slots(
                items, service_id, doctor_id, branch_id
            ),
            lambda slots: [asdict(slot) for slot in slots],
            fresh=fresh,
        )

    async def validate_service(self, service_id: str) -> Service | None:
        services = await self.search_services(service_id, fresh=True)
        return next((item for item in services if item.id == service_id), None)

    async def validate_doctor(
        self,
        doctor_id: str,
        service_id: str,
        branch_id: str | None = None,
    ) -> Doctor | None:
        doctors = await self.doctors(service_id, branch_id, fresh=True)
        return next((item for item in doctors if item.id == doctor_id), None)

    async def validate_slot(
        self,
        slot_id: str,
        service_id: str,
        doctor_id: str | None = None,
        branch_id: str | None = None,
    ) -> Slot | None:
        slots = await self.slots(
            service_id, doctor_id, branch_id, fresh=True
        )
        return next((item for item in slots if item.id == slot_id), None)

    def booking_url(self, session: ChatSession) -> str:
        selection = session.selection
        params = {
            key: value
            for key, value in {
                "service_id": selection.service_id,
                "doctor_id": selection.doctor_id,
                "branch_id": selection.branch_id,
                "slot_id": selection.slot_id,
                "source": "ai_chat",
            }.items()
            if value
        }
        separator = "&" if "?" in self.appointment_url else "?"
        return f"{self.appointment_url}{separator}{urlencode(params)}"

    async def ping(self) -> bool:
        if not self.base_url:
            return False
        try:
            response = await self.http.get(
                f"{self.base_url}{self.health_path}", headers=self._headers()
            )
            return response.is_success
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self.cache.close()
        if self._owns_http:
            await self.http.aclose()
