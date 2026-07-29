import json

from app.domain.models import Service
from app.domain.priorities import ServicePrioritizer


def test_configured_catalog_is_fail_closed_and_prioritized(tmp_path):
    config = tmp_path / "priorities.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "allowed_service_ids": ["allowed-low", "allowed-high"],
                "rules": [
                    {"service_id": "allowed-high", "weight": 100},
                ],
            }
        ),
        encoding="utf-8",
    )
    prioritizer = ServicePrioritizer.from_file(config)

    result = prioritizer.rank(
        [
            Service(id="not-approved", title="Не согласована"),
            Service(id="allowed-low", title="Обычный приоритет"),
            Service(id="allowed-high", title="Высокий приоритет"),
        ]
    )

    assert [service.id for service in result] == ["allowed-high", "allowed-low"]


def test_empty_configured_catalog_returns_no_services(tmp_path):
    config = tmp_path / "priorities.json"
    config.write_text(
        '{"version": 1, "allowed_service_ids": [], "rules": []}',
        encoding="utf-8",
    )

    result = ServicePrioritizer.from_file(config).rank(
        [Service(id="service-1", title="МРТ")]
    )

    assert result == []
