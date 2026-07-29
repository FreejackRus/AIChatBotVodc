#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.model_gateway import SYSTEM_PROMPT  # noqa: E402


@dataclass(frozen=True, slots=True)
class Candidate:
    model: str
    base_url: str


@dataclass(frozen=True, slots=True)
class ControlCase:
    id: str
    category: str
    prompt: str
    source_context: str
    required_all: tuple[str, ...]
    required_any: tuple[str, ...]
    forbidden: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Sample:
    case_id: str
    passed: bool
    ttft_seconds: float | None
    total_seconds: float
    response: str
    error: str | None = None


def load_cases(path: Path) -> list[ControlCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = [
        ControlCase(
            id=str(item["id"]),
            category=str(item["category"]),
            prompt=str(item["prompt"]),
            source_context=str(item.get("source_context", "")),
            required_all=tuple(
                str(term).casefold() for term in item.get("required_all", [])
            ),
            required_any=tuple(
                str(term).casefold() for term in item.get("required_any", [])
            ),
            forbidden=tuple(
                str(term).casefold() for term in item.get("forbidden", [])
            ),
        )
        for item in payload
    ]
    ids = [case.id for case in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("Контрольный набор пуст или содержит дублирующиеся id")
    return cases


def parse_candidate(value: str) -> Candidate:
    try:
        model, base_url = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "candidate должен иметь формат MODEL=http://host:port"
        ) from exc
    if not model.strip() or not base_url.startswith(("http://", "https://")):
        raise argparse.ArgumentTypeError("Некорректный candidate")
    return Candidate(model.strip(), base_url.rstrip("/"))


def evaluate(case: ControlCase, response: str) -> bool:
    normalized = " ".join(response.casefold().split())
    has_all = all(term in normalized for term in case.required_all)
    has_any = not case.required_any or any(
        term in normalized for term in case.required_any
    )
    has_forbidden = any(term in normalized for term in case.forbidden)
    return bool(normalized) and has_all and has_any and not has_forbidden


async def sample(
    client: httpx.AsyncClient,
    candidate: Candidate,
    case: ControlCase,
) -> Sample:
    system = SYSTEM_PROMPT
    if case.source_context:
        system += f"\nПроверенный контекст:\n{case.source_context}"
    started = time.perf_counter()
    first_content_at: float | None = None
    chunks: list[str] = []
    try:
        async with client.stream(
            "POST",
            f"{candidate.base_url}/v1/chat/completions",
            json={
                "model": candidate.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": case.prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 768,
                "stream": True,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                data = json.loads(payload)
                content = data["choices"][0]["delta"].get("content", "")
                if content:
                    if first_content_at is None:
                        first_content_at = time.perf_counter()
                    chunks.append(str(content))
    except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        finished = time.perf_counter()
        return Sample(
            case_id=case.id,
            passed=False,
            ttft_seconds=None,
            total_seconds=finished - started,
            response="".join(chunks),
            error=f"{type(exc).__name__}: {exc}",
        )
    finished = time.perf_counter()
    content = "".join(chunks).strip()
    error = None if content else "empty_response"
    return Sample(
        case_id=case.id,
        passed=error is None and evaluate(case, content),
        ttft_seconds=(
            first_content_at - started if first_content_at is not None else None
        ),
        total_seconds=finished - started,
        response=content,
        error=error,
    )


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


async def benchmark_candidate(
    client: httpx.AsyncClient,
    candidate: Candidate,
    cases: list[ControlCase],
    repetitions: int,
) -> dict[str, Any]:
    samples = [
        await sample(client, candidate, case)
        for _ in range(repetitions)
        for case in cases
    ]
    ttft = [
        item.ttft_seconds for item in samples if item.ttft_seconds is not None
    ]
    totals = [item.total_seconds for item in samples]
    passed = sum(item.passed for item in samples)
    return {
        "model": candidate.model,
        "base_url": candidate.base_url,
        "samples": len(samples),
        "passed": passed,
        "pass_rate": round(passed / len(samples), 4),
        "errors": sum(item.error is not None for item in samples),
        "ttft_median_seconds": (
            round(statistics.median(ttft), 3) if ttft else None
        ),
        "ttft_p95_seconds": (
            round(percentile(ttft, 0.95) or 0.0, 3) if ttft else None
        ),
        "total_p95_seconds": round(percentile(totals, 0.95) or 0.0, 3),
        "failed_cases": [
            {
                "id": item.case_id,
                "error": item.error,
                "response": item.response[:500],
            }
            for item in samples
            if not item.passed
        ],
    }


async def run(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    timeout = httpx.Timeout(args.timeout, connect=min(args.timeout, 5))
    async with httpx.AsyncClient(timeout=timeout) as client:
        candidates = [
            await benchmark_candidate(client, candidate, cases, args.repetitions)
            for candidate in args.candidate
        ]
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "control_set": str(args.cases),
        "case_count": len(cases),
        "repetitions": args.repetitions,
        "gates": {
            "minimum_pass_rate": args.minimum_pass_rate,
            "maximum_ttft_p95_seconds": args.maximum_ttft,
        },
        "candidates": candidates,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    if not args.enforce:
        return 0
    return int(
        any(
            item["pass_rate"] < args.minimum_pass_rate
            or item["ttft_p95_seconds"] is None
            or item["ttft_p95_seconds"] > args.maximum_ttft
            or item["errors"] > 0
            for item in candidates
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        type=parse_candidate,
        action="append",
        required=True,
        help="MODEL=http://host:port; укажите параметр для каждой модели",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=PROJECT_ROOT / "evals" / "model_prototype.json",
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--minimum-pass-rate", type=float, default=1.0)
    parser.add_argument("--maximum-ttft", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions должен быть положительным")
    if not 0 <= args.minimum_pass_rate <= 1:
        parser.error("--minimum-pass-rate должен быть от 0 до 1")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
