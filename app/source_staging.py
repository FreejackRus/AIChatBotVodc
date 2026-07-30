"""Versioned, review-gated discovery of semantic RAG source candidates."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import asyncpg
import httpx
from bs4 import BeautifulSoup

from .domain.safety import contains_prompt_injection
from .ingestion import normalize_content

ALLOWED_HOSTS = frozenset({"vodc.ru", "www.vodc.ru"})
SOURCE_TYPES = frozenset(
    {"organizational", "preparation", "service_description"}
)
RISK_TIERS = frozenset({"low", "medium", "medical"})
USER_AGENT = "VODC-AI-Source-Staging/1.0 (+https://vodc.ru/)"
SPACE_RE = re.compile(r"\s+")
PRICE_RE = re.compile(
    r"(?:\b(?:цена|стоимость)\b.{0,40}\d|"
    r"\d[\d\s\u00a0]*(?:₽|руб(?:\.|лей)?))",
    re.IGNORECASE,
)


class SourceStagingError(RuntimeError):
    """A source cannot be safely discovered, fetched, or extracted."""


@dataclass(frozen=True, slots=True)
class DiscoverySeed:
    url: str
    source_type: str
    risk_tier: str
    owner: str
    discover_prefix: str | None
    discovery_only: bool


@dataclass(frozen=True, slots=True)
class SourceTarget:
    id: uuid.UUID
    url: str
    source_type: str
    risk_tier: str
    owner: str
    service_code: str | None
    etag: str | None
    last_modified: str | None
    discover_prefix: str | None = None
    discovery_only: bool = False


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    title: str
    text: str
    sections: tuple[dict[str, str], ...]
    quality_issues: tuple[str, ...]
    discovered_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FetchResult:
    final_url: str
    html: str | None
    etag: str | None
    last_modified: str | None
    not_modified: bool


def _normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def canonical_vodc_url(value: str, *, base_url: str | None = None) -> str:
    absolute = urljoin(base_url, value) if base_url else value
    parsed = urlparse(absolute)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or host not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
    ):
        raise SourceStagingError(f"URL вне HTTPS allowlist VODC: {absolute}")
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunparse(("https", parsed.netloc.lower(), path, "", "", ""))


def load_discovery_manifest(path: Path) -> tuple[DiscoverySeed, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceStagingError(
            f"Не удалось прочитать discovery manifest {path}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or not isinstance(payload.get("seeds"), list)
    ):
        raise SourceStagingError(
            "Discovery manifest version=1 должен содержать seeds"
        )

    result: list[DiscoverySeed] = []
    seen: set[str] = set()
    for index, item in enumerate(payload["seeds"]):
        if not isinstance(item, dict):
            raise SourceStagingError(f"seeds[{index}] должен быть объектом")
        url = canonical_vodc_url(str(item.get("url", "")).strip())
        source_type = str(item.get("source_type", "")).strip()
        risk_tier = str(item.get("risk_tier", "")).strip()
        owner = str(item.get("owner", "")).strip()
        prefix_value = item.get("discover_prefix")
        discover_prefix = (
            str(prefix_value).strip() if prefix_value is not None else None
        )
        discovery_only = item.get("discovery_only", False)
        if source_type not in SOURCE_TYPES:
            raise SourceStagingError(f"seeds[{index}].source_type неизвестен")
        if risk_tier not in RISK_TIERS:
            raise SourceStagingError(f"seeds[{index}].risk_tier неизвестен")
        if not owner:
            raise SourceStagingError(f"seeds[{index}].owner обязателен")
        if not isinstance(discovery_only, bool):
            raise SourceStagingError(
                f"seeds[{index}].discovery_only должен быть boolean"
            )
        if discovery_only and not discover_prefix:
            raise SourceStagingError(
                f"seeds[{index}] discovery_only требует discover_prefix"
            )
        if discover_prefix is not None and (
            not discover_prefix.startswith("/")
            or ".." in discover_prefix
            or "?" in discover_prefix
        ):
            raise SourceStagingError(
                f"seeds[{index}].discover_prefix небезопасен"
            )
        if url in seen:
            raise SourceStagingError(f"seeds[{index}] дублирует URL")
        seen.add(url)
        result.append(
            DiscoverySeed(
                url=url,
                source_type=source_type,
                risk_tier=risk_tier,
                owner=owner,
                discover_prefix=discover_prefix,
                discovery_only=discovery_only,
            )
        )
    return tuple(result)


def extract_semantic_page(
    html: str,
    source_url: str,
    *,
    source_type: str,
    discover_prefix: str | None,
) -> ExtractedPage:
    canonical_url = canonical_vodc_url(source_url)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main.page") or soup.find("main")
    if main is None:
        raise SourceStagingError("На странице отсутствует main")
    discovered: set[str] = set()
    if discover_prefix:
        for link in main.find_all("a", href=True):
            try:
                target = canonical_vodc_url(
                    str(link["href"]),
                    base_url=canonical_url,
                )
            except SourceStagingError:
                continue
            parsed = urlparse(target)
            if (
                (parsed.hostname or "").lower() in ALLOWED_HOSTS
                and parsed.path.startswith(discover_prefix)
                and target != canonical_url
            ):
                discovered.add(target)
    for node in main.select(
        "script, style, nav, footer, header, aside, form, noscript, svg, "
        ".breadcrumbs, .breadcrumb, [class*='review'], [class*='rating']"
    ):
        node.decompose()
    heading = main.find("h1")
    if heading is None:
        raise SourceStagingError("На странице отсутствует h1")
    title = _normalize_text(heading.get_text(" ", strip=True))
    if not title:
        raise SourceStagingError("Страница содержит пустой h1")

    sections: list[dict[str, str]] = []
    section_heading = title
    paragraphs: list[str] = []

    def flush() -> None:
        if not paragraphs:
            return
        content = normalize_content("\n".join(paragraphs))
        if content:
            sections.append({"heading": section_heading, "content": content})
        paragraphs.clear()

    last_text = ""
    for node in main.find_all(["h2", "h3", "h4", "p", "li"]):
        text = _normalize_text(node.get_text(" ", strip=True))
        if not text or text == last_text:
            continue
        last_text = text
        if node.name in {"h2", "h3", "h4"}:
            flush()
            section_heading = text
            continue
        if source_type == "service_description" and PRICE_RE.search(text):
            continue
        paragraphs.append(text)
    flush()

    if not sections:
        fallback = _normalize_text(main.get_text(" ", strip=True))
        if fallback.startswith(title):
            fallback = fallback[len(title) :].strip()
        if source_type == "service_description":
            fallback = " ".join(
                sentence
                for sentence in re.split(r"(?<=[.!?])\s+", fallback)
                if not PRICE_RE.search(sentence)
            )
        if fallback:
            sections.append({"heading": title, "content": fallback})

    text = normalize_content(
        "\n\n".join(
            f"## {section['heading']}\n{section['content']}"
            for section in sections
        )
    )
    quality_issues: list[str] = []
    minimum = {
        "organizational": 80,
        "preparation": 100,
        "service_description": 80,
    }[source_type]
    if len(text) < minimum:
        quality_issues.append("content_too_short")
    if contains_prompt_injection(text):
        quality_issues.append("prompt_injection")
    if source_type == "service_description" and PRICE_RE.search(text):
        quality_issues.append("dynamic_price_leak")

    return ExtractedPage(
        title=title,
        text=text,
        sections=tuple(sections),
        quality_issues=tuple(sorted(set(quality_issues))),
        discovered_urls=tuple(sorted(discovered)),
    )


class SemanticSourceStager:
    def __init__(
        self,
        database_url: str,
        manifest_path: Path,
        *,
        timeout: float,
        maximum_bytes: int,
        batch_size: int,
        delay_ms: int,
    ) -> None:
        self.database_url = database_url
        self.seeds = load_discovery_manifest(manifest_path)
        self.maximum_bytes = maximum_bytes
        self.batch_size = batch_size
        self.delay_seconds = delay_ms / 1000
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        )
        self._robots: dict[str, RobotFileParser] = {}

    async def close(self) -> None:
        await self.http.aclose()

    async def _read_bounded(self, response: httpx.Response) -> bytes:
        length = response.headers.get("content-length")
        if length:
            try:
                if int(length) > self.maximum_bytes:
                    raise SourceStagingError("Страница превышает лимит размера")
            except ValueError as exc:
                raise SourceStagingError("Некорректный Content-Length") from exc
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > self.maximum_bytes:
                raise SourceStagingError("Страница превышает лимит размера")
        return bytes(body)

    async def _robot_policy(self, url: str) -> RobotFileParser:
        host = (urlparse(url).hostname or "").lower()
        cached = self._robots.get(host)
        if cached is not None:
            return cached
        robots_url = f"https://{host}/robots.txt"
        async with self.http.stream("GET", robots_url) as response:
            response.raise_for_status()
            body = await self._read_bounded(response)
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        self._robots[host] = parser
        return parser

    async def _fetch(self, target: SourceTarget) -> FetchResult:
        policy = await self._robot_policy(target.url)
        if not policy.can_fetch(USER_AGENT, target.url):
            raise SourceStagingError("robots.txt запрещает загрузку URL")
        headers: dict[str, str] = {}
        if target.etag:
            headers["If-None-Match"] = target.etag
        if target.last_modified:
            headers["If-Modified-Since"] = target.last_modified
        async with self.http.stream("GET", target.url, headers=headers) as response:
            for item in (*response.history, response):
                canonical_vodc_url(str(item.url))
            final_url = canonical_vodc_url(str(response.url))
            if urlparse(final_url).hostname != urlparse(target.url).hostname:
                final_policy = await self._robot_policy(final_url)
                if not final_policy.can_fetch(USER_AGENT, final_url):
                    raise SourceStagingError(
                        "robots.txt финального домена запрещает URL"
                    )
            if response.status_code == 304:
                return FetchResult(
                    final_url=final_url,
                    html=None,
                    etag=response.headers.get("etag") or target.etag,
                    last_modified=(
                        response.headers.get("last-modified")
                        or target.last_modified
                    ),
                    not_modified=True,
                )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                raise SourceStagingError(
                    f"Неожиданный Content-Type: {content_type[:100]}"
                )
            body = await self._read_bounded(response)
            encoding = response.charset_encoding or "utf-8"
            return FetchResult(
                final_url=final_url,
                html=body.decode(encoding, errors="replace"),
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                not_modified=False,
            )

    async def _upsert_candidate(
        self,
        pool: asyncpg.Pool,
        *,
        url: str,
        source_type: str,
        risk_tier: str,
        owner: str,
        service_code: str | None = None,
    ) -> None:
        candidate_id = uuid.uuid5(uuid.NAMESPACE_URL, url)
        await pool.execute(
            """
            INSERT INTO source_candidates
                (id, url, source_type, risk_tier, owner, service_code, enabled)
            VALUES ($1, $2, $3, $4, $5, $6, true)
            ON CONFLICT (url) DO UPDATE SET
                source_type = excluded.source_type,
                risk_tier = excluded.risk_tier,
                owner = excluded.owner,
                service_code = COALESCE(
                    excluded.service_code, source_candidates.service_code
                ),
                enabled = true,
                last_seen_at = now()
            """,
            candidate_id,
            url,
            source_type,
            risk_tier,
            owner,
            service_code,
        )

    async def _register_catalog_targets(self, pool: asyncpg.Pool) -> int:
        await pool.execute(
            """
            UPDATE source_candidates
            SET enabled = false
            WHERE source_type = 'service_description'
            """
        )
        rows = await pool.fetch(
            """
            WITH latest AS (
                SELECT id
                FROM catalog_audit_runs
                WHERE status IN ('success', 'quarantined')
                ORDER BY completed_at DESC
                LIMIT 1
            )
            SELECT DISTINCT o.service_code, o.detail_url
            FROM catalog_service_observations o
            JOIN latest l ON l.id = o.run_id
            WHERE o.detail_url IS NOT NULL
            ORDER BY o.service_code, o.detail_url
            """
        )
        for row in rows:
            await self._upsert_candidate(
                pool,
                url=canonical_vodc_url(row["detail_url"]),
                source_type="service_description",
                risk_tier="medium",
                owner="Контент-владелец каталога ВОККДЦ",
                service_code=row["service_code"],
            )
        return len(rows)

    async def _due_targets(self, pool: asyncpg.Pool) -> tuple[SourceTarget, ...]:
        seed_prefixes = {
            seed.url: seed.discover_prefix
            for seed in self.seeds
        }
        discovery_only_urls = {
            seed.url
            for seed in self.seeds
            if seed.discovery_only
        }
        rows = await pool.fetch(
            """
            SELECT id, url, source_type, risk_tier, owner, service_code,
                   etag, last_modified
            FROM source_candidates
            WHERE enabled = true
            ORDER BY last_checked_at ASC NULLS FIRST, url
            LIMIT $1
            """,
            self.batch_size,
        )
        return tuple(
            SourceTarget(
                id=row["id"],
                url=row["url"],
                source_type=row["source_type"],
                risk_tier=row["risk_tier"],
                owner=row["owner"],
                service_code=row["service_code"],
                etag=row["etag"],
                last_modified=row["last_modified"],
                discover_prefix=seed_prefixes.get(row["url"]),
                discovery_only=row["url"] in discovery_only_urls,
            )
            for row in rows
        )

    async def _store_page(
        self,
        pool: asyncpg.Pool,
        *,
        run_id: uuid.UUID,
        target: SourceTarget,
        fetched: FetchResult,
        page: ExtractedPage,
    ) -> str:
        content_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
        version_id = uuid.uuid5(target.id, content_hash)
        review_status = (
            "quarantined" if page.quality_issues else "pending_review"
        )
        command = await pool.execute(
            """
            INSERT INTO source_versions
                (id, candidate_id, run_id, content_hash, title, extracted_text,
                 sections, quality_issues, review_status)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            ON CONFLICT (candidate_id, content_hash) DO NOTHING
            """,
            version_id,
            target.id,
            run_id,
            content_hash,
            page.title,
            page.text,
            json.dumps(page.sections, ensure_ascii=False),
            list(page.quality_issues),
            review_status,
        )
        await pool.execute(
            """
            UPDATE source_candidates
            SET etag = $2, last_modified = $3, last_checked_at = now(),
                last_seen_at = now(), last_error = NULL
            WHERE id = $1
            """,
            target.id,
            fetched.etag,
            fetched.last_modified,
        )
        return "created" if command.endswith("1") else "unchanged"

    async def run(self) -> dict[str, int | str]:
        run_id = uuid.uuid4()
        started_at = datetime.now(UTC)
        pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=3)
        await pool.execute(
            """
            INSERT INTO source_stage_runs (id, status, started_at)
            VALUES ($1, 'running', $2)
            """,
            run_id,
            started_at,
        )
        stats = {
            "registered": 0,
            "checked": 0,
            "created": 0,
            "unchanged": 0,
            "quarantined": 0,
            "errors": 0,
            "discovered": 0,
        }
        try:
            for seed in self.seeds:
                await self._upsert_candidate(
                    pool,
                    url=seed.url,
                    source_type=seed.source_type,
                    risk_tier=seed.risk_tier,
                    owner=seed.owner,
                )
                stats["registered"] += 1
            stats["registered"] += await self._register_catalog_targets(pool)
            targets = await self._due_targets(pool)

            for index, target in enumerate(targets):
                try:
                    fetched = await self._fetch(target)
                    stats["checked"] += 1
                    if fetched.not_modified:
                        await pool.execute(
                            """
                            UPDATE source_candidates
                            SET last_checked_at = now(), last_seen_at = now(),
                                last_error = NULL, etag = $2, last_modified = $3
                            WHERE id = $1
                            """,
                            target.id,
                            fetched.etag,
                            fetched.last_modified,
                        )
                        stats["unchanged"] += 1
                        continue
                    if fetched.html is None:
                        raise SourceStagingError("Пустой HTML после загрузки")
                    page = extract_semantic_page(
                        fetched.html,
                        fetched.final_url,
                        source_type=target.source_type,
                        discover_prefix=target.discover_prefix,
                    )
                    for url in page.discovered_urls:
                        await self._upsert_candidate(
                            pool,
                            url=url,
                            source_type=target.source_type,
                            risk_tier=target.risk_tier,
                            owner=target.owner,
                        )
                        stats["discovered"] += 1
                    if target.discovery_only:
                        await pool.execute(
                            """
                            UPDATE source_candidates
                            SET etag = $2, last_modified = $3,
                                last_checked_at = now(), last_seen_at = now(),
                                last_error = NULL
                            WHERE id = $1
                            """,
                            target.id,
                            fetched.etag,
                            fetched.last_modified,
                        )
                        continue
                    result = await self._store_page(
                        pool,
                        run_id=run_id,
                        target=target,
                        fetched=fetched,
                        page=page,
                    )
                    stats[result] += 1
                    if page.quality_issues:
                        stats["quarantined"] += 1
                except (
                    SourceStagingError,
                    httpx.HTTPError,
                    UnicodeError,
                    ValueError,
                ) as exc:
                    stats["errors"] += 1
                    await pool.execute(
                        """
                        UPDATE source_candidates
                        SET last_checked_at = now(), last_error = $2
                        WHERE id = $1
                        """,
                        target.id,
                        f"{type(exc).__name__}: {str(exc)[:400]}",
                    )
                if self.delay_seconds and index + 1 < len(targets):
                    await asyncio.sleep(self.delay_seconds)

            status = (
                "partial"
                if stats["errors"]
                else "success"
            )
            await pool.execute(
                """
                UPDATE source_stage_runs
                SET status = $2, stats = $3::jsonb, completed_at = now()
                WHERE id = $1
                """,
                run_id,
                status,
                json.dumps(stats, ensure_ascii=False),
            )
            return {"run_id": str(run_id), "status": status, **stats}
        except Exception:
            await pool.execute(
                """
                UPDATE source_stage_runs
                SET status = 'failed', stats = $2::jsonb, completed_at = now()
                WHERE id = $1
                """,
                run_id,
                json.dumps(stats, ensure_ascii=False),
            )
            raise
        finally:
            await pool.close()
