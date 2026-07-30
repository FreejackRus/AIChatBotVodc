#!/usr/bin/env python3
"""Measure Recall@K of the production pgvector knowledge adapter."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.knowledge import PostgresKnowledgeAdapter
from config import get_settings
from scripts.validate_retrieval_gold import validate_cases


async def evaluate(
    cases: list[dict[str, Any]],
    adapter: Any,
    k: int,
) -> dict[str, Any]:
    results = []
    recall_sum = 0.0
    critical_failures = 0
    for case in cases:
        expected = set(case["expected_urls"])
        sources = await adapter.search(str(case["query"]), k)
        returned = {source.url for source in sources}
        matched = expected & returned
        recall = len(matched) / len(expected)
        recall_sum += recall
        critical_failed = bool(case.get("critical")) and not matched
        critical_failures += int(critical_failed)
        results.append(
            {
                "query": case["query"],
                "expected_urls": sorted(expected),
                "returned_urls": [source.url for source in sources],
                "recall": round(recall, 6),
                "critical_failed": critical_failed,
            }
        )
    return {
        "cases": len(cases),
        "k": k,
        "recall_at_k": round(recall_sum / max(1, len(cases)), 6),
        "critical_failures": critical_failures,
        "results": results,
    }


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--minimum-recall", type=float, default=0.9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k должен быть положительным")
    if not 0 <= args.minimum_recall <= 1:
        parser.error("--minimum-recall должен быть от 0 до 1")

    cases = json.loads(args.path.read_text(encoding="utf-8"))
    failures = validate_cases(cases)
    if failures:
        parser.error("; ".join(failures))
    settings = get_settings()
    if not settings.database_url:
        parser.error("DATABASE_URL обязателен для production retrieval eval")

    adapter = PostgresKnowledgeAdapter(
        settings.database_url,
        settings.embedding_base_url,
        settings.embedding_model,
        settings.embedding_revision,
        settings.embedding_dimensions,
        settings.request_timeout,
        settings.rag_dense_weight,
        settings.rag_min_score,
        settings.rag_candidate_multiplier,
        settings.source_max_age_days,
        settings.rag_excerpt_chars,
    )
    try:
        report = await evaluate(cases, adapter, args.k)
    finally:
        await adapter.close()
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    passed = (
        report["recall_at_k"] >= args.minimum_recall
        and report["critical_failures"] == 0
    )
    return 0 if passed else 1


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
