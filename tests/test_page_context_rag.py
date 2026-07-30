from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.adapters.knowledge import LocalKnowledgeAdapter
from app.domain.models import RetrievalContext
from app.domain.retrieval import canonical_vodc_page_key


def _manifest(tmp_path):
    reviewed_at = datetime.now(UTC).date().isoformat()
    (tmp_path / "about.md").write_text(
        "ВОККДЦ оказывает специализированную медицинскую помощь.",
        encoding="utf-8",
    )
    (tmp_path / "contacts.md").write_text(
        "Телефон регистратуры центра: официальный номер на странице контактов.",
        encoding="utf-8",
    )
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 2,
                "sources": [
                    {
                        "filename": "about.md",
                        "title": "О центре",
                        "url": "https://vodc.ru/about/",
                        "owner": "ВОККДЦ",
                        "reviewed_at": reviewed_at,
                        "local_path": "about.md",
                    },
                    {
                        "filename": "contacts.md",
                        "title": "Контакты",
                        "url": "https://vodc.ru/contacts/",
                        "owner": "ВОККДЦ",
                        "reviewed_at": reviewed_at,
                        "local_path": "contacts.md",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest


def test_canonical_page_key_collapses_www_query_fragment_and_trailing_slash():
    assert canonical_vodc_page_key(
        "https://www.vodc.ru/about/?utm_source=chat#details"
    ) == "https://vodc.ru/about"
    assert canonical_vodc_page_key("http://vodc.ru/about/") is None
    assert canonical_vodc_page_key("https://evil.example/about/") is None


@pytest.mark.asyncio
async def test_local_retrieval_uses_approved_current_page_for_ambiguous_query(
    tmp_path,
):
    adapter = LocalKnowledgeAdapter(
        _manifest(tmp_path),
        chunk_size=1000,
        overlap=200,
        source_max_age_days=180,
        source_max_bytes=2_000_000,
        excerpt_chars=800,
        context_boost=0.15,
    )

    result = await adapter.search(
        "Что здесь?",
        3,
        RetrievalContext(
            page_url="https://www.vodc.ru/about/?utm_source=chat#details"
        ),
    )

    assert result
    assert result[0].url == "https://vodc.ru/about/"
    assert result[0].score == 0.15


@pytest.mark.asyncio
async def test_relevant_global_result_beats_unrelated_current_page(tmp_path):
    adapter = LocalKnowledgeAdapter(
        _manifest(tmp_path),
        chunk_size=1000,
        overlap=200,
        source_max_age_days=180,
        source_max_bytes=2_000_000,
        excerpt_chars=800,
        context_boost=0.15,
    )

    result = await adapter.search(
        "Какой телефон регистратуры?",
        3,
        RetrievalContext(page_url="https://vodc.ru/about/"),
    )

    assert result[0].url == "https://vodc.ru/contacts/"
    assert result[0].score > result[1].score


@pytest.mark.asyncio
async def test_unapproved_page_cannot_inject_context_into_local_retrieval(tmp_path):
    adapter = LocalKnowledgeAdapter(
        _manifest(tmp_path),
        chunk_size=1000,
        overlap=200,
        source_max_age_days=180,
        source_max_bytes=2_000_000,
        excerpt_chars=800,
    )

    result = await adapter.search(
        "Что здесь?",
        3,
        RetrievalContext(page_url="https://evil.example/about/"),
    )

    assert result == []
