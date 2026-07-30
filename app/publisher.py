"""Controlled activation and rollback of approved staged RAG sources."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import asyncpg
import httpx

from .domain.safety import contains_prompt_injection
from .ingestion import chunk_text
from .source_staging import PRICE_RE


class PublicationError(RuntimeError):
    """An approved version cannot be safely published or rolled back."""


@dataclass(frozen=True, slots=True)
class PublicationCandidate:
    version_id: uuid.UUID
    candidate_id: uuid.UUID
    url: str
    title: str
    owner: str
    risk_tier: str
    sections: tuple[dict[str, str], ...]
    content_hash: str
    reviewed_at: date
    reviewer_role: str
    manual_conflict: bool
    snapshot_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class PreparedPublication:
    candidate: PublicationCandidate
    snapshot_id: uuid.UUID
    chunks: tuple[str, ...]
    embeddings: tuple[tuple[float, ...], ...]
    existing_snapshot: bool


def semantic_chunks(
    title: str,
    sections: tuple[dict[str, str], ...],
    *,
    chunk_size: int,
    overlap: int,
) -> tuple[str, ...]:
    result: list[str] = []
    for section in sections:
        heading = str(section.get("heading", "")).strip() or title
        content = str(section.get("content", "")).strip()
        if not content:
            continue
        text = f"# {title}\n\n## {heading}\n{content}"
        result.extend(chunk_text(text, chunk_size, overlap))
    if not result:
        raise PublicationError("Утверждённая версия не содержит секций")
    for item in result:
        if contains_prompt_injection(item):
            raise PublicationError("Chunk содержит prompt injection")
        if PRICE_RE.search(item):
            raise PublicationError("Chunk содержит динамическую цену")
    return tuple(result)


def _vector(values: tuple[float, ...]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


class ControlledPublisher:
    def __init__(
        self,
        database_url: str,
        embedding_base_url: str,
        embedding_model: str,
        embedding_revision: str,
        embedding_dimensions: int,
        embedding_batch_size: int,
        *,
        timeout: float,
        chunk_size: int,
        chunk_overlap: int,
        source_max_age_days: int,
    ) -> None:
        self.database_url = database_url
        self.embedding_base_url = embedding_base_url
        self.embedding_model = embedding_model
        self.embedding_revision = embedding_revision
        self.embedding_dimensions = embedding_dimensions
        self.embedding_batch_size = embedding_batch_size
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.source_max_age_days = source_max_age_days
        self.http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self.http.aclose()

    async def plan(self, limit: int) -> tuple[PublicationCandidate, ...]:
        pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=2)
        try:
            rows = await pool.fetch(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (v.candidate_id)
                           v.id, v.candidate_id, v.content_hash, v.title,
                           v.sections, v.fetched_at,
                           c.url, c.owner, c.risk_tier
                    FROM source_versions v
                    JOIN source_candidates c ON c.id = v.candidate_id
                    WHERE v.review_status = 'approved' AND c.enabled = true
                    ORDER BY v.candidate_id, v.fetched_at DESC
                ),
                reviews AS (
                    SELECT DISTINCT ON (r.version_id)
                           r.version_id, r.reviewer_role,
                           r.reviewed_at::date AS reviewed_at
                    FROM source_version_reviews r
                    WHERE r.decision = 'approved'
                    ORDER BY r.version_id, r.reviewed_at DESC
                )
                SELECT l.*, r.reviewer_role, r.reviewed_at,
                       s.id AS snapshot_id,
                       COALESCE(k.origin = 'manual', false) AS manual_conflict,
                       a.snapshot_id AS active_snapshot_id
                FROM latest l
                JOIN reviews r ON r.version_id = l.id
                LEFT JOIN knowledge_source_snapshots s
                    ON s.source_version_id = l.id
                   AND s.embedding_model = $2
                   AND s.embedding_revision = $3
                   AND s.embedding_dimensions = $4
                   AND s.chunk_size = $5
                   AND s.chunk_overlap = $6
                LEFT JOIN knowledge_sources k ON k.url = l.url
                LEFT JOIN knowledge_source_activations a ON a.source_id = k.id
                WHERE s.id IS NULL OR a.snapshot_id IS DISTINCT FROM s.id
                ORDER BY l.risk_tier DESC, l.fetched_at, l.url
                LIMIT $1
                """,
                limit,
                self.embedding_model,
                self.embedding_revision,
                self.embedding_dimensions,
                self.chunk_size,
                self.chunk_overlap,
            )
            result = []
            for row in rows:
                sections_value: Any = row["sections"]
                if isinstance(sections_value, str):
                    sections_value = json.loads(sections_value)
                if not isinstance(sections_value, list):
                    raise PublicationError("sections имеет некорректную схему")
                sections = tuple(
                    {
                        "heading": str(item.get("heading", "")),
                        "content": str(item.get("content", "")),
                    }
                    for item in sections_value
                    if isinstance(item, dict)
                )
                reviewer_role = row["reviewer_role"]
                if row["risk_tier"] == "medical" and reviewer_role != "medical_owner":
                    raise PublicationError(
                        "Medical source не имеет medical_owner approval"
                    )
                result.append(
                    PublicationCandidate(
                        version_id=row["id"],
                        candidate_id=row["candidate_id"],
                        url=row["url"],
                        title=row["title"],
                        owner=row["owner"],
                        risk_tier=row["risk_tier"],
                        sections=sections,
                        content_hash=row["content_hash"],
                        reviewed_at=row["reviewed_at"],
                        reviewer_role=reviewer_role,
                        manual_conflict=row["manual_conflict"],
                        snapshot_id=row["snapshot_id"],
                    )
                )
            return tuple(result)
        finally:
            await pool.close()

    async def _embeddings(
        self, texts: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]:
        result: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self.embedding_batch_size):
            batch = texts[start : start + self.embedding_batch_size]
            response = await self.http.post(
                f"{self.embedding_base_url}/v1/embeddings",
                json={"model": self.embedding_model, "input": list(batch)},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(rows, list) or len(rows) != len(batch):
                raise PublicationError("Embedding API вернул неверное число векторов")
            try:
                ordered = sorted(rows, key=lambda row: int(row["index"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise PublicationError("Embedding API вернул неверные индексы") from exc
            if [int(row["index"]) for row in ordered] != list(range(len(batch))):
                raise PublicationError("Embedding API вернул дублированные индексы")
            for row in ordered:
                values = row.get("embedding") if isinstance(row, dict) else None
                if not isinstance(values, list):
                    raise PublicationError("Embedding API вернул неверный вектор")
                vector = tuple(float(value) for value in values)
                if (
                    len(vector) != self.embedding_dimensions
                    or not all(math.isfinite(value) for value in vector)
                ):
                    raise PublicationError("Embedding не соответствует контракту")
                result.append(vector)
        return tuple(result)

    async def prepare(
        self, candidates: tuple[PublicationCandidate, ...]
    ) -> tuple[PreparedPublication, ...]:
        result = []
        for candidate in candidates:
            if candidate.manual_conflict:
                continue
            snapshot_id = candidate.snapshot_id or uuid.uuid5(
                candidate.version_id,
                (
                    f"{self.embedding_model}:{self.embedding_revision}:"
                    f"{self.chunk_size}:{self.chunk_overlap}"
                ),
            )
            if candidate.snapshot_id:
                result.append(
                    PreparedPublication(candidate, snapshot_id, (), (), True)
                )
                continue
            chunks = semantic_chunks(
                candidate.title,
                candidate.sections,
                chunk_size=self.chunk_size,
                overlap=self.chunk_overlap,
            )
            embeddings = await self._embeddings(chunks)
            result.append(
                PreparedPublication(
                    candidate,
                    snapshot_id,
                    chunks,
                    embeddings,
                    False,
                )
            )
        return tuple(result)

    async def publish(
        self,
        prepared: tuple[PreparedPublication, ...],
        *,
        actor: str,
        blocked: int,
    ) -> dict[str, int | str]:
        if not prepared:
            return {"published": 0, "blocked": blocked, "run_id": ""}
        run_id = uuid.uuid4()
        pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=2)
        try:
            async with pool.acquire() as connection, connection.transaction():
                for item in prepared:
                    candidate = item.candidate
                    source_id = uuid.uuid5(uuid.NAMESPACE_URL, candidate.url)
                    existing = await connection.fetchrow(
                        "SELECT origin FROM knowledge_sources WHERE url = $1 FOR UPDATE",
                        candidate.url,
                    )
                    if existing and existing["origin"] == "manual":
                        raise PublicationError(
                            f"Manual source нельзя перезаписать: {candidate.url}"
                        )
                    if not item.existing_snapshot:
                        await connection.execute(
                            """
                            INSERT INTO knowledge_source_snapshots
                                (id, source_version_id, candidate_id, url, title,
                                 owner, reviewed_at, content_hash, embedding_model,
                                 embedding_revision, embedding_dimensions,
                                 chunk_size, chunk_overlap)
                            VALUES
                                ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                                 $11, $12, $13)
                            """,
                            item.snapshot_id,
                            candidate.version_id,
                            candidate.candidate_id,
                            candidate.url,
                            candidate.title,
                            candidate.owner,
                            candidate.reviewed_at,
                            candidate.content_hash,
                            self.embedding_model,
                            self.embedding_revision,
                            self.embedding_dimensions,
                            self.chunk_size,
                            self.chunk_overlap,
                        )
                        await connection.executemany(
                            """
                            INSERT INTO knowledge_snapshot_chunks
                                (snapshot_id, position, content, content_hash, embedding)
                            VALUES ($1, $2, $3, $4, $5::vector)
                            """,
                            [
                                (
                                    item.snapshot_id,
                                    position,
                                    chunk,
                                    hashlib.sha256(chunk.encode()).hexdigest(),
                                    _vector(embedding),
                                )
                                for position, (chunk, embedding) in enumerate(
                                    zip(item.chunks, item.embeddings, strict=True)
                                )
                            ],
                        )
                    previous = await connection.fetchval(
                        """
                        SELECT snapshot_id FROM knowledge_source_activations
                        WHERE source_id = $1
                        """,
                        source_id,
                    )
                    expiry = datetime.combine(
                        candidate.reviewed_at
                        + timedelta(days=self.source_max_age_days),
                        time.max,
                        UTC,
                    )
                    await connection.execute(
                        """
                        INSERT INTO knowledge_sources
                            (id, filename, title, url, owner, reviewed_at,
                             expires_at, content_hash, enabled, indexed_at,
                             embedding_model, embedding_dimensions,
                             embedding_revision, chunk_size, chunk_overlap,
                             last_checked_at, origin, source_version_id)
                        VALUES
                            ($1, $2, $3, $4, $5, $6, $7, $8, true, now(),
                             $9, $10, $11, $12, $13, now(), 'staged', $14)
                        ON CONFLICT (url) DO UPDATE SET
                            title = excluded.title,
                            owner = excluded.owner,
                            reviewed_at = excluded.reviewed_at,
                            expires_at = excluded.expires_at,
                            content_hash = excluded.content_hash,
                            enabled = true,
                            indexed_at = now(),
                            embedding_model = excluded.embedding_model,
                            embedding_dimensions = excluded.embedding_dimensions,
                            embedding_revision = excluded.embedding_revision,
                            chunk_size = excluded.chunk_size,
                            chunk_overlap = excluded.chunk_overlap,
                            last_checked_at = now(),
                            origin = 'staged',
                            source_version_id = excluded.source_version_id
                        """,
                        source_id,
                        f"staged-{candidate.candidate_id}.md",
                        candidate.title,
                        candidate.url,
                        candidate.owner,
                        candidate.reviewed_at,
                        expiry,
                        candidate.content_hash,
                        self.embedding_model,
                        self.embedding_dimensions,
                        self.embedding_revision,
                        self.chunk_size,
                        self.chunk_overlap,
                        candidate.version_id,
                    )
                    await connection.execute(
                        "DELETE FROM knowledge_chunks WHERE source_id = $1",
                        source_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO knowledge_chunks
                            (source_id, position, content, content_hash, embedding)
                        SELECT $1, position, content, content_hash, embedding
                        FROM knowledge_snapshot_chunks
                        WHERE snapshot_id = $2
                        ORDER BY position
                        """,
                        source_id,
                        item.snapshot_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO knowledge_source_activations
                            (source_id, snapshot_id, activated_at)
                        VALUES ($1, $2, now())
                        ON CONFLICT (source_id) DO UPDATE SET
                            snapshot_id = excluded.snapshot_id,
                            activated_at = excluded.activated_at
                        """,
                        source_id,
                        item.snapshot_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO knowledge_publication_events
                            (run_id, source_id, previous_snapshot_id, snapshot_id)
                        VALUES ($1, $2, $3, $4)
                        """,
                        run_id,
                        source_id,
                        previous,
                        item.snapshot_id,
                    )
                stats = {"published": len(prepared), "blocked": blocked}
                await connection.execute(
                    """
                    INSERT INTO knowledge_publication_runs
                        (id, action, status, actor, stats)
                    VALUES ($1, 'publish', 'success', $2, $3::jsonb)
                    """,
                    run_id,
                    actor,
                    json.dumps(stats, ensure_ascii=False),
                )
            return {"run_id": str(run_id), **stats}
        finally:
            await pool.close()

    async def rollback(
        self,
        url: str,
        *,
        actor: str,
        snapshot_id: uuid.UUID | None = None,
    ) -> dict[str, str]:
        run_id = uuid.uuid4()
        source_id = uuid.uuid5(uuid.NAMESPACE_URL, url)
        pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=2)
        try:
            async with pool.acquire() as connection, connection.transaction():
                current = await connection.fetchval(
                    """
                    SELECT snapshot_id FROM knowledge_source_activations
                    WHERE source_id = $1
                    """,
                    source_id,
                )
                if current is None:
                    raise PublicationError("Для URL нет активного staged snapshot")
                target = snapshot_id
                if target is None:
                    target = await connection.fetchval(
                        """
                        SELECT previous_snapshot_id
                        FROM knowledge_publication_events
                        WHERE source_id = $1
                          AND snapshot_id = $2
                          AND previous_snapshot_id IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        source_id,
                        current,
                    )
                snapshot = await connection.fetchrow(
                    """
                    SELECT s.*, v.id AS version_id
                    FROM knowledge_source_snapshots s
                    JOIN source_versions v ON v.id = s.source_version_id
                    WHERE s.id = $1 AND s.url = $2
                    """,
                    target,
                    url,
                )
                if snapshot is None:
                    raise PublicationError("Rollback snapshot не найден для URL")
                expiry = datetime.combine(
                    snapshot["reviewed_at"]
                    + timedelta(days=self.source_max_age_days),
                    time.max,
                    UTC,
                )
                await connection.execute(
                    "DELETE FROM knowledge_chunks WHERE source_id = $1",
                    source_id,
                )
                await connection.execute(
                    """
                    INSERT INTO knowledge_chunks
                        (source_id, position, content, content_hash, embedding)
                    SELECT $1, position, content, content_hash, embedding
                    FROM knowledge_snapshot_chunks
                    WHERE snapshot_id = $2
                    """,
                    source_id,
                    target,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_sources
                    SET title = $2, owner = $3, reviewed_at = $4,
                        content_hash = $5, embedding_model = $6,
                        embedding_revision = $7, embedding_dimensions = $8,
                        chunk_size = $9, chunk_overlap = $10,
                        source_version_id = $11, expires_at = $12, indexed_at = now(),
                        last_checked_at = now(), enabled = true
                    WHERE id = $1 AND origin = 'staged'
                    """,
                    source_id,
                    snapshot["title"],
                    snapshot["owner"],
                    snapshot["reviewed_at"],
                    snapshot["content_hash"],
                    snapshot["embedding_model"],
                    snapshot["embedding_revision"],
                    snapshot["embedding_dimensions"],
                    snapshot["chunk_size"],
                    snapshot["chunk_overlap"],
                    snapshot["version_id"],
                    expiry,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_source_activations
                    SET snapshot_id = $2, activated_at = now()
                    WHERE source_id = $1
                    """,
                    source_id,
                    target,
                )
                await connection.execute(
                    """
                    INSERT INTO knowledge_publication_runs
                        (id, action, status, actor, stats)
                    VALUES ($1, 'rollback', 'success', $2, $3::jsonb)
                    """,
                    run_id,
                    actor,
                    json.dumps(
                        {"url": url, "from": str(current), "to": str(target)}
                    ),
                )
                await connection.execute(
                    """
                    INSERT INTO knowledge_publication_events
                        (run_id, source_id, previous_snapshot_id, snapshot_id)
                    VALUES ($1, $2, $3, $4)
                    """,
                    run_id,
                    source_id,
                    current,
                    target,
                )
            return {"run_id": str(run_id), "snapshot_id": str(target)}
        finally:
            await pool.close()
