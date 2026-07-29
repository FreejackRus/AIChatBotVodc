#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx


async def create_session(client: httpx.AsyncClient, base_url: str) -> str:
    response = await client.post(
        f"{base_url}/api/v1/sessions",
        json={
            "page_context": {
                "url": "https://vodc.ru/",
                "title": "Нагрузочный тест",
            },
            "client": {"locale": "ru", "timezone": "Europe/Moscow"},
        },
    )
    response.raise_for_status()
    return response.json()["session_id"]


async def message(
    client: httpx.AsyncClient, base_url: str, session_id: str, text: str
) -> tuple[float, float]:
    started = time.perf_counter()
    first_token = None
    async with client.stream(
        "POST",
        f"{base_url}/api/v1/sessions/{session_id}/messages/stream",
        json={
            "input": {"type": "text", "text": text},
            "client_message_id": str(uuid.uuid4()),
        },
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.startswith("event: text_delta") and first_token is None:
                first_token = time.perf_counter()
    completed = time.perf_counter()
    return (
        (first_token or completed) - started,
        completed - started,
    )


async def dialog(
    client: httpx.AsyncClient, base_url: str, turns: int
) -> list[tuple[float, float]]:
    session_id = await create_session(client, base_url)
    return [
        await message(
            client,
            base_url,
            session_id,
            f"Тестовый организационный вопрос {index + 1}: где найти услугу?",
        )
        for index in range(turns)
    ]


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, int(len(ordered) * percentile_value) - 1),
    )
    return ordered[index]


async def run(args) -> int:
    timeout = httpx.Timeout(args.timeout, connect=5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        results = await asyncio.gather(
            *(
                dialog(client, args.base_url.rstrip("/"), args.turns)
                for _ in range(args.concurrency)
            ),
            return_exceptions=True,
        )
    errors = [result for result in results if isinstance(result, Exception)]
    samples = [
        sample
        for result in results
        if not isinstance(result, Exception)
        for sample in result
    ]
    if not samples:
        print(json.dumps({"errors": len(errors), "samples": 0}))
        return 1
    ttft = [sample[0] for sample in samples]
    total = [sample[1] for sample in samples]
    report = {
        "dialogs": args.concurrency,
        "turns": args.turns,
        "samples": len(samples),
        "errors": len(errors),
        "ttft_p50_seconds": round(statistics.median(ttft), 3),
        "ttft_p95_seconds": round(percentile(ttft, 0.95), 3),
        "total_p95_seconds": round(percentile(total, 0.95), 3),
        "gate_ttft_seconds": args.ttft_gate,
        "passed": not errors and percentile(ttft, 0.95) <= args.ttft_gate,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://chat.vodc.ru")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--ttft-gate", type=float, default=10)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
