from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from config import get_settings

from .adapters.event_store import PostgresEventStore
from .ingestion import KnowledgeIngestion, load_manifest

logger = logging.getLogger("vodc_worker")
PROJECT_DIR = Path(__file__).resolve().parents[1]


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
        settings.request_timeout,
        PROJECT_DIR,
    )
    result = await ingestion.run(
        load_manifest(settings.source_manifest_path),
        settings.rag_chunk_size,
        settings.rag_chunk_overlap,
    )
    logger.info(
        "Worker cycle completed: sources=%s chunks=%s expired_rows=%s",
        result["sources"],
        result["chunks"],
        deleted,
    )


async def run(once: bool) -> None:
    interval = int(os.getenv("WORKER_INTERVAL_SECONDS", "86400"))
    retry_interval = int(os.getenv("WORKER_RETRY_SECONDS", "60"))
    while True:
        succeeded = False
        try:
            await cycle()
            succeeded = True
        except Exception:
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
    asyncio.run(run(args.once))


if __name__ == "__main__":
    main()
