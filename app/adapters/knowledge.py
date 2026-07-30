from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from ..domain.models import SourceRef
from ..domain.safety import contains_prompt_injection
from ..ingestion import ManifestSource, chunk_text, load_manifest
from ..metrics import RAG_SEARCH_SECONDS, RAG_SEARCHES
from ..ports import KnowledgeUnavailable

QUERY_INSTRUCTION = (
    "Instruct: Given a Russian-language website query, retrieve approved "
    "VODC passages that answer the query.\nQuery: "
)
STOP_WORDS = {
    "для",
    "или",
    "как",
    "что",
    "это",
    "при",
    "где",
    "когда",
    "какой",
    "какая",
    "какие",
}


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zа-яё0-9]{3,}", text.lower())
        if token not in STOP_WORDS
    }


@dataclass(frozen=True, slots=True)
class LocalChunk:
    source: ManifestSource
    position: int
    content: str


class LocalKnowledgeAdapter:
    """Read-only lexical fallback over approved local snapshots."""

    def __init__(
        self,
        manifest_path: Path,
        chunk_size: int,
        overlap: int,
        source_max_age_days: int,
        source_max_bytes: int,
        excerpt_chars: int,
    ):
        self.excerpt_chars = excerpt_chars
        self.source_max_age_days = source_max_age_days
        root = manifest_path.parent.resolve()
        chunks: list[LocalChunk] = []
        for source in load_manifest(manifest_path):
            if not source.active(source_max_age_days) or not source.local_path:
                continue
            path = (root / source.local_path).resolve()
            if root != path.parent and root not in path.parents:
                raise ValueError("local_path выходит за пределы каталога реестра")
            if not path.is_file():
                raise ValueError(f"Локальный snapshot отсутствует: {source.local_path}")
            if path.stat().st_size > source_max_bytes:
                raise ValueError(f"Источник {source.filename} превышает лимит размера")
            source_content = path.read_text(encoding="utf-8")
            if contains_prompt_injection(source_content):
                raise ValueError(
                    f"Источник {source.filename} содержит инструкции для модели"
                )
            for position, chunk in enumerate(
                chunk_text(source_content, chunk_size, overlap)
            ):
                chunks.append(LocalChunk(source, position, chunk))
        self.chunks = tuple(chunks)

    async def search(self, query: str, limit: int) -> list[SourceRef]:
        started = time.perf_counter()
        query_terms = _terms(query)
        query_normalized = " ".join(query.lower().split())
        ranked: list[tuple[float, LocalChunk]] = []
        for chunk in self.chunks:
            if not chunk.source.active(self.source_max_age_days):
                continue
            content_terms = _terms(chunk.content)
            title_terms = _terms(chunk.source.title)
            overlap = query_terms & content_terms
            if not overlap:
                continue
            coverage = len(overlap) / max(1, len(query_terms))
            title_coverage = len(query_terms & title_terms) / max(1, len(query_terms))
            phrase = 1.0 if query_normalized in chunk.content.lower() else 0.0
            score = 0.75 * coverage + 0.15 * title_coverage + 0.1 * phrase
            ranked.append((score, chunk))
        ranked.sort(
            key=lambda item: (
                -item[0],
                item[1].source.filename,
                item[1].position,
            )
        )
        result = [
            SourceRef(
                id=f"{chunk.source.filename}:{chunk.position}",
                title=chunk.source.title,
                url=chunk.source.url,
                excerpt=chunk.content[: self.excerpt_chars],
                reviewed_at=chunk.source.reviewed_at.isoformat(),
                score=round(score, 6),
            )
            for score, chunk in ranked[:limit]
        ]
        RAG_SEARCHES.labels("hit" if result else "empty").inc()
        RAG_SEARCH_SECONDS.observe(time.perf_counter() - started)
        return result

    async def ping(self) -> bool:
        return any(
            chunk.source.active(self.source_max_age_days) for chunk in self.chunks
        )

    async def close(self) -> None:
        return None


class PostgresKnowledgeAdapter:
    def __init__(
        self,
        database_url: str,
        embedding_base_url: str,
        embedding_model: str,
        embedding_revision: str,
        embedding_dimensions: int,
        timeout: float,
        dense_weight: float,
        min_score: float,
        candidate_multiplier: int,
        source_max_age_days: int,
        excerpt_chars: int,
    ):
        self.database_url = database_url
        self.embedding_base_url = embedding_base_url
        self.embedding_model = embedding_model
        self.embedding_revision = embedding_revision
        self.embedding_dimensions = embedding_dimensions
        self.timeout = timeout
        self.dense_weight = dense_weight
        self.min_score = min_score
        self.candidate_multiplier = candidate_multiplier
        self.source_max_age_days = source_max_age_days
        self.excerpt_chars = excerpt_chars
        self.pool: asyncpg.Pool | None = None
        self.http = httpx.AsyncClient(timeout=timeout)

    async def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.database_url, min_size=1, max_size=5
            )
        return self.pool

    async def _embedding(self, text: str) -> tuple[float, ...]:
        response = await self.http.post(
            f"{self.embedding_base_url}/v1/embeddings",
            json={
                "model": self.embedding_model,
                "input": QUERY_INSTRUCTION + text.strip(),
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        values = data["data"][0]["embedding"]
        vector = tuple(float(value) for value in values)
        if len(vector) != self.embedding_dimensions:
            raise ValueError(
                f"Embedding query dimension {len(vector)} "
                f"!= {self.embedding_dimensions}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding query contains NaN or Infinity")
        return vector

    async def search(self, query: str, limit: int) -> list[SourceRef]:
        started = time.perf_counter()
        try:
            embedding = await self._embedding(query)
            vector = "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
            candidate_limit = max(limit, limit * self.candidate_multiplier)
            pool = await self._pool()
            rows = await pool.fetch(
                """
                WITH dense AS (
                    SELECT c.id
                    FROM knowledge_chunks c
                    JOIN knowledge_sources s ON s.id = c.source_id
                    WHERE s.enabled = true
                      AND s.reviewed_at >= current_date - $7::integer
                      AND (s.expires_at IS NULL OR s.expires_at > now())
                      AND s.embedding_model = $8
                      AND s.embedding_dimensions = $9
                      AND s.embedding_revision = $10
                    ORDER BY c.embedding <=> $1::vector
                    LIMIT $4
                ),
                lexical AS (
                    SELECT c.id
                    FROM knowledge_chunks c
                    JOIN knowledge_sources s ON s.id = c.source_id
                    WHERE s.enabled = true
                      AND s.reviewed_at >= current_date - $7::integer
                      AND (s.expires_at IS NULL OR s.expires_at > now())
                      AND s.embedding_model = $8
                      AND s.embedding_dimensions = $9
                      AND s.embedding_revision = $10
                      AND c.search_vector @@ plainto_tsquery('russian', $2)
                    ORDER BY ts_rank_cd(
                        c.search_vector, plainto_tsquery('russian', $2)
                    ) DESC
                    LIMIT $4
                ),
                candidates AS (
                    SELECT id FROM dense
                    UNION
                    SELECT id FROM lexical
                ),
                ranked AS (
                    SELECT
                        c.id::text,
                        s.title,
                        s.url,
                        c.content,
                        s.reviewed_at::text,
                        (
                            $3 * (1 - (c.embedding <=> $1::vector))
                            + (1 - $3) * LEAST(
                                ts_rank_cd(
                                    c.search_vector,
                                    plainto_tsquery('russian', $2)
                                ) * 4,
                                1
                            )
                        ) AS score
                    FROM candidates x
                    JOIN knowledge_chunks c ON c.id = x.id
                    JOIN knowledge_sources s ON s.id = c.source_id
                )
                SELECT id, title, url, content, reviewed_at, score
                FROM ranked
                WHERE score >= $5
                ORDER BY score DESC, id
                LIMIT $6
                """,
                vector,
                query,
                self.dense_weight,
                candidate_limit,
                self.min_score,
                limit,
                self.source_max_age_days,
                self.embedding_model,
                self.embedding_dimensions,
                self.embedding_revision,
            )
        except (
            OSError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            httpx.HTTPError,
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
        ) as exc:
            RAG_SEARCHES.labels("error").inc()
            raise KnowledgeUnavailable("RAG временно недоступен") from exc
        finally:
            RAG_SEARCH_SECONDS.observe(time.perf_counter() - started)
        result = [
            SourceRef(
                id=row["id"],
                title=row["title"],
                url=row["url"],
                excerpt=row["content"][: self.excerpt_chars],
                reviewed_at=row["reviewed_at"],
                score=round(float(row["score"]), 6),
            )
            for row in rows
        ]
        RAG_SEARCHES.labels("hit" if result else "empty").inc()
        return result

    async def ping(self) -> bool:
        try:
            pool = await self._pool()
            ready = await pool.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM knowledge_chunks c
                    JOIN knowledge_sources s ON s.id = c.source_id
                    WHERE s.enabled = true
                      AND s.reviewed_at >= current_date - $1::integer
                      AND (s.expires_at IS NULL OR s.expires_at > now())
                      AND s.embedding_model = $2
                      AND s.embedding_dimensions = $3
                      AND s.embedding_revision = $4
                )
                """,
                self.source_max_age_days,
                self.embedding_model,
                self.embedding_dimensions,
                self.embedding_revision,
            )
            return ready is True
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError):
            return False

    async def close(self) -> None:
        await self.http.aclose()
        if self.pool is not None:
            await self.pool.close()
