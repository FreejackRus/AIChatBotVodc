from __future__ import annotations

import argparse
import asyncio
import logging
import os

from prometheus_client import start_http_server

from config import get_settings

from .adapters.event_store import PostgresEventStore
from .ingestion import KnowledgeIngestion, load_manifest
from .metrics import KNOWLEDGE_INGESTION_CHUNKS, KNOWLEDGE_INGESTION_RUNS

logger = logging.getLogger("vodc_worker")


async def cycle() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("Worker требует DATABASE_URL")
    events = PostgresEventStore(settings.database_url)
    deleted = await events.cleanup(settings.transcript_retention_days)
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
