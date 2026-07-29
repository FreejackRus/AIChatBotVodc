from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg


class InMemoryEventStore:
    def __init__(self):
        self.messages: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def record_message(
        self,
        session_id: str,
        role: str,
        redacted_text: str,
        categories: tuple[str, ...],
    ) -> None:
        self.messages.append(
            {
                "session_id": session_id,
                "role": role,
                "text": redacted_text,
                "categories": list(categories),
                "created_at": datetime.now(timezone.utc),
            }
        )

    async def record_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.events.append(
            {
                "session_id": session_id,
                "event_type": event_type,
                "payload": payload,
                "created_at": datetime.now(timezone.utc),
            }
        )

    async def cleanup(self, retention_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        before = len(self.messages) + len(self.events)
        self.messages = [item for item in self.messages if item["created_at"] >= cutoff]
        self.events = [item for item in self.events if item["created_at"] >= cutoff]
        return before - len(self.messages) - len(self.events)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class PostgresEventStore:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None

    async def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.database_url, min_size=1, max_size=5
            )
        return self.pool

    async def record_message(
        self,
        session_id: str,
        role: str,
        redacted_text: str,
        categories: tuple[str, ...],
    ) -> None:
        pool = await self._pool()
        await pool.execute(
            """
            INSERT INTO redacted_messages
                (session_id, role, redacted_text, redaction_categories)
            VALUES ($1::uuid, $2, $3, $4::text[])
            """,
            session_id,
            role,
            redacted_text,
            list(categories),
        )

    async def record_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        pool = await self._pool()
        await pool.execute(
            """
            INSERT INTO funnel_events (session_id, event_type, payload)
            VALUES ($1::uuid, $2, $3::jsonb)
            """,
            session_id,
            event_type,
            json.dumps(payload, ensure_ascii=False),
        )

    async def cleanup(self, retention_days: int) -> int:
        pool = await self._pool()
        message_result = await pool.execute(
            """
            DELETE FROM redacted_messages
            WHERE created_at < now() - make_interval(days => $1::int)
            """,
            retention_days,
        )
        event_result = await pool.execute(
            """
            DELETE FROM funnel_events
            WHERE created_at < now() - make_interval(days => $1::int)
            """,
            retention_days,
        )
        return int(message_result.split()[-1]) + int(event_result.split()[-1])

    async def ping(self) -> bool:
        try:
            pool = await self._pool()
            return bool(await pool.fetchval("SELECT true"))
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError):
            return False

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
