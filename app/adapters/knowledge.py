from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from ..domain.models import SourceRef
from ..ports import KnowledgeUnavailable


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zа-яё0-9]{3,}", text.lower())
        if token not in {"для", "или", "как", "что", "это", "при"}
    }


class JsonKnowledgeAdapter:
    """Safe local fallback for the existing read-only JSON index."""

    def __init__(self, knowledge_base_path: Path, manifest_path: Path):
        store = json.loads(
            (knowledge_base_path / "vector_store.json").read_text(encoding="utf-8")
        )
        self.documents = store.get("documents", [])
        self.sources: dict[str, dict[str, Any]] = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.sources = {
                item.get("filename", ""): item for item in manifest.get("sources", [])
            }

    async def search(self, query: str, limit: int) -> list[SourceRef]:
        query_terms = _terms(query)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for document in self.documents:
            content_terms = _terms(document.get("content", ""))
            score = len(query_terms & content_terms) / max(1, len(query_terms))
            if score:
                ranked.append((score, document))
        ranked.sort(key=lambda item: item[0], reverse=True)
        result: list[SourceRef] = []
        for score, document in ranked[:limit]:
            filename = document.get("filename", "source")
            metadata = self.sources.get(filename, {})
            result.append(
                SourceRef(
                    id=f"{filename}:{document.get('chunk_id', 0)}",
                    title=metadata.get("title") or filename,
                    url=metadata.get("url", "https://vodc.ru/"),
                    excerpt=document.get("content", "")[:320],
                    reviewed_at=metadata.get("reviewed_at"),
                    score=round(score, 4),
                )
            )
        return result

    async def ping(self) -> bool:
        return bool(self.documents)

    async def close(self) -> None:
        return None


class PostgresKnowledgeAdapter:
    def __init__(
        self,
        database_url: str,
        embedding_base_url: str,
        embedding_model: str,
        timeout: float,
    ):
        self.database_url = database_url
        self.embedding_base_url = embedding_base_url
        self.embedding_model = embedding_model
        self.timeout = timeout
        self.pool: asyncpg.Pool | None = None
        self.http = httpx.AsyncClient(timeout=timeout)

    async def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.database_url, min_size=1, max_size=5
            )
        return self.pool

    async def _embedding(self, text: str) -> list[float]:
        response = await self.http.post(
            f"{self.embedding_base_url}/v1/embeddings",
            json={"model": self.embedding_model, "input": text},
        )
        response.raise_for_status()
        data = response.json()
        return [float(value) for value in data["data"][0]["embedding"]]

    async def search(self, query: str, limit: int) -> list[SourceRef]:
        try:
            embedding = await self._embedding(query)
            vector = "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
            pool = await self._pool()
            rows = await pool.fetch(
                """
                SELECT
                    c.id::text,
                    s.title,
                    s.url,
                    c.content,
                    s.reviewed_at::text,
                    1 - (c.embedding <=> $1::vector) AS score
                FROM knowledge_chunks c
                JOIN knowledge_sources s ON s.id = c.source_id
                WHERE s.enabled = true
                  AND (s.expires_at IS NULL OR s.expires_at > now())
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
                """,
                vector,
                limit,
            )
        except (
            OSError,
            ValueError,
            KeyError,
            IndexError,
            httpx.HTTPError,
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
        ) as exc:
            raise KnowledgeUnavailable("RAG временно недоступен") from exc
        return [
            SourceRef(
                id=row["id"],
                title=row["title"],
                url=row["url"],
                excerpt=row["content"][:320],
                reviewed_at=row["reviewed_at"],
                score=round(float(row["score"]), 6),
            )
            for row in rows
        ]

    async def ping(self) -> bool:
        try:
            pool = await self._pool()
            chunks = await pool.fetchval("SELECT count(*) FROM knowledge_chunks")
            return int(chunks) > 0
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError):
            return False

    async def close(self) -> None:
        await self.http.aclose()
        if self.pool is not None:
            await self.pool.close()
