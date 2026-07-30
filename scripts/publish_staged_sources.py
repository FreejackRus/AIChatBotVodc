#!/usr/bin/env python3
"""Dry-run, publish, or roll back approved staged knowledge sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.publisher import ControlledPublisher
from config import get_settings


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--rollback-url")
    parser.add_argument("--snapshot-id", type=uuid.UUID)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit должен быть положительным")
    if (args.apply or args.rollback_url) and not (args.actor or "").strip():
        parser.error("--actor обязателен для изменения активного RAG")
    if args.snapshot_id and not args.rollback_url:
        parser.error("--snapshot-id используется только с --rollback-url")

    settings = get_settings()
    if not settings.database_url:
        parser.error("DATABASE_URL обязателен")
    publisher = ControlledPublisher(
        settings.database_url,
        settings.embedding_base_url,
        settings.embedding_model,
        settings.embedding_revision,
        settings.embedding_dimensions,
        settings.embedding_batch_size,
        timeout=settings.request_timeout,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        source_max_age_days=settings.source_max_age_days,
    )
    try:
        if args.rollback_url:
            result = await publisher.rollback(
                args.rollback_url,
                actor=args.actor.strip(),
                snapshot_id=args.snapshot_id,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        candidates = await publisher.plan(args.limit)
        plan = [
            {
                "version_id": str(item.version_id),
                "url": item.url,
                "title": item.title,
                "risk_tier": item.risk_tier,
                "reviewer_role": item.reviewer_role,
                "manual_conflict": item.manual_conflict,
                "snapshot_exists": item.snapshot_id is not None,
            }
            for item in candidates
        ]
        if not args.apply:
            print(
                json.dumps(
                    {
                        "mode": "dry-run",
                        "publishable": sum(
                            not item["manual_conflict"] for item in plan
                        ),
                        "blocked": sum(item["manual_conflict"] for item in plan),
                        "items": plan,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        prepared = await publisher.prepare(candidates)
        result = await publisher.publish(
            prepared,
            actor=args.actor.strip(),
            blocked=sum(item.manual_conflict for item in candidates),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        await publisher.close()


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
