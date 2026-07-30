import json

import httpx
import pytest

from app.adapters.model_gateway import VLLMModelGateway
from app.domain.models import SourceRef
from app.ports import ModelUnavailable


@pytest.mark.asyncio
async def test_model_gateway_rotates_requests_but_keeps_unique_failover_order():
    gateway = VLLMModelGateway(
        ("http://primary:8000", "http://secondary:8000"),
        "test-model",
        timeout=5,
        max_tokens=10,
    )

    assert await gateway._replica_order() == (
        "http://primary:8000",
        "http://secondary:8000",
    )
    assert await gateway._replica_order() == (
        "http://secondary:8000",
        "http://primary:8000",
    )
    await gateway.close()


@pytest.mark.asyncio
async def test_model_gateway_fails_over_before_first_token():
    calls = []
    payloads = []

    def handler(request):
        calls.append(str(request.url))
        payloads.append(request.read())
        if request.url.host == "primary":
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
            ),
        )

    gateway = VLLMModelGateway(
        ("http://primary:8000", "http://secondary:8000"),
        "test-model",
        timeout=5,
        max_tokens=10,
    )
    await gateway.http.aclose()
    gateway.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = SourceRef(
        id="1",
        title="source",
        url="https://vodc.ru/",
        excerpt="verified",
    )

    output = [
        chunk
        async for chunk in gateway.stream(prompt="test", history=[], sources=[source])
    ]
    await gateway.close()

    assert output == ["ok"]
    assert calls == [
        "http://primary:8000/v1/chat/completions",
        "http://secondary:8000/v1/chat/completions",
    ]
    for payload in payloads:
        request_data = json.loads(payload)
        assert request_data["chat_template_kwargs"] == {
            "enable_thinking": False
        }
        system = request_data["messages"][0]["content"]
        assert "SOURCE_DATA_JSON:" in system
        assert '"url":"https://vodc.ru/"' in system
        assert "Проверенный контекст:" not in system


@pytest.mark.asyncio
async def test_model_gateway_translates_empty_replicas_to_port_error():
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: [DONE]\n\n",
        )

    gateway = VLLMModelGateway(
        ("http://primary:8000", "http://secondary:8000"),
        "test-model",
        timeout=5,
        max_tokens=10,
    )
    await gateway.http.aclose()
    gateway.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ModelUnavailable):
        _ = [
            chunk
            async for chunk in gateway.stream(
                prompt="test",
                history=[],
                sources=[],
            )
        ]
    await gateway.close()
