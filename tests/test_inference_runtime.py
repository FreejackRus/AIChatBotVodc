import json
from pathlib import Path

import httpx
import pytest

from scripts.inference_preflight import PreflightError, parse_gpu_inventory
from scripts.inference_smoke import (
    SmokeError,
    _text_delta,
    probe_chat,
    probe_embedding,
)


ROOT = Path(__file__).resolve().parents[1]


def test_parse_gpu_inventory():
    inventory = parse_gpu_inventory(
        "0, NVIDIA GeForce RTX 5090, 32607, 580.82.09\n"
        "1, NVIDIA GeForce RTX 5090, 32607, 580.82.09\n"
    )

    assert [gpu.index for gpu in inventory] == [0, 1]
    assert all(gpu.memory_mib == 32607 for gpu in inventory)


def test_parse_gpu_inventory_rejects_unknown_format():
    with pytest.raises(PreflightError):
        parse_gpu_inventory("GPU 0: unknown")


def test_sse_parser_rejects_broken_payload():
    with pytest.raises(SmokeError):
        _text_delta("data: {broken")


def test_inference_probes_validate_chat_and_embedding_contracts():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        if request.url.path == "/v1/models":
            model = (
                "Qwen3-Embedding-0.6B"
                if request.url.host == "embedding"
                else "Qwen3.5-9B"
            )
            return httpx.Response(200, json={"data": [{"id": model}]})
        if request.url.path == "/v1/chat/completions":
            payload = json.loads(request.content)
            assert payload["chat_template_kwargs"] == {"enable_thinking": False}
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    'data: {"choices":[{"delta":{"content":"готов"}}]}\n\n'
                    "data: [DONE]\n\n"
                ).encode(),
            )
        if request.url.path == "/v1/embeddings":
            return httpx.Response(
                200,
                json={"data": [{"embedding": [0.1, 0.2, 0.3]}]},
            )
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        chat = probe_chat(client, "http://chat:8000", "Qwen3.5-9B", 10)
        embedding = probe_embedding(
            client,
            "http://embedding:8000",
            "Qwen3-Embedding-0.6B",
        )

    assert chat.output_chars == 5
    assert chat.ttft_seconds <= 10
    assert embedding.dimensions == 3


def test_stage_3_observability_artifacts_are_wired():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prometheus = (ROOT / "ops/prometheus.yml").read_text(encoding="utf-8")
    alerts = (ROOT / "ops/alert-rules.yml").read_text(encoding="utf-8")
    dashboard = json.loads(
        (ROOT / "ops/dashboards/vodc-inference.json").read_text(encoding="utf-8")
    )

    assert compose.count("/health', timeout=5)") == 3
    assert '"127.0.0.1:${VLLM_PRIMARY_PORT:-8000}:8000"' in compose
    assert "dcgm-exporter:4.6.0-4.8.3-distroless" in compose
    assert "vllm-embedding:8000" in prometheus
    assert "dcgm-exporter:9400" in prometheus
    assert "VodcAllChatReplicasUnavailable" in alerts
    assert dashboard["uid"] == "vodc-inference"
    assert len(dashboard["panels"]) >= 8
