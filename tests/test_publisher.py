import json
import uuid
from datetime import date

import httpx
import pytest

from app.publisher import (
    ControlledPublisher,
    PublicationCandidate,
    PublicationError,
    semantic_chunks,
)


def _candidate(**overrides):
    values = {
        "version_id": uuid.uuid4(),
        "candidate_id": uuid.uuid4(),
        "url": "https://vodc.ru/service/example/",
        "title": "Описание услуги",
        "owner": "Контент-владелец",
        "risk_tier": "medium",
        "sections": (
            {
                "heading": "Описание",
                "content": (
                    "Подробное утверждённое описание услуги диагностического "
                    "центра для посетителей официального сайта."
                ),
            },
        ),
        "content_hash": "a" * 64,
        "reviewed_at": date(2026, 7, 30),
        "reviewer_role": "content_owner",
        "manual_conflict": False,
        "snapshot_id": None,
    }
    values.update(overrides)
    return PublicationCandidate(**values)


def test_semantic_chunks_keep_heading_context():
    chunks = semantic_chunks(
        "МРТ",
        (
            {
                "heading": "Подготовка",
                "content": "Исследование проводится по утверждённым правилам.",
            },
        ),
        chunk_size=1000,
        overlap=200,
    )

    assert chunks == (
        "# МРТ\n\n## Подготовка\nИсследование проводится по утверждённым правилам.",
    )


def test_semantic_chunks_reject_dynamic_price():
    with pytest.raises(PublicationError, match="цен"):
        semantic_chunks(
            "Услуга",
            ({"heading": "Цена", "content": "Стоимость 2 500 ₽."},),
            chunk_size=1000,
            overlap=200,
        )


@pytest.mark.asyncio
async def test_prepare_embeds_publishable_and_skips_manual_conflict():
    publisher = ControlledPublisher(
        "postgresql://unused",
        "http://embedding:8000",
        "Qwen3-Embedding-0.6B",
        "revision",
        3,
        16,
        timeout=5,
        chunk_size=1000,
        chunk_overlap=200,
        source_max_age_days=180,
    )

    def handler(request):
        inputs = json.loads(request.content)["input"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [0.1, 0.2, 0.3]}
                    for index, _ in enumerate(inputs)
                ]
            },
        )

    await publisher.http.aclose()
    publisher.http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    prepared = await publisher.prepare(
        (
            _candidate(),
            _candidate(
                version_id=uuid.uuid4(),
                candidate_id=uuid.uuid4(),
                manual_conflict=True,
            ),
        )
    )
    await publisher.close()

    assert len(prepared) == 1
    assert len(prepared[0].chunks) == 1
    assert prepared[0].embeddings == ((0.1, 0.2, 0.3),)
