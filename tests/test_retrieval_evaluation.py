import pytest

from app.domain.models import SourceRef
from scripts.evaluate_retrieval import evaluate


class FakeKnowledge:
    async def search(self, query, limit):
        if "адрес" in query:
            return [
                SourceRef(
                    id="1",
                    title="Контакты",
                    url="https://vodc.ru/contacts/",
                    excerpt="Адрес",
                )
            ][:limit]
        return []


@pytest.mark.asyncio
async def test_retrieval_evaluation_calculates_recall_and_critical_failures():
    report = await evaluate(
        [
            {
                "query": "Какой адрес?",
                "expected_urls": ["https://vodc.ru/contacts/"],
                "critical": True,
            },
            {
                "query": "Неизвестный вопрос",
                "expected_urls": ["https://vodc.ru/about/"],
                "critical": False,
            },
        ],
        FakeKnowledge(),
        5,
    )

    assert report["recall_at_k"] == 0.5
    assert report["critical_failures"] == 0
    assert report["results"][0]["recall"] == 1.0
