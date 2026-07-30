from __future__ import annotations

import hashlib
import json
import os
import uuid

import asyncpg
import httpx
import pytest

from app.adapters.knowledge import PostgresKnowledgeAdapter
from app.domain.models import RetrievalContext

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("TEST_DATABASE_URL"),
        reason="real pgvector integration runs in the migration CI job",
    ),
]


async def test_context_candidate_and_boost_execute_on_real_pgvector():
    database_url = os.environ["TEST_DATABASE_URL"]
    source_id = uuid.uuid4()
    path = f"context-integration-{source_id}"
    source_url = f"https://vodc.ru/{path}/"
    vector = "[" + ",".join(["0.1"] * 1024) + "]"
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            """
            INSERT INTO knowledge_sources
                (id, filename, title, url, owner, reviewed_at, content_hash,
                 embedding_model, embedding_revision, embedding_dimensions,
                 chunk_size, chunk_overlap)
            VALUES
                ($1, 'context.md', 'Контекстная страница', $2, 'ВОККДЦ',
                 current_date, $3, 'Qwen3-Embedding-0.6B',
                 'context-test-revision', 1024, 1000, 200)
            """,
            source_id,
            source_url,
            hashlib.sha256(b"source").hexdigest(),
        )
        await connection.execute(
            """
            INSERT INTO knowledge_chunks
                (source_id, position, content, content_hash, embedding)
            VALUES ($1, 0, 'Утверждённый контекст страницы', $2, $3::vector)
            """,
            source_id,
            hashlib.sha256(b"chunk").hexdigest(),
            vector,
        )

        adapter = PostgresKnowledgeAdapter(
            database_url,
            "http://embedding.test",
            "Qwen3-Embedding-0.6B",
            "context-test-revision",
            1024,
            5,
            0.8,
            0.3,
            8,
            180,
            800,
            context_boost=0.15,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert payload["input"].endswith("Что здесь?")
            assert path not in payload["input"]
            return httpx.Response(
                200,
                json={"data": [{"embedding": [0.1] * 1024}]},
            )

        await adapter.http.aclose()
        adapter.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await adapter.search(
                "Что здесь?",
                5,
                RetrievalContext(
                    page_url=f"https://www.vodc.ru/{path}/?utm_source=test"
                ),
            )
        finally:
            await adapter.close()

        assert result
        assert result[0].url == source_url
        assert result[0].score == 0.95
    finally:
        await connection.execute(
            "DELETE FROM knowledge_sources WHERE id = $1",
            source_id,
        )
        await connection.close()
