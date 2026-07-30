from pathlib import Path

import pytest

from app.adapters.knowledge import LocalKnowledgeAdapter


@pytest.mark.asyncio
async def test_rag_initialization_and_search_do_not_modify_snapshots():
    knowledge_dir = Path(__file__).resolve().parents[1] / "knowledge_base"
    before = {
        path: path.read_bytes()
        for path in knowledge_dir.glob("*.md")
    }

    adapter = LocalKnowledgeAdapter(
        knowledge_dir / "sources.json",
        chunk_size=1000,
        overlap=200,
        source_max_age_days=180,
        source_max_bytes=2_000_000,
        excerpt_chars=800,
    )
    assert adapter.chunks
    await adapter.search("ВОККДЦ", 3)

    assert {path: path.read_bytes() for path in knowledge_dir.glob("*.md")} == before
