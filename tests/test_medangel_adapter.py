from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Callable

import httpx
import pytest

from app.adapters.medangel import MedAngelAdapter
from app.adapters.mis_cache import InMemoryMISResponseCache, RedisMISResponseCache
from app.ports import MedAngelUnavailable


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    cache: InMemoryMISResponseCache | None = None,
    max_response_bytes: int = 2_000_000,
) -> tuple[MedAngelAdapter, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=1,
    )
    return (
        MedAngelAdapter(
            "https://mis.example.test",
            "secret",
            "/services",
            "/doctors",
            "/schedule",
            "https://vodc.ru/appointment/",
            1,
            300,
            30,
            max_response_bytes=max_response_bytes,
            cache=cache,
            http_client=client,
        ),
        client,
    )


def test_http_client_cannot_log_the_service_query_at_info():
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


@pytest.mark.asyncio
async def test_service_mapping_uses_bearer_auth_and_hashed_cache_key():
    requests: list[httpx.Request] = []
    cache = InMemoryMISResponseCache()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "service_id": 42,
                        "name": "МРТ",
                        "description": "Исследование",
                        "price": 3000,
                        "branch_id": "branch-1",
                        "echo": "МРТ головного мозга",
                    }
                ]
            },
        )

    adapter, client = _adapter(handler, cache=cache)
    try:
        first = await adapter.search_services("МРТ головного мозга")
        second = await adapter.search_services("МРТ головного мозга")
        cache_keys = list(cache._items)
        cache_payloads = [payload for _, payload in cache._items.values()]
    finally:
        await adapter.close()
        await client.aclose()

    assert first == second
    assert first[0].id == "42"
    assert first[0].price == "3000"
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer secret"
    assert len(cache_keys) == 1
    assert all("МРТ" not in key for key in cache_keys)
    assert all("echo" not in payload for payload in cache_payloads)
    assert all("головного мозга" not in payload for payload in cache_payloads)


@pytest.mark.asyncio
async def test_parallel_identical_requests_are_single_flight():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=[{"id": "1", "title": "Услуга"}])

    adapter, client = _adapter(handler)
    try:
        results = await asyncio.gather(
            adapter.search_services("МРТ"),
            adapter.search_services("МРТ"),
        )
    finally:
        await adapter.close()
        await client.aclose()

    assert results[0] == results[1]
    assert calls == 1


@pytest.mark.asyncio
async def test_live_slot_validation_bypasses_cached_schedule():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        items = (
            [
                {
                    "id": "slot-1",
                    "starts_at": "2026-08-01T07:00:00Z",
                    "doctor_id": "doctor-1",
                    "service_id": "service-1",
                    "branch_id": "branch-1",
                }
            ]
            if calls == 1
            else []
        )
        return httpx.Response(200, json={"items": items})

    adapter, client = _adapter(handler)
    try:
        cached = await adapter.slots(
            "service-1", "doctor-1", "branch-1"
        )
        live = await adapter.validate_slot(
            "slot-1", "service-1", "doctor-1", "branch-1"
        )
    finally:
        await adapter.close()
        await client.aclose()

    assert cached[0].starts_at == "2026-08-01T10:00:00+03:00"
    assert live is None
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"items": [{"id": "slot-1", "starts_at": "2026-08-01T10:00:00"}]},
        {
            "items": [
                {
                    "id": "slot-1",
                    "starts_at": "2026-08-01T10:00:00+03:00",
                    "doctor_id": "wrong-doctor",
                }
            ]
        },
        {
            "items": [
                {
                    "id": "slot-1",
                    "starts_at": "2026-08-01T10:00:00+03:00",
                    "doctor_id": "doctor-1",
                    "service_id": "wrong-service",
                }
            ]
        },
    ],
)
async def test_slot_schema_and_relationship_mismatches_fail_closed(payload):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(MedAngelUnavailable, match="некорректную схему"):
            await adapter.slots("service-1", "doctor-1", "branch-1")
    finally:
        await adapter.close()
        await client.aclose()


@pytest.mark.asyncio
async def test_conflicting_duplicate_identifiers_fail_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"id": "service-1", "title": "МРТ"},
                {"id": "service-1", "title": "КТ"},
            ],
        )

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(MedAngelUnavailable, match="некорректную схему"):
            await adapter.search_services("томография")
    finally:
        await adapter.close()
        await client.aclose()


@pytest.mark.asyncio
async def test_unauthorized_response_is_not_retried():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(MedAngelUnavailable):
            await adapter.search_services("МРТ")
    finally:
        await adapter.close()
        await client.aclose()

    assert calls == 1


@pytest.mark.asyncio
async def test_transient_server_error_is_retried():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json=[{"id": "1", "title": "МРТ"}])

    adapter, client = _adapter(handler)
    try:
        services = await adapter.search_services("МРТ")
    finally:
        await adapter.close()
        await client.aclose()

    assert services[0].id == "1"
    assert calls == 2


@pytest.mark.asyncio
async def test_malformed_envelope_fails_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []})

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(MedAngelUnavailable):
            await adapter.search_services("МРТ")
    finally:
        await adapter.close()
        await client.aclose()


@pytest.mark.asyncio
async def test_oversized_response_is_rejected_before_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"id": "1", "title": "x" * 100}],
        )

    adapter, client = _adapter(handler, max_response_bytes=32)
    try:
        with pytest.raises(MedAngelUnavailable):
            await adapter.search_services("МРТ")
    finally:
        await adapter.close()
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"),
    reason="real Redis integration is enabled in CI",
)
async def test_redis_mis_cache_is_shared_between_adapter_instances():
    prefix = f"vodc:test:mis:{uuid.uuid4()}"
    first = RedisMISResponseCache(os.environ["TEST_REDIS_URL"], prefix)
    second = RedisMISResponseCache(os.environ["TEST_REDIS_URL"], prefix)
    try:
        await first.set("shared-key", [{"id": "service-1"}], 2)
        assert await second.get("shared-key") == [{"id": "service-1"}]
    finally:
        await first.redis.delete(first._key("shared-key"))
        await first.close()
        await second.close()
