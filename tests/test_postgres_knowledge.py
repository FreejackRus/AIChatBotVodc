import json

import httpx
import pytest

from app.adapters.knowledge import (
    QUERY_INSTRUCTION,
    PostgresKnowledgeAdapter,
)
from app.ports import KnowledgeUnavailable


class FakePool:
    def __init__(self):
        self.query = ""
        self.args = ()

    async def fetch(self, query, *args):
        self.query = query
        self.args = args
        return [
            {
                "id": "chunk-1",
                "title": "Контакты",
                "url": "https://vodc.ru/contacts/",
                "content": "Главный корпус находится на площади Ленина, 5а.",
                "reviewed_at": "2026-07-29",
                "score": 0.91,
            }
        ]

    async def fetchval(self, _query, *_args):
        return True

    async def close(self):
        return None


def _adapter():
    return PostgresKnowledgeAdapter(
        "postgresql://unused",
        "http://embedding:8000",
        "Qwen3-Embedding-0.6B",
        "test-revision",
        embedding_dimensions=3,
        timeout=5,
        dense_weight=0.8,
        min_score=0.3,
        candidate_multiplier=8,
        source_max_age_days=180,
        excerpt_chars=800,
    )


@pytest.mark.asyncio
async def test_postgres_search_is_hybrid_current_and_instruction_aware():
    adapter = _adapter()
    pool = FakePool()
    adapter.pool = pool
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2, 0.3]}]},
        )

    await adapter.http.aclose()
    adapter.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await adapter.search("Где находится центр?", 5)
    await adapter.close()

    assert result[0].url == "https://vodc.ru/contacts/"
    assert bodies[0]["input"].startswith(QUERY_INSTRUCTION)
    assert bodies[0]["input"].endswith("Где находится центр?")
    assert "WITH dense AS" in pool.query
    assert "lexical AS" in pool.query
    assert "plainto_tsquery('russian'" in pool.query
    assert "s.reviewed_at >= current_date" in pool.query
    assert pool.args[3] == 40
    assert pool.args[4] == 0.3


@pytest.mark.asyncio
async def test_postgres_search_translates_wrong_embedding_dimension():
    adapter = _adapter()

    def handler(_request):
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2]}]},
        )

    await adapter.http.aclose()
    adapter.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(KnowledgeUnavailable):
        await adapter.search("контакты", 3)
    await adapter.close()
