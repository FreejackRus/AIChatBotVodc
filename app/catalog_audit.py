"""Audit-only ingestion of the public VODC service catalogue.

The data collected here is deliberately isolated from the user-facing RAG
index and MIS adapter. A successful crawl is an observation for comparison
and review, not an authoritative price publication.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import asyncpg
import httpx
from bs4 import BeautifulSoup

ALLOWED_HOSTS = frozenset({"vodc.ru", "www.vodc.ru"})
SERVICE_CODE_RE = re.compile(r"^[0-9]{10}$")
SPACE_RE = re.compile(r"\s+")
CATEGORY_COUNT_RE = re.compile(r"\s*\(\d+\s+услуг\w*\)\s*$", re.IGNORECASE)
USER_AGENT = "VODC-AI-Catalog-Audit/1.0 (+https://vodc.ru/)"


class CatalogAuditError(RuntimeError):
    """The public catalogue could not be fetched or parsed safely."""


@dataclass(frozen=True, slots=True)
class AuditIssue:
    code: str
    severity: str
    service_code: str | None
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ServiceObservation:
    service_code: str
    name: str
    price_text: str
    price_min_rub: int | None
    category_path: tuple[str, ...]
    detail_url: str | None
    row_hash: str


@dataclass(frozen=True, slots=True)
class ParsedCatalog:
    observations: tuple[ServiceObservation, ...]
    issues: tuple[AuditIssue, ...]

    @property
    def service_codes(self) -> frozenset[str]:
        return frozenset(item.service_code for item in self.observations)

    @property
    def fingerprints(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for item in self.observations:
            grouped.setdefault(item.service_code, []).append(item.row_hash)
        return {
            code: tuple(sorted(hashes))
            for code, hashes in grouped.items()
        }


@dataclass(frozen=True, slots=True)
class PreviousCatalog:
    run_id: uuid.UUID
    service_count: int
    etag: str | None
    last_modified: str | None
    fingerprints: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class CatalogFetch:
    final_url: str
    html: str | None
    content_hash: str | None
    etag: str | None
    last_modified: str | None
    not_modified: bool


def _text(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def _vodc_url(value: str, *, base_url: str | None = None) -> str:
    absolute = urljoin(base_url, value) if base_url else value
    parsed = urlparse(absolute)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_HOSTS:
        raise CatalogAuditError(f"URL вне HTTPS allowlist VODC: {absolute}")
    return urlunparse(
        (
            "https",
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )


def _price_min_rub(price_text: str) -> int | None:
    match = re.search(r"\d(?:[\d\s\xa0]*\d)?", price_text)
    digits = re.sub(r"\D", "", match.group(0)) if match else ""
    return int(digits) if digits else None


def _row_hash(item: tuple[str | int | None, ...]) -> str:
    encoded = json.dumps(
        item,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_catalog_html(
    html: str,
    source_url: str,
    *,
    minimum_services: int,
) -> ParsedCatalog:
    """Parse the server-rendered VODC price table without publishing it."""

    canonical_source = _vodc_url(source_url)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table#priceTable")
    if table is None:
        raise CatalogAuditError("На странице отсутствует table#priceTable")

    page_title = _text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    issues: list[AuditIssue] = []
    if "активация продукта" in page_title.lower():
        issues.append(
            AuditIssue(
                "unexpected_page_template",
                "critical",
                None,
                {"title": page_title[:200]},
            )
        )

    observations: list[ServiceObservation] = []
    categories_by_depth: dict[int, str] = {}
    for position, row in enumerate(table.select("tr")):
        classes = set(row.get("class") or ())
        cells = row.find_all("td", recursive=False)
        if "pricetable-parent-child" in classes:
            raw_depth = row.get("data-depth")
            category = _text(row.get_text(" ", strip=True))
            category = CATEGORY_COUNT_RE.sub("", category).strip()
            try:
                depth = int(raw_depth or "")
            except ValueError:
                depth = 0
            if depth > 0 and category:
                categories_by_depth = {
                    level: value
                    for level, value in categories_by_depth.items()
                    if level < depth
                }
                categories_by_depth[depth] = category
            else:
                issues.append(
                    AuditIssue(
                        "unknown_category_depth",
                        "warning",
                        None,
                        {"position": position, "depth": raw_depth},
                    )
                )
            continue
        if "pricetable-child" not in classes:
            continue
        if len(cells) != 3:
            issues.append(
                AuditIssue(
                    "invalid_service_row",
                    "critical",
                    None,
                    {"position": position, "cell_count": len(cells)},
                )
            )
            continue

        service_code = _text(cells[0].get_text(" ", strip=True))
        name = _text(cells[1].get_text(" ", strip=True))
        price_text = _text(cells[2].get_text(" ", strip=True))
        if not SERVICE_CODE_RE.fullmatch(service_code):
            issues.append(
                AuditIssue(
                    "invalid_service_code",
                    "critical",
                    service_code[:64] or None,
                    {"position": position},
                )
            )
            continue
        if not name:
            issues.append(
                AuditIssue(
                    "missing_service_name",
                    "critical",
                    service_code,
                    {"position": position},
                )
            )
            continue

        detail_url: str | None = None
        link = cells[1].find("a", href=True)
        if link is not None:
            try:
                detail_url = _vodc_url(str(link["href"]), base_url=canonical_source)
            except CatalogAuditError:
                issues.append(
                    AuditIssue(
                        "untrusted_detail_url",
                        "critical",
                        service_code,
                        {"position": position},
                    )
                )
        price_min = _price_min_rub(price_text)
        if price_min is None:
            issues.append(
                AuditIssue(
                    "price_without_number",
                    "warning",
                    service_code,
                    {"position": position, "price_text": price_text[:100]},
                )
            )

        category_path = tuple(
            categories_by_depth[level]
            for level in sorted(categories_by_depth)
        )
        identity = (
            service_code,
            name,
            price_text,
            price_min,
            category_path,
            detail_url,
        )
        observations.append(
            ServiceObservation(
                service_code=service_code,
                name=name,
                price_text=price_text,
                price_min_rub=price_min,
                category_path=category_path,
                detail_url=detail_url,
                row_hash=_row_hash(identity),
            )
        )

    grouped: dict[str, list[ServiceObservation]] = {}
    for item in observations:
        grouped.setdefault(item.service_code, []).append(item)
    for service_code, items in grouped.items():
        names = {item.name.casefold() for item in items}
        prices = {
            item.price_min_rub
            for item in items
            if item.price_min_rub is not None
        }
        if len(names) > 1:
            issues.append(
                AuditIssue(
                    "conflicting_service_names",
                    "critical",
                    service_code,
                    {"variants": len(names)},
                )
            )
        if len(prices) > 1:
            issues.append(
                AuditIssue(
                    "conflicting_service_prices",
                    "warning",
                    service_code,
                    {"variants": sorted(prices)},
                )
            )

    unique_count = len(grouped)
    if unique_count < minimum_services:
        issues.append(
            AuditIssue(
                "service_count_below_threshold",
                "critical",
                None,
                {"actual": unique_count, "minimum": minimum_services},
            )
        )
    return ParsedCatalog(tuple(observations), tuple(issues))


def compare_catalogs(
    current: ParsedCatalog,
    previous: PreviousCatalog | None,
    *,
    max_removed_ratio: float,
) -> tuple[dict[str, int | float | str | None], tuple[AuditIssue, ...]]:
    current_fingerprints = current.fingerprints
    current_codes = set(current_fingerprints)
    if previous is None:
        return (
            {
                "previous_run_id": None,
                "added": len(current_codes),
                "removed": 0,
                "changed": 0,
                "removed_ratio": 0.0,
            },
            (),
        )

    previous_codes = set(previous.fingerprints)
    added = current_codes - previous_codes
    removed = previous_codes - current_codes
    shared = current_codes & previous_codes
    changed = {
        code
        for code in shared
        if current_fingerprints[code] != previous.fingerprints[code]
    }
    removed_ratio = len(removed) / max(1, len(previous_codes))
    issues: list[AuditIssue] = []
    if removed_ratio > max_removed_ratio:
        issues.append(
            AuditIssue(
                "service_removal_spike",
                "critical",
                None,
                {
                    "removed": len(removed),
                    "previous": len(previous_codes),
                    "ratio": round(removed_ratio, 6),
                    "maximum": max_removed_ratio,
                },
            )
        )
    return (
        {
            "previous_run_id": str(previous.run_id),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "removed_ratio": round(removed_ratio, 6),
        },
        tuple(issues),
    )


class CatalogAuditRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def previous(self, source_url: str) -> PreviousCatalog | None:
        run = await self.pool.fetchrow(
            """
            SELECT r.id, r.service_count, r.etag, r.last_modified
            FROM catalog_audit_runs r
            WHERE r.source_url = $1
              AND r.status IN ('success', 'quarantined')
              AND EXISTS (
                  SELECT 1 FROM catalog_service_observations o
                  WHERE o.run_id = r.id
              )
            ORDER BY r.completed_at DESC
            LIMIT 1
            """,
            source_url,
        )
        if run is None:
            return None
        rows = await self.pool.fetch(
            """
            SELECT service_code, row_hash
            FROM catalog_service_observations
            WHERE run_id = $1
            ORDER BY service_code, row_hash
            """,
            run["id"],
        )
        grouped: dict[str, list[str]] = {}
        for row in rows:
            grouped.setdefault(row["service_code"], []).append(row["row_hash"])
        return PreviousCatalog(
            run_id=run["id"],
            service_count=run["service_count"],
            etag=run["etag"],
            last_modified=run["last_modified"],
            fingerprints={
                code: tuple(hashes)
                for code, hashes in grouped.items()
            },
        )

    async def save(
        self,
        *,
        run_id: uuid.UUID,
        source_url: str,
        fetched: CatalogFetch,
        parsed: ParsedCatalog,
        issues: tuple[AuditIssue, ...],
        stats: dict[str, Any],
        started_at: datetime,
    ) -> str:
        status = (
            "quarantined"
            if any(issue.severity == "critical" for issue in issues)
            else "success"
        )
        async with (
            self.pool.acquire() as connection,
            connection.transaction(),
        ):
            await connection.execute(
                """
                INSERT INTO catalog_audit_runs
                    (id, source_url, final_url, status, content_hash, etag,
                     last_modified, row_count, service_count, issue_count,
                     stats, started_at, completed_at)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                     $11::jsonb, $12, now())
                """,
                run_id,
                source_url,
                fetched.final_url,
                status,
                fetched.content_hash,
                fetched.etag,
                fetched.last_modified,
                len(parsed.observations),
                len(parsed.service_codes),
                len(issues),
                json.dumps(stats, ensure_ascii=False),
                started_at,
            )
            await connection.executemany(
                """
                INSERT INTO catalog_service_observations
                    (run_id, service_code, name, price_text, price_min_rub,
                     category_path, detail_url, row_hash)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    (
                        run_id,
                        item.service_code,
                        item.name,
                        item.price_text,
                        item.price_min_rub,
                        list(item.category_path),
                        item.detail_url,
                        item.row_hash,
                    )
                    for item in parsed.observations
                ],
            )
            await connection.executemany(
                """
                INSERT INTO catalog_audit_issues
                    (run_id, code, severity, service_code, details)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                [
                    (
                        run_id,
                        issue.code,
                        issue.severity,
                        issue.service_code,
                        json.dumps(issue.details, ensure_ascii=False),
                    )
                    for issue in issues
                ],
            )
        return status

    async def save_unchanged(
        self,
        *,
        run_id: uuid.UUID,
        source_url: str,
        fetched: CatalogFetch,
        previous: PreviousCatalog,
        started_at: datetime,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO catalog_audit_runs
                (id, source_url, final_url, status, content_hash, etag,
                 last_modified, row_count, service_count, issue_count,
                 stats, started_at, completed_at)
            VALUES
                ($1, $2, $3, 'unchanged', NULL, $4, $5, 0, $6, 0,
                 $7::jsonb, $8, now())
            """,
            run_id,
            source_url,
            fetched.final_url,
            fetched.etag,
            fetched.last_modified,
            previous.service_count,
            json.dumps(
                {"previous_run_id": str(previous.run_id)},
                ensure_ascii=False,
            ),
            started_at,
        )

    async def save_failure(
        self,
        *,
        run_id: uuid.UUID,
        source_url: str,
        started_at: datetime,
        error: Exception,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO catalog_audit_runs
                (id, source_url, final_url, status, row_count, service_count,
                 issue_count, stats, started_at, completed_at)
            VALUES
                ($1, $2, $2, 'failed', 0, 0, 1, $3::jsonb, $4, now())
            """,
            run_id,
            source_url,
            json.dumps(
                {
                    "error_type": type(error).__name__,
                    "message": str(error)[:500],
                },
                ensure_ascii=False,
            ),
            started_at,
        )


class VodcCatalogAuditor:
    def __init__(
        self,
        database_url: str,
        source_url: str,
        *,
        timeout: float,
        maximum_bytes: int,
        minimum_services: int,
        max_removed_ratio: float,
    ) -> None:
        self.database_url = database_url
        self.source_url = _vodc_url(source_url)
        self.maximum_bytes = maximum_bytes
        self.minimum_services = minimum_services
        self.max_removed_ratio = max_removed_ratio
        self.http = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def _fetch(self, previous: PreviousCatalog | None) -> CatalogFetch:
        headers: dict[str, str] = {}
        if previous and previous.etag:
            headers["If-None-Match"] = previous.etag
        if previous and previous.last_modified:
            headers["If-Modified-Since"] = previous.last_modified

        async with self.http.stream(
            "GET",
            self.source_url,
            headers=headers,
        ) as response:
            for redirect in (*response.history, response):
                _vodc_url(str(redirect.url))
            if response.status_code == 304:
                return CatalogFetch(
                    final_url=_vodc_url(str(response.url)),
                    html=None,
                    content_hash=None,
                    etag=response.headers.get("etag") or (
                        previous.etag if previous else None
                    ),
                    last_modified=response.headers.get("last-modified") or (
                        previous.last_modified if previous else None
                    ),
                    not_modified=True,
                )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                raise CatalogAuditError(
                    f"Неожиданный Content-Type каталога: {content_type[:100]}"
                )
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.maximum_bytes:
                raise CatalogAuditError("Каталог превышает лимит размера")

            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > self.maximum_bytes:
                    raise CatalogAuditError("Каталог превышает лимит размера")
            encoding = response.charset_encoding or "utf-8"
            raw = bytes(body)
            return CatalogFetch(
                final_url=_vodc_url(str(response.url)),
                html=raw.decode(encoding, errors="replace"),
                content_hash=hashlib.sha256(raw).hexdigest(),
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                not_modified=False,
            )

    async def run(self) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        run_id = uuid.uuid4()
        pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=2)
        repository = CatalogAuditRepository(pool)
        try:
            previous = await repository.previous(self.source_url)
            fetched = await self._fetch(previous)
            if fetched.not_modified:
                if previous is None:
                    raise CatalogAuditError("Получен 304 без предыдущего снимка")
                await repository.save_unchanged(
                    run_id=run_id,
                    source_url=self.source_url,
                    fetched=fetched,
                    previous=previous,
                    started_at=started_at,
                )
                return {
                    "run_id": str(run_id),
                    "status": "unchanged",
                    "services": previous.service_count,
                    "rows": 0,
                    "issues": 0,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }

            if fetched.html is None:
                raise CatalogAuditError("Пустой HTML каталога")
            parsed = parse_catalog_html(
                fetched.html,
                fetched.final_url,
                minimum_services=self.minimum_services,
            )
            comparison, comparison_issues = compare_catalogs(
                parsed,
                previous,
                max_removed_ratio=self.max_removed_ratio,
            )
            issues = parsed.issues + comparison_issues
            stats: dict[str, Any] = {
                **comparison,
                "duplicate_rows": len(parsed.observations)
                - len(parsed.service_codes),
                "critical_issues": sum(
                    issue.severity == "critical" for issue in issues
                ),
                "warning_issues": sum(
                    issue.severity == "warning" for issue in issues
                ),
            }
            status = await repository.save(
                run_id=run_id,
                source_url=self.source_url,
                fetched=fetched,
                parsed=parsed,
                issues=issues,
                stats=stats,
                started_at=started_at,
            )
            return {
                "run_id": str(run_id),
                "status": status,
                "services": len(parsed.service_codes),
                "rows": len(parsed.observations),
                "issues": len(issues),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                **comparison,
            }
        except Exception as exc:
            await repository.save_failure(
                run_id=run_id,
                source_url=self.source_url,
                started_at=started_at,
                error=exc,
            )
            raise
        finally:
            await pool.close()
