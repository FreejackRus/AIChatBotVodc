import json
import hashlib
from datetime import date, timedelta

import httpx
import pytest

from app.ingestion import (
    KnowledgeIngestion,
    ManifestSource,
    chunk_text,
    load_manifest,
    normalize_content,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class FakeConnection:
    def __init__(self, timeline):
        self.timeline = timeline
        self.executed = []

    def transaction(self):
        return AsyncContext(self)

    async def execute(self, query, *args):
        self.executed.append((query, args))
        self.timeline.append("database-write")


class FakeIngestionPool:
    def __init__(self, existing, timeline):
        self.existing = existing
        self.timeline = timeline
        self.connection = FakeConnection(timeline)
        self.acquire_calls = 0

    async def fetch(self, _query):
        return self.existing

    def acquire(self):
        self.acquire_calls += 1
        self.timeline.append("transaction")
        return AsyncContext(self.connection)

    async def close(self):
        return None


def _write_manifest(path, sources):
    path.write_text(
        json.dumps({"version": 2, "sources": sources}, ensure_ascii=False),
        encoding="utf-8",
    )


def _source(**overrides):
    value = {
        "filename": "about.md",
        "title": "О центре",
        "url": "https://vodc.ru/about/",
        "owner": "ВОККДЦ",
        "reviewed_at": date.today().isoformat(),
        "local_path": "about.md",
        "enabled": True,
    }
    value.update(overrides)
    return value


def test_manifest_is_fail_closed_for_untrusted_or_duplicate_sources(tmp_path):
    manifest = tmp_path / "sources.json"
    _write_manifest(
        manifest,
        [
            _source(),
            _source(
                filename="other.md",
                url="https://evil.example/about/",
            ),
        ],
    )

    with pytest.raises(ValueError, match="allowlist"):
        load_manifest(manifest)

    _write_manifest(manifest, [_source(), _source()])
    with pytest.raises(ValueError, match="дублирует"):
        load_manifest(manifest)


def test_manifest_rejects_future_review_and_expires_old_sources(tmp_path):
    manifest = tmp_path / "sources.json"
    _write_manifest(
        manifest,
        [
            _source(
                reviewed_at=(date.today() + timedelta(days=1)).isoformat(),
            )
        ],
    )
    with pytest.raises(ValueError, match="будущем"):
        load_manifest(manifest)

    _write_manifest(
        manifest,
        [_source(reviewed_at=(date.today() - timedelta(days=181)).isoformat())],
    )
    source = load_manifest(manifest)[0]
    assert source.active(180) is False


def test_chunking_is_normalized_deterministic_and_overlapping():
    text = "# Заголовок\r\n\r\n" + ("Первый абзац. " * 30) + "\n\nВторой абзац."

    first = chunk_text(text, chunk_size=180, overlap=30)
    second = chunk_text(text, chunk_size=180, overlap=30)

    assert first == second
    assert len(first) > 1
    assert all(chunk and "\r" not in chunk for chunk in first)
    assert len(first[0]) <= 180


@pytest.mark.asyncio
async def test_embedding_batches_preserve_index_order_and_dimension(tmp_path):
    ingestion = KnowledgeIngestion(
        "postgresql://unused",
        "http://embedding:8000",
        "Qwen3-Embedding-0.6B",
        "test-revision",
        embedding_dimensions=3,
        embedding_batch_size=2,
        timeout=5,
        manifest_root=tmp_path,
        source_max_bytes=1000,
        source_max_age_days=180,
    )

    def handler(request):
        inputs = json.loads(request.content)["input"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [index + 0.1, 0.2, 0.3]}
                    for index, _ in reversed(list(enumerate(inputs)))
                ]
            },
        )

    await ingestion.http.aclose()
    ingestion.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    embeddings = await ingestion._embeddings(["a", "b", "c"])
    await ingestion.http.aclose()

    assert len(embeddings) == 3
    assert embeddings[0] == (0.1, 0.2, 0.3)
    assert embeddings[1] == (1.1, 0.2, 0.3)


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_fails_before_database_update(tmp_path):
    ingestion = KnowledgeIngestion(
        "postgresql://unused",
        "http://embedding:8000",
        "Qwen3-Embedding-0.6B",
        "test-revision",
        embedding_dimensions=3,
        embedding_batch_size=16,
        timeout=5,
        manifest_root=tmp_path,
        source_max_bytes=1000,
        source_max_age_days=180,
    )

    def handler(_request):
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
        )

    await ingestion.http.aclose()
    ingestion.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="Размерность"):
        await ingestion._embeddings(["a"])
    await ingestion.http.aclose()


@pytest.mark.asyncio
async def test_ingestion_embeds_before_atomic_database_update(monkeypatch, tmp_path):
    content = "# Контакты\n\nПлощадь Ленина, 5а."
    (tmp_path / "contacts.md").write_text(content, encoding="utf-8")
    source = ManifestSource(
        filename="contacts.md",
        title="Контакты",
        url="https://vodc.ru/contacts/",
        owner="ВОККДЦ",
        reviewed_at=date.today(),
        local_path="contacts.md",
    )
    timeline = []
    pool = FakeIngestionPool([], timeline)

    async def create_pool(*_args, **_kwargs):
        return pool

    monkeypatch.setattr("app.ingestion.asyncpg.create_pool", create_pool)
    ingestion = KnowledgeIngestion(
        "postgresql://unused",
        "http://embedding:8000",
        "Qwen3-Embedding-0.6B",
        "test-revision",
        embedding_dimensions=3,
        embedding_batch_size=16,
        timeout=5,
        manifest_root=tmp_path,
        source_max_bytes=1000,
        source_max_age_days=180,
    )

    def handler(request):
        timeline.append("embedding")
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

    await ingestion.http.aclose()
    ingestion.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await ingestion.run([source], chunk_size=1000, overlap=200)

    assert result["changed"] == 1
    assert result["chunks"] == 1
    assert timeline.index("embedding") < timeline.index("transaction")
    assert any(
        "INSERT INTO knowledge_chunks" in query
        for query, _args in pool.connection.executed
    )


@pytest.mark.asyncio
async def test_unchanged_source_skips_embedding_and_chunk_replacement(
    monkeypatch, tmp_path
):
    content = "# Контакты\n\nПлощадь Ленина, 5а."
    normalized = normalize_content(content)
    chunks = chunk_text(content, 1000, 200)
    (tmp_path / "contacts.md").write_text(content, encoding="utf-8")
    source = ManifestSource(
        filename="contacts.md",
        title="Контакты",
        url="https://vodc.ru/contacts/",
        owner="ВОККДЦ",
        reviewed_at=date.today(),
        local_path="contacts.md",
    )
    existing = [
        {
            "url": source.url,
            "content_hash": hashlib.sha256(normalized.encode()).hexdigest(),
            "embedding_model": "Qwen3-Embedding-0.6B",
            "embedding_revision": "test-revision",
            "embedding_dimensions": 3,
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "chunk_count": len(chunks),
        }
    ]
    pool = FakeIngestionPool(existing, [])

    async def create_pool(*_args, **_kwargs):
        return pool

    monkeypatch.setattr("app.ingestion.asyncpg.create_pool", create_pool)
    ingestion = KnowledgeIngestion(
        "postgresql://unused",
        "http://embedding:8000",
        "Qwen3-Embedding-0.6B",
        "test-revision",
        embedding_dimensions=3,
        embedding_batch_size=16,
        timeout=5,
        manifest_root=tmp_path,
        source_max_bytes=1000,
        source_max_age_days=180,
    )

    def handler(_request):
        raise AssertionError("unchanged source must not call embedding API")

    await ingestion.http.aclose()
    ingestion.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await ingestion.run([source], chunk_size=1000, overlap=200)

    assert result["changed"] == 0
    assert result["unchanged"] == 1
    assert not any(
        "INSERT INTO knowledge_chunks" in query
        for query, _args in pool.connection.executed
    )
