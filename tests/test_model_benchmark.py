import json
from pathlib import Path

import httpx
import pytest

from scripts.benchmark_models import (
    Candidate,
    ControlCase,
    evaluate,
    load_cases,
    sample,
)


def test_model_control_set_has_unique_twenty_cases():
    path = Path(__file__).resolve().parents[1] / "evals" / "model_prototype.json"
    cases = load_cases(path)
    assert len(cases) == 20
    assert len({case.id for case in cases}) == 20
    assert {
        "grounding",
        "dynamic_data",
        "medical_safety",
        "prompt_injection",
        "tool_boundary",
        "privacy",
        "style",
    } <= {case.category for case in cases}


def test_control_case_evaluator_checks_required_and_forbidden_terms():
    case = ControlCase(
        id="test",
        category="test",
        prompt="test",
        source_context="",
        required_all=("официальн",),
        required_any=("источник", "сайт"),
        forbidden=("выдуманная цена",),
    )
    assert evaluate(case, "Официальный источник находится на сайте.")
    assert not evaluate(case, "Официальный сайт: выдуманная цена.")


@pytest.mark.asyncio
async def test_benchmark_uses_first_content_and_disables_thinking():
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.read()))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"reasoning_content":"hidden"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":"official source"}}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    case = ControlCase(
        id="test",
        category="test",
        prompt="test",
        source_context="verified",
        required_all=("official",),
        required_any=("source",),
        forbidden=(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await sample(
            client,
            Candidate("test-model", "http://model:8000"),
            case,
        )

    assert result.passed is True
    assert result.ttft_seconds is not None
    assert result.response == "official source"
    assert payloads[0]["chat_template_kwargs"]["enable_thinking"] is False
