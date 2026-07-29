from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..domain.models import ChatSession


class InMemorySessionStore:
    """Development/test fallback with the same TTL semantics as Redis."""

    def __init__(self, ttl_seconds: int, max_sessions: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, tuple[float, ChatSession]] = {}
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def create(self, session: ChatSession) -> None:
        await self.save(session)

    async def get(self, session_id: str) -> ChatSession | None:
        async with self._lock:
            item = self._sessions.get(session_id)
            if not item:
                return None
            expires_at, session = item
            if expires_at <= time.monotonic():
                self._sessions.pop(session_id, None)
                return None
            self._sessions[session_id] = (
                time.monotonic() + self.ttl_seconds,
                session,
            )
            return ChatSession.from_dict(session.to_dict())

    async def save(self, session: ChatSession) -> None:
        async with self._lock:
            now = time.monotonic()
            expired = [
                key for key, (expiry, _) in self._sessions.items() if expiry <= now
            ]
            for key in expired:
                self._sessions.pop(key, None)
            if (
                session.id not in self._sessions
                and len(self._sessions) >= self.max_sessions
            ):
                oldest = min(self._sessions, key=lambda key: self._sessions[key][0])
                self._sessions.pop(oldest, None)
            self._sessions[session.id] = (
                now + self.ttl_seconds,
                ChatSession.from_dict(session.to_dict()),
            )

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def allow_request(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        async with self._lock:
            events = self._requests[key]
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class RedisSessionStore:
    def __init__(self, url: str, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self.redis = Redis.from_url(url, decode_responses=True)

    def _key(self, session_id: str) -> str:
        return f"vodc:session:{session_id}"

    async def create(self, session: ChatSession) -> None:
        await self.save(session)

    async def get(self, session_id: str) -> ChatSession | None:
        key = self._key(session_id)
        value = await self.redis.get(key)
        if value is None:
            return None
        await self.redis.expire(key, self.ttl_seconds)
        return ChatSession.from_dict(json.loads(value))

    async def save(self, session: ChatSession) -> None:
        await self.redis.set(
            self._key(session.id),
            json.dumps(session.to_dict(), ensure_ascii=False),
            ex=self.ttl_seconds,
        )

    async def delete(self, session_id: str) -> None:
        await self.redis.delete(self._key(session_id))

    async def allow_request(self, key: str, limit: int, window: int) -> bool:
        redis_key = f"vodc:rate:{key}:{int(time.time()) // window}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, window + 1)
            count, _ = await pipe.execute()
        return int(count) <= limit

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except (OSError, RedisError):
            return False

    async def close(self) -> None:
        await self.redis.aclose()
