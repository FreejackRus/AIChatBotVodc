from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True, slots=True)
class ManifestSource:
    filename: str
    title: str
    url: str
    owner: str
    reviewed_at: str
    local_path: str | None = None
    enabled: bool = True


def load_manifest(path: Path) -> list[ManifestSource]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = []
    for item in data.get("sources", []):
        source = ManifestSource(**item)
        if source.enabled:
            sources.append(source)
    return sources


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not normalized:
        return []
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        if end < len(normalized):
            boundary = normalized.rfind("\n", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


class KnowledgeIngestion:
    def __init__(
        self,
        database_url: str,
        embedding_base_url: str,
        embedding_model: str,
        timeout: float,
        project_dir: Path,
    ):
        self.database_url = database_url
        self.embedding_base_url = embedding_base_url
        self.embedding_model = embedding_model
        self.project_dir = project_dir
        self.http = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def _content(self, source: ManifestSource) -> str:
        if source.local_path:
            path = (self.project_dir / source.local_path).resolve()
            if self.project_dir.resolve() not in path.parents:
                raise ValueError("local_path выходит за пределы проекта")
            return path.read_text(encoding="utf-8")
        response = await self.http.get(source.url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(["script", "style", "nav", "footer"]):
            node.decompose()
        return soup.get_text("\n", strip=True)

    async def _embedding(self, text: str) -> list[float]:
        response = await self.http.post(
            f"{self.embedding_base_url}/v1/embeddings",
            json={"model": self.embedding_model, "input": text},
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return [float(value) for value in payload["data"][0]["embedding"]]

    async def run(
        self,
        sources: list[ManifestSource],
        chunk_size: int,
        overlap: int,
    ) -> dict[str, int]:
        pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=3)
        source_count = 0
        chunk_count = 0
        try:
            for source in sources:
                content = await self._content(source)
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                source_id = uuid.uuid5(uuid.NAMESPACE_URL, source.url)
                chunks = chunk_text(content, chunk_size, overlap)
                embedded_chunks = [
                    (chunk, await self._embedding(chunk)) for chunk in chunks
                ]
                async with (
                    pool.acquire() as connection,
                    connection.transaction(),
                ):
                    await connection.execute(
                        """
                            INSERT INTO knowledge_sources
                                (id, filename, title, url, owner, reviewed_at,
                                 content_hash, enabled)
                            VALUES
                                ($1, $2, $3, $4, $5, $6::date, $7, true)
                            ON CONFLICT (url) DO UPDATE SET
                                filename = excluded.filename,
                                title = excluded.title,
                                owner = excluded.owner,
                                reviewed_at = excluded.reviewed_at,
                                content_hash = excluded.content_hash,
                                enabled = true,
                                indexed_at = now()
                            """,
                        source_id,
                        source.filename,
                        source.title,
                        source.url,
                        source.owner,
                        source.reviewed_at,
                        content_hash,
                    )
                    await connection.execute(
                        "DELETE FROM knowledge_chunks WHERE source_id = $1",
                        source_id,
                    )
                    for position, (chunk, embedding) in enumerate(embedded_chunks):
                        vector = (
                            "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
                        )
                        await connection.execute(
                            """
                                INSERT INTO knowledge_chunks
                                    (source_id, position, content, embedding)
                                VALUES ($1, $2, $3, $4::vector)
                                """,
                            source_id,
                            position,
                            chunk,
                            vector,
                        )
                        chunk_count += 1
                source_count += 1
        finally:
            await pool.close()
            await self.http.aclose()
        return {"sources": source_count, "chunks": chunk_count}
