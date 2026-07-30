from scripts.validate_retrieval_gold import validate_cases


def test_gold_validation_rejects_duplicates_queries_and_query_strings():
    failures = validate_cases(
        [
            {
                "query": "Адрес",
                "expected_urls": ["https://vodc.ru/contacts/?from=test"],
            },
            {
                "query": "адрес",
                "expected_urls": ["https://vodc.ru/contacts/"],
            },
        ],
        minimum=2,
        maximum=2,
    )

    assert any("untrusted URL" in failure for failure in failures)
    assert any("duplicate query" in failure for failure in failures)
