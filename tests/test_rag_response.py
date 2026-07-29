from pathlib import Path

import pytest

from app.adapters.knowledge import JsonKnowledgeAdapter


@pytest.mark.asyncio
async def test_local_rag_returns_allowlisted_sources():
    knowledge_base = Path(__file__).resolve().parents[1] / "knowledge_base"
    adapter = JsonKnowledgeAdapter(
        knowledge_base,
        knowledge_base / "sources.json",
    )

    result = await adapter.search("Где находится центр на площади Ленина?", 5)

    assert result
    assert result[0].id.startswith("vodc_complete_info.md:")
    assert result[0].title == "Официальная информация ВОККДЦ"
    assert result[0].url == "https://vodc.ru/"
    assert result[0].excerpt
