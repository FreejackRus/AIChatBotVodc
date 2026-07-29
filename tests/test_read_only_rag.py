import hashlib
from pathlib import Path

import pytest

from app.adapters.knowledge import JsonKnowledgeAdapter


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.asyncio
async def test_rag_initialization_and_search_do_not_modify_index():
    knowledge_dir = Path(__file__).resolve().parents[1] / "knowledge_base"
    store = knowledge_dir / "vector_store.json"
    before = file_hash(store)

    adapter = JsonKnowledgeAdapter(knowledge_dir, knowledge_dir / "sources.json")
    assert len(adapter.documents) == 24
    await adapter.search("ВОККДЦ", 3)

    assert file_hash(store) == before
