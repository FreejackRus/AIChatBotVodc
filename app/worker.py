from __future__ import annotations

import argparse
import asyncio
import logging
import os

from prometheus_client import start_http_server

from config import get_settings

from .adapters.event_store import PostgresEventStore
from .catalog_audit import VodcCatalogAuditor
from .ingestion import KnowledgeIngestion, load_manifest
from .metrics import (
    CATALOG_AUDIT_ISSUES,
    CATALOG_AUDIT_RUNS,
    CATALOG_AUDIT_SERVICES,
    KNOWLEDGE_INGESTION_CHUNKS,
    KNOWLEDGE_INGESTION_RUNS,
    SOURCE_STAGING_CREATED,
    SOURCE_STAGING_QUARANTINED,
    SOURCE_STAGING_RUNS,
)
from .source_staging import SemanticSourceStager

logger = logging.getLogger("vodc_worker")


async def _audit_public_catalog(settings) -> None:
    auditor = VodcCatalogAuditor(
        settings.database_url,
        settings.catalog_audit_url,
        timeout=settings.request_timeout,
        maximum_bytes=settings.catalog_audit_max_bytes,
        minimum_services=settings.catalog_audit_min_services,
        max_removed_ratio=settings.catalog_audit_max_removed_ratio,
    )
    try:
        audit = await auditor.run()
    except Exception:
        CATALOG_AUDIT_RUNS.labels("error").inc()
        logger.exception(
            "Audit-only public catalogue cycle failed; active RAG is unchanged"
        )
    else:
        CATALOG_AUDIT_RUNS.labels(audit["status"]).inc()
        CATALOG_AUDIT_SERVICES.set(audit["services"])
        CATALOG_AUDIT_ISSUES.set(audit["issues"])
        logger.info(
            (
                "Audit-only catalogue completed: status=%s services=%s "
                "rows=%s issues=%s added=%s removed=%s changed=%s"
            ),
            audit["status"],
            audit["services"],
            audit["rows"],
            audit["issues"],
            audit.get("added", 0),
            audit.get("removed", 0),
            audit.get("changed", 0),
        )
    finally:
        await auditor.close()


async def _stage_semantic_sources(settings) -> None:
    stager = SemanticSourceStager(
        settings.database_url,
        settings.source_discovery_manifest_path,
        timeout=settings.request_timeout,
        maximum_bytes=settings.source_staging_max_bytes,
        batch_size=settings.source_staging_batch_size,
        delay_ms=settings.source_staging_delay_ms,
    )
    try:
        result = await stager.run()
    except Exception:
        SOURCE_STAGING_RUNS.labels("error").inc()
        logger.exception(
            "Semantic source staging failed; active RAG is unchanged"
        )
    else:
        SOURCE_STAGING_RUNS.labels(result["status"]).inc()
        SOURCE_STAGING_CREATED.set(result["created"])
        SOURCE_STAGING_QUARANTINED.set(result["quarantined"])
        logger.info(
            (
                "Semantic source staging completed: status=%s registered=%s "
                "checked=%s created=%s unchanged=%s quarantined=%s "
                "discovered=%s errors=%s"
            ),
            result["status"],
            result["registered"],
            result["checked"],
            result["created"],
            result["unchanged"],
            result["quarantined"],
            result["discovered"],
            result["errors"],
        )
    finally:
        await stager.close()


async def cycle() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("Worker требует DATABASE_URL")
    try:
        events = PostgresEventStore(settings.database_url)
        try:
            deleted = await events.cleanup(settings.transcript_retention_days)
        finally:
            await events.close()
        ingestion = KnowledgeIngestion(
            settings.database_url,
            settings.embedding_base_url,
            settings.embedding_model,
            settings.embedding_revision,
            settings.embedding_dimensions,
            settings.embedding_batch_size,
            settings.request_timeout,
            settings.source_manifest_path.parent,
            settings.source_max_bytes,
            settings.source_max_age_days,
        )
        result = await ingestion.run(
            load_manifest(settings.source_manifest_path),
            settings.rag_chunk_size,
            settings.rag_chunk_overlap,
        )
        logger.info(
            (
                "Worker cycle completed: listed=%s active=%s changed=%s "
                "unchanged=%s disabled=%s chunks=%s expired_rows=%s"
            ),
            result["listed"],
            result["active"],
            result["changed"],
            result["unchanged"],
            result["disabled"],
            result["chunks"],
            deleted,
        )
        KNOWLEDGE_INGESTION_RUNS.labels("success").inc()
        KNOWLEDGE_INGESTION_CHUNKS.inc(result["chunks"])
    finally:
        if settings.catalog_audit_enabled:
            await _audit_public_catalog(settings)
        if settings.source_staging_enabled:
            await _stage_semantic_sources(settings)


async def run(once: bool) -> None:
    interval = int(os.getenv("WORKER_INTERVAL_SECONDS", "86400"))
    retry_interval = int(os.getenv("WORKER_RETRY_SECONDS", "60"))
    while True:
        succeeded = False
        try:
            await cycle()
            succeeded = True
        except Exception:
            KNOWLEDGE_INGESTION_RUNS.labels("error").inc()
            logger.exception("Worker cycle failed")
            if once:
                raise
        if once:
            return
        await asyncio.sleep(interval if succeeded else retry_interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    metrics_port = int(os.getenv("WORKER_METRICS_PORT", "9101"))
    if metrics_port < 1 or metrics_port > 65535:
        raise ValueError("WORKER_METRICS_PORT должен быть от 1 до 65535")
    start_http_server(metrics_port)
    asyncio.run(run(args.once))


if __name__ == "__main__":
    main()
