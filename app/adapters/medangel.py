from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from ..domain.models import ChatSession, Doctor, Service, Slot
from ..ports import MedAngelUnavailable


class MedAngelAdapter:
    """Narrow anti-corruption layer around the actual MIS contract."""

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
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.services_path = services_path
        self.doctors_path = doctors_path
        self.slots_path = slots_path
        self.appointment_url = appointment_url
        self.catalog_ttl = catalog_ttl
        self.slots_ttl = slots_ttl
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0))
        )
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _get(
        self, path: str, params: dict[str, str], ttl: int
    ) -> list[dict[str, Any]]:
        if not self.base_url:
            raise MedAngelUnavailable("MIS API не настроен")
        cache_key = f"{path}:{urlencode(sorted(params.items()))}"
        cached = self._cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last_error: Exception | None = None
        body = None
        for attempt in range(3):
            try:
                response = await self.http.get(
                    f"{self.base_url}{path}", params=params, headers=headers
                )
                response.raise_for_status()
                body = response.json()
                break
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status != 429 and status < 500:
                    break
            except ValueError as exc:
                last_error = exc
                break
            if attempt < 2:
                await asyncio.sleep(0.2 * (2**attempt))
        if body is None:
            raise MedAngelUnavailable("MIS временно недоступна") from last_error
        items = (
            body.get("items", body.get("data", body))
            if isinstance(body, dict)
            else body
        )
        if not isinstance(items, list):
            raise MedAngelUnavailable("MIS вернула некорректную схему")
        valid_items = [item for item in items if isinstance(item, dict)]
        self._cache[cache_key] = (time.monotonic() + ttl, valid_items)
        return valid_items

    async def search_services(self, query: str) -> list[Service]:
        items = await self._get(self.services_path, {"query": query}, self.catalog_ttl)
        result = []
        for item in items[:5]:
            entity_id = item.get("id") or item.get("service_id")
            title = item.get("title") or item.get("name")
            if entity_id is None or not title:
                continue
            price = item.get("price")
            result.append(
                Service(
                    id=str(entity_id),
                    title=str(title),
                    description=str(item.get("description", "")),
                    price=str(price) if price is not None else None,
                    branch_id=(
                        str(item["branch_id"])
                        if item.get("branch_id") is not None
                        else None
                    ),
                    updated_at=item.get("updated_at"),
                )
            )
        return result

    async def doctors(
        self, service_id: str, branch_id: str | None = None
    ) -> list[Doctor]:
        params = {"service_id": service_id}
        if branch_id:
            params["branch_id"] = branch_id
        items = await self._get(self.doctors_path, params, self.catalog_ttl)
        result = []
        for item in items[:5]:
            entity_id = item.get("id") or item.get("doctor_id")
            title = item.get("title") or item.get("name")
            if entity_id is None or not title:
                continue
            result.append(
                Doctor(
                    id=str(entity_id),
                    title=str(title),
                    specialty=str(item.get("specialty", "")),
                    branch_id=(
                        str(item["branch_id"])
                        if item.get("branch_id") is not None
                        else branch_id
                    ),
                    service_id=service_id,
                )
            )
        return result

    async def slots(
        self,
        service_id: str,
        doctor_id: str | None = None,
        branch_id: str | None = None,
    ) -> list[Slot]:
        params = {"service_id": service_id}
        if doctor_id:
            params["doctor_id"] = doctor_id
        if branch_id:
            params["branch_id"] = branch_id
        items = await self._get(self.slots_path, params, self.slots_ttl)
        result = []
        for item in items[:8]:
            entity_id = item.get("id") or item.get("slot_id")
            starts_at = item.get("starts_at") or item.get("start")
            item_doctor = item.get("doctor_id") or doctor_id
            if entity_id is None or not starts_at or item_doctor is None:
                continue
            result.append(
                Slot(
                    id=str(entity_id),
                    starts_at=str(starts_at),
                    doctor_id=str(item_doctor),
                    service_id=service_id,
                    branch_id=(
                        str(item["branch_id"])
                        if item.get("branch_id") is not None
                        else branch_id
                    ),
                )
            )
        return result

    async def validate_service(self, service_id: str) -> Service | None:
        services = await self.search_services(service_id)
        return next((item for item in services if item.id == service_id), None)

    async def validate_doctor(self, doctor_id: str, service_id: str) -> Doctor | None:
        doctors = await self.doctors(service_id)
        return next((item for item in doctors if item.id == doctor_id), None)

    async def validate_slot(self, slot_id: str, service_id: str) -> Slot | None:
        slots = await self.slots(service_id)
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
            response = await self.http.get(f"{self.base_url}/health")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self.http.aclose()
