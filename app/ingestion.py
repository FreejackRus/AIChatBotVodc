from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import asyncpg
import httpx
from bs4 import BeautifulSoup

from .domain.safety import contains_prompt_injection

TRUSTED_SOURCE_HOSTS = {"vodc.ru", "www.vodc.ru"}
EMPTY_CONTENT_HASH = hashlib.sha256(b"").hexdigest()


@dataclass(frozen=True, slots=True)
class ManifestSource:
    filename: str
    title: str
    url: str
    owner: str
    reviewed_at: date
    local_path: str | None = None
    expires_at: date | None = None
    enabled: bool = True

    def effective_expiry(self, max_age_days: int) -> date:
        review_expiry = self.reviewed_at + timedelta(days=max_age_days)
        return min(review_expiry, self.expires_at or review_expiry)

    def active(self, max_age_days: int, as_of: date | None = None) -> bool:
        return self.enabled and self.effective_expiry(max_age_days) >= (
            as_of or datetime.now(timezone.utc).date()
        )


@dataclass(frozen=True, slots=True)
class PreparedSource:
    source: ManifestSource
    content_hash: str
    chunks: tuple[str, ...]
    embeddings: tuple[tuple[float, ...], ...]
    changed: bool


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise TypeError(f"{field} должен быть датой ISO YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} должен быть датой ISO YYYY-MM-DD") from exc


def load_manifest(path: Path) -> list[ManifestSource]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось прочитать реестр источников {path}") from exc
    if (
        not isinstance(data, dict)
        or data.get("version") != 2
        or not isinstance(data.get("sources"), list)
    ):
        raise ValueError(
            "Реестр источников version=2 должен содержать массив sources"
        )

    result: list[ManifestSource] = []
    filenames: set[str] = set()
    urls: set[str] = set()
    today = datetime.now(timezone.utc).date()
    for index, item in enumerate(data["sources"]):
        if not isinstance(item, dict):
            raise TypeError(f"sources[{index}] должен быть объектом")
        required = ("filename", "title", "url", "owner", "reviewed_at")
        missing = [field for field in required if not str(item.get(field, "")).strip()]
        if missing:
            raise ValueError(f"sources[{index}] не содержит {', '.join(missing)}")

        filename = str(item["filename"]).strip()
        if Path(filename).name != filename:
            raise ValueError(f"sources[{index}].filename должен быть именем файла")
        url = str(item["url"]).strip().rstrip("/") + "/"
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() not in TRUSTED_SOURCE_HOSTS
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"sources[{index}].url не входит в allowlist VODC")
        if filename in filenames or url in urls:
            raise ValueError(f"sources[{index}] дублирует filename или url")

        reviewed_at = _parse_date(item["reviewed_at"], "reviewed_at")
        if reviewed_at > today:
            raise ValueError(f"sources[{index}].reviewed_at находится в будущем")
        expires_at = (
            _parse_date(item["expires_at"], "expires_at")
            if item.get("expires_at")
            else None
        )
        if expires_at and expires_at < reviewed_at:
            raise ValueError(f"sources[{index}].expires_at раньше reviewed_at")

        local_path = (
            str(item["local_path"]).strip() if item.get("local_path") else None
        )
        if local_path and (
            Path(local_path).is_absolute() or ".." in Path(local_path).parts
        ):
            raise ValueError(f"sources[{index}].local_path небезопасен")
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise TypeError(f"sources[{index}].enabled должен быть boolean")

        source = ManifestSource(
            filename=filename,
            title=str(item["title"]).strip(),
            url=url,
            owner=str(item["owner"]).strip(),
            reviewed_at=reviewed_at,
            local_path=local_path,
            expires_at=expires_at,
            enabled=enabled,
        )
        result.append(source)
        filenames.add(filename)
        urls.add(url)
    return result


def normalize_content(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = normalize_content(text)
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        if end < len(normalized):
            search_start = start + max(1, chunk_size // 2)
            boundaries = (
                normalized.rfind("\n\n", search_start, end),
                normalized.rfind("\n", search_start, end),
                normalized.rfind(". ", search_start, end),
                normalized.rfind(" ", search_start, end),
            )
            boundary = max(boundaries)
            if boundary > start:
                end = boundary + (1 if normalized[boundary] == "." else 0)
        chunk = normalized[start:end].strip()
        if chunk and (not chunks or chunks[-1] != chunk):
            chunks.append(chunk)
        if end >= len(normalized):
            break
        next_start = max(start + 1, end - overlap)
        for delimiter in ("\n\n", ". ", "\n", " "):
            boundary = normalized.find(delimiter, next_start, end)
            if boundary >= 0:
                next_start = boundary + len(delimiter)
                break
        start = next_start
    return chunks


def _vector(values: tuple[float, ...]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


class KnowledgeIngestion:
    def __init__(
        self,
        database_url: str,
        embedding_base_url: str,
        embedding_model: str,
        embedding_revision: str,
        embedding_dimensions: int,
        embedding_batch_size: int,
        timeout: float,
        manifest_root: Path,
        source_max_bytes: int,
        source_max_age_days: int,
    ):
        self.database_url = database_url
        self.embedding_base_url = embedding_base_url
        self.embedding_model = embedding_model
        self.embedding_revision = embedding_revision
        self.embedding_dimensions = embedding_dimensions
        self.embedding_batch_size = embedding_batch_size
        self.manifest_root = manifest_root.resolve()
        self.source_max_bytes = source_max_bytes
        self.source_max_age_days = source_max_age_days
        self.http = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def _content(self, source: ManifestSource) -> str:
        if source.local_path:
            path = (self.manifest_root / source.local_path).resolve()
            if self.manifest_root != path.parent and self.manifest_root not in path.parents:
                raise ValueError("local_path выходит за пределы каталога реестра")
            if not path.is_file():
                raise ValueError(f"Локальный snapshot отсутствует: {source.local_path}")
            raw = path.read_bytes()
            if len(raw) > self.source_max_bytes:
                raise ValueError(f"Источник {source.filename} превышает лимит размера")
            return normalize_content(raw.decode("utf-8"))

        response = await self.http.get(source.url)
        response.raise_for_status()
        final_host = (response.url.host or "").lower()
        if final_host not in TRUSTED_SOURCE_HOSTS:
            raise ValueError("Источник перенаправил запрос за пределы allowlist")
        if len(response.content) > self.source_max_bytes:
            raise ValueError(f"Источник {source.filename} превышает лимит размера")
        content_type = response.headers.get("content-type", "").lower()
        if not any(kind in content_type for kind in ("text/html", "text/plain")):
            raise ValueError(f"Источник {source.filename} вернул не текст")
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "aside",
                "form",
                "noscript",
                "svg",
            ]
        ):
            node.decompose()
        return normalize_content(soup.get_text("\n", strip=True))

    async def _embeddings(self, texts: list[str]) -> tuple[tuple[float, ...], ...]:
        result: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self.embedding_batch_size):
            batch = texts[start : start + self.embedding_batch_size]
            response = await self.http.post(
                f"{self.embedding_base_url}/v1/embeddings",
                json={"model": self.embedding_model, "input": batch},
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            rows = payload.get("data")
            if not isinstance(rows, list) or len(rows) != len(batch):
                raise ValueError("Embedding API вернул неверное число векторов")
            if not all(isinstance(row, dict) for row in rows):
                raise ValueError("Embedding API вернул некорректный data")
            try:
                indices = [int(row["index"]) for row in rows]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Embedding API не вернул корректные индексы") from exc
            if sorted(indices) != list(range(len(batch))):
                raise ValueError("Embedding API вернул дублированные индексы")
            ordered = sorted(rows, key=lambda row: int(row["index"]))
            for row in ordered:
                values = row.get("embedding") if isinstance(row, dict) else None
                if not isinstance(values, list):
                    raise TypeError("Embedding API вернул некорректный вектор")
                vector = tuple(float(value) for value in values)
                if len(vector) != self.embedding_dimensions:
                    raise ValueError(
                        "Размерность embedding не совпадает со схемой pgvector: "
                        f"{len(vector)} != {self.embedding_dimensions}"
                    )
                if not all(math.isfinite(value) for value in vector):
                    raise ValueError("Embedding содержит NaN или Infinity")
                result.append(vector)
        return tuple(result)

    def _manifest_hash(self, sources: list[ManifestSource]) -> str:
        payload = [
            {
                **asdict(source),
                "reviewed_at": source.reviewed_at.isoformat(),
                "expires_at": (
                    source.expires_at.isoformat() if source.expires_at else None
                ),
            }
            for source in sources
        ]
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def run(
        self,
        sources: list[ManifestSource],
        chunk_size: int,
        overlap: int,
    ) -> dict[str, int]:
        pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=3)
        try:
            existing_rows = await pool.fetch(
                """
                SELECT s.url, s.content_hash, s.embedding_model,
                       s.embedding_revision,
                       s.embedding_dimensions, s.chunk_size, s.chunk_overlap,
                       s.origin,
                       count(c.id)::integer AS chunk_count
                FROM knowledge_sources s
                LEFT JOIN knowledge_chunks c ON c.source_id = s.id
                GROUP BY s.id
                """
            )
            existing = {row["url"]: row for row in existing_rows}
            prepared: list[PreparedSource] = []
            inactive = 0
            unchanged = 0

            for source in sources:
                if not source.active(self.source_max_age_days):
                    inactive += 1
                    continue
                content = await self._content(source)
                if not content:
                    raise ValueError(f"Источник {source.filename} не содержит текста")
                if contains_prompt_injection(content):
                    raise ValueError(
                        f"Источник {source.filename} содержит инструкции для модели"
                    )
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                chunks = chunk_text(content, chunk_size, overlap)
                if not chunks:
                    raise ValueError(f"Источник {source.filename} не дал ни одного чанка")
                current = existing.get(source.url)
                if current and current.get("origin", "manual") == "staged":
                    raise ValueError(
                        f"Manual manifest конфликтует со staged source: {source.url}"
                    )
                changed = not current or any(
                    (
                        current["content_hash"] != content_hash,
                        current["embedding_model"] != self.embedding_model,
                        current["embedding_revision"] != self.embedding_revision,
                        current["embedding_dimensions"] != self.embedding_dimensions,
                        current["chunk_size"] != chunk_size,
                        current["chunk_overlap"] != overlap,
                        current["chunk_count"] != len(chunks),
                    )
                )
                embeddings = await self._embeddings(chunks) if changed else ()
                if not changed:
                    unchanged += 1
                prepared.append(
                    PreparedSource(
                        source=source,
                        content_hash=content_hash,
                        chunks=tuple(chunks),
                        embeddings=embeddings,
                        changed=changed,
                    )
                )

            stats = {
                "listed": len(sources),
                "active": len(prepared),
                "changed": sum(item.changed for item in prepared),
                "unchanged": unchanged,
                "disabled": inactive,
                "chunks": sum(
                    len(item.chunks) for item in prepared if item.changed
                ),
            }
            manifest_hash = self._manifest_hash(sources)
            now = datetime.now(timezone.utc)

            async with pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    """
                    UPDATE knowledge_sources
                    SET enabled = false, last_checked_at = $1
                    WHERE origin = 'manual'
                    """,
                    now,
                )
                for source in sources:
                    if source.active(self.source_max_age_days):
                        continue
                    source_id = uuid.uuid5(uuid.NAMESPACE_URL, source.url)
                    expiry = datetime.combine(
                        source.effective_expiry(self.source_max_age_days),
                        time.max,
                        timezone.utc,
                    )
                    await connection.execute(
                        """
                        INSERT INTO knowledge_sources
                            (id, filename, title, url, owner, reviewed_at,
                             expires_at, content_hash, enabled, last_checked_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, false, $9)
                        ON CONFLICT (url) DO UPDATE SET
                            filename = excluded.filename,
                            title = excluded.title,
                            owner = excluded.owner,
                            reviewed_at = excluded.reviewed_at,
                            expires_at = excluded.expires_at,
                            enabled = false,
                            last_checked_at = excluded.last_checked_at
                        """,
                        source_id,
                        source.filename,
                        source.title,
                        source.url,
                        source.owner,
                        source.reviewed_at,
                        expiry,
                        existing.get(source.url, {}).get(
                            "content_hash", EMPTY_CONTENT_HASH
                        ),
                        now,
                    )

                for item in prepared:
                    source = item.source
                    source_id = uuid.uuid5(uuid.NAMESPACE_URL, source.url)
                    expiry = datetime.combine(
                        source.effective_expiry(self.source_max_age_days),
                        time.max,
                        timezone.utc,
                    )
                    await connection.execute(
                        """
                        INSERT INTO knowledge_sources
                            (id, filename, title, url, owner, reviewed_at,
                             expires_at, content_hash, enabled, indexed_at,
                             embedding_model, embedding_dimensions,
                             embedding_revision, chunk_size, chunk_overlap,
                             last_checked_at)
                        VALUES
                            ($1, $2, $3, $4, $5, $6, $7, $8, true, $9,
                             $10, $11, $12, $13, $14, $9)
                        ON CONFLICT (url) DO UPDATE SET
                            filename = excluded.filename,
                            title = excluded.title,
                            owner = excluded.owner,
                            reviewed_at = excluded.reviewed_at,
                            expires_at = excluded.expires_at,
                            content_hash = excluded.content_hash,
                            enabled = true,
                            indexed_at = CASE WHEN $15
                                THEN excluded.indexed_at
                                ELSE knowledge_sources.indexed_at END,
                            embedding_model = excluded.embedding_model,
                            embedding_dimensions = excluded.embedding_dimensions,
                            embedding_revision = excluded.embedding_revision,
                            chunk_size = excluded.chunk_size,
                            chunk_overlap = excluded.chunk_overlap,
                            last_checked_at = excluded.last_checked_at
                        """,
                        source_id,
                        source.filename,
                        source.title,
                        source.url,
                        source.owner,
                        source.reviewed_at,
                        expiry,
                        item.content_hash,
                        now,
                        self.embedding_model,
                        self.embedding_dimensions,
                        self.embedding_revision,
                        chunk_size,
                        overlap,
                        item.changed,
                    )
                    if not item.changed:
                        continue
                    await connection.execute(
                        "DELETE FROM knowledge_chunks WHERE source_id = $1",
                        source_id,
                    )
                    for position, (chunk, embedding) in enumerate(
                        zip(item.chunks, item.embeddings, strict=True)
                    ):
                        await connection.execute(
                            """
                            INSERT INTO knowledge_chunks
                                (source_id, position, content, content_hash, embedding)
                            VALUES ($1, $2, $3, $4, $5::vector)
                            """,
                            source_id,
                            position,
                            chunk,
                            hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                            _vector(embedding),
                        )
                await connection.execute(
                    """
                    DELETE FROM knowledge_chunks c
                    USING knowledge_sources s
                    WHERE c.source_id = s.id AND s.enabled = false
                    """
                )
                await connection.execute(
                    """
                    INSERT INTO knowledge_index_runs
                        (manifest_hash, embedding_model, embedding_revision, stats)
                    VALUES ($1, $2, $3, $4::jsonb)
                    """,
                    manifest_hash,
                    self.embedding_model,
                    self.embedding_revision,
                    json.dumps(stats, ensure_ascii=False),
                )
            return stats
        finally:
            await pool.close()
            await self.http.aclose()
