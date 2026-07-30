#!/usr/bin/env python3
"""Probe every local inference endpoint and enforce the TTFT gate."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx


class SmokeError(RuntimeError):
    """An inference endpoint failed its contract check."""


@dataclass(frozen=True)
class ChatProbe:
    url: str
    model: str
    ttft_seconds: float
    output_chars: int


@dataclass(frozen=True)
class EmbeddingProbe:
    url: str
    model: str
    dimensions: int


def _model_ids(payload: Any) -> set[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise SmokeError("/v1/models вернул неожиданный JSON")
    return {
        item["id"]
        for item in payload["data"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _text_delta(line: str) -> str:
    if not line.startswith("data:"):
        return ""
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return ""
    try:
        data = json.loads(payload)
        delta = data["choices"][0]["delta"].get("content", "")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise SmokeError("Поток chat completion содержит некорректный SSE") from exc
    return delta if isinstance(delta, str) else ""


def _assert_health(client: httpx.Client, base_url: str) -> None:
    response = client.get(f"{base_url}/health")
    response.raise_for_status()


def probe_chat(
    client: httpx.Client,
    base_url: str,
    model: str,
    ttft_limit: float,
) -> ChatProbe:
    base_url = base_url.rstrip("/")
    _assert_health(client, base_url)
    models_response = client.get(f"{base_url}/v1/models")
    models_response.raise_for_status()
    if model not in _model_ids(models_response.json()):
        raise SmokeError(f"{base_url} не обслуживает модель {model}")

    started = time.perf_counter()
    first_token_at: float | None = None
    output: list[str] = []
    with client.stream(
        "POST",
        f"{base_url}/v1/chat/completions",
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "Ответьте одним словом: готов.",
                }
            ],
            "temperature": 0,
            "max_tokens": 16,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            delta = _text_delta(line)
            if not delta:
                continue
            if first_token_at is None:
                first_token_at = time.perf_counter()
            output.append(delta)

    if first_token_at is None or not "".join(output).strip():
        raise SmokeError(f"{base_url} завершил поток без текста")
    ttft = first_token_at - started
    if ttft > ttft_limit:
        raise SmokeError(
            f"{base_url}: TTFT {ttft:.3f}s превышает лимит {ttft_limit:.3f}s"
        )
    return ChatProbe(
        url=base_url,
        model=model,
        ttft_seconds=round(ttft, 3),
        output_chars=len("".join(output)),
    )


def probe_embedding(
    client: httpx.Client,
    base_url: str,
    model: str,
) -> EmbeddingProbe:
    base_url = base_url.rstrip("/")
    _assert_health(client, base_url)
    models_response = client.get(f"{base_url}/v1/models")
    models_response.raise_for_status()
    if model not in _model_ids(models_response.json()):
        raise SmokeError(f"{base_url} не обслуживает модель {model}")

    response = client.post(
        f"{base_url}/v1/embeddings",
        json={"model": model, "input": "проверка локального поиска"},
    )
    response.raise_for_status()
    try:
        vector = response.json()["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise SmokeError("Embedding endpoint вернул неожиданный JSON") from exc
    if not isinstance(vector, list) or not vector:
        raise SmokeError("Embedding endpoint вернул пустой вектор")
    if not all(isinstance(value, (int, float)) for value in vector):
        raise SmokeError("Embedding-вектор содержит нечисловые значения")
    return EmbeddingProbe(url=base_url, model=model, dimensions=len(vector))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test двух chat-реплик и embedding vLLM."
    )
    parser.add_argument(
        "--chat-url",
        action="append",
        required=True,
        help="URL chat-реплики; укажите аргумент для каждой реплики.",
    )
    parser.add_argument("--chat-model", default="Qwen3.5-9B")
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--embedding-model", default="Qwen3-Embedding-0.6B")
    parser.add_argument("--ttft-limit", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    if args.ttft_limit <= 0 or args.timeout <= 0:
        parser.error("таймауты должны быть положительными")

    try:
        with httpx.Client(timeout=args.timeout) as client:
            chats = [
                probe_chat(client, url, args.chat_model, args.ttft_limit)
                for url in args.chat_url
            ]
            embedding = probe_embedding(
                client, args.embedding_url, args.embedding_model
            )
    except (SmokeError, httpx.HTTPError) as exc:
        print(f"Inference smoke failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "passed",
                "chat_replicas": [asdict(probe) for probe in chats],
                "embedding": asdict(embedding),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
