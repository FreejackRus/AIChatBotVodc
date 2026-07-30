from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any, Protocol

import redis.asyncio as redis

logger = logging.getLogger("vodc_chat.mis_cache")


class MISResponseCache(Protocol):
    async def get(self, key: str) -> list[dict[str, Any]] | None: ...
    async def set(
        self, key: str, value: list[dict[str, Any]], ttl_seconds: int
    ) -> None: ...
    async def close(self) -> None: ...


def _decode_items(payload: str | bytes) -> list[dict[str, Any]] | None:
    try:
        value = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        return None
    return [dict(item) for item in value]


class InMemoryMISResponseCache:
    """Bounded development cache; production workers use Redis."""

    def __init__(self, max_entries: int = 512):
        self.max_entries = max_entries
        self._items: OrderedDict[str, tuple[float, str]] = OrderedDict()

    async def get(self, key: str) -> list[dict[str, Any]] | None:
        cached = self._items.get(key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        decoded = _decode_items(payload)
        if decoded is None:
            self._items.pop(key, None)
        return decoded

    async def set(
        self, key: str, value: list[dict[str, Any]], ttl_seconds: int
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        self._items[key] = (time.monotonic() + ttl_seconds, payload)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    async def close(self) -> None:
        self._items.clear()


class RedisMISResponseCache:
    """Shared best-effort cache that never makes MIS unavailable by itself."""

    def __init__(self, redis_url: str, prefix: str = "vodc:mis:v1"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> list[dict[str, Any]] | None:
        try:
            payload = await self.redis.get(self._key(key))
        except redis.RedisError:
            logger.warning("MIS Redis cache read failed", exc_info=True)
            return None
        if payload is None:
            return None
        decoded = _decode_items(payload)
        if decoded is None:
            try:
                await self.redis.delete(self._key(key))
            except redis.RedisError:
                logger.warning("MIS Redis cache cleanup failed", exc_info=True)
        return decoded

    async def set(
        self, key: str, value: list[dict[str, Any]], ttl_seconds: int
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        try:
            await self.redis.set(self._key(key), payload, ex=ttl_seconds)
        except redis.RedisError:
            logger.warning("MIS Redis cache write failed", exc_info=True)

    async def close(self) -> None:
        await self.redis.aclose()
