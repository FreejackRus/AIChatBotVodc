import uuid

import httpx
import pytest

from app.catalog_audit import (
    CatalogAuditError,
    PreviousCatalog,
    VodcCatalogAuditor,
    compare_catalogs,
    parse_catalog_html,
)


def _catalog_html(*rows: str, title: str = "Прейскурант") -> str:
    return (
        "<html><head><title>"
        + title
        + "</title></head><body><table id='priceTable'>"
        + "".join(rows)
        + "</table></body></html>"
    )


def _category(depth: int, name: str) -> str:
    return (
        f"<tr class='pricetable-parent-child' data-depth='{depth}'>"
        f"<td>{name}</td></tr>"
    )


def _service(code: str, name: str, price: str, href: str) -> str:
    return (
        "<tr class='pricetable-child'>"
        f"<td>{code}</td><td><a href='{href}'>{name}</a></td>"
        f"<td>{price}</td></tr>"
    )


def test_catalog_parser_preserves_hierarchy_and_many_to_many_service_codes():
    html = _catalog_html(
        _category(2, "Консультации (2 услуги)"),
        _category(3, "Аллергология (1 услуги)"),
        _service(
            "0000000114",
            "Консультация аллерголога",
            "от 2 000 ₽",
            "/308/0000000114_308/",
        ),
        _category(3, "Иммунология (1 услуги)"),
        _service(
            "0000000114",
            "Консультация аллерголога",
            "от 2 000 ₽",
            "/309/0000000114_309/",
        ),
        _category(4, "Аппарат МРТ (1 услуга)"),
        _category(5, "МРТ всего тела (1 услуга)"),
        _service(
            "0000009999",
            "Другая услуга",
            "1 500 ₽",
            "/309/0000009999_309/",
        ),
    )

    parsed = parse_catalog_html(
        html,
        "https://www.vodc.ru/pacientam/platnye/platnye.php",
        minimum_services=2,
    )

    assert len(parsed.observations) == 3
    assert parsed.service_codes == {"0000000114", "0000009999"}
    first = parsed.observations[0]
    assert first.price_min_rub == 2000
    assert first.category_path == ("Консультации", "Аллергология")
    assert first.detail_url == "https://www.vodc.ru/308/0000000114_308/"
    assert parsed.observations[-1].category_path == (
        "Консультации",
        "Иммунология",
        "Аппарат МРТ",
        "МРТ всего тела",
    )
    assert parsed.issues == ()


def test_catalog_parser_quarantines_untrusted_links_and_small_snapshots():
    html = _catalog_html(
        _category(2, "Консультации (1 услуга)"),
        _service(
            "0000000114",
            "Консультация",
            "2 000 ₽",
            "https://evil.example/service",
        ),
    )

    parsed = parse_catalog_html(
        html,
        "https://vodc.ru/pacientam/platnye/platnye.php",
        minimum_services=1000,
    )

    assert {
        (issue.code, issue.severity)
        for issue in parsed.issues
    } == {
        ("untrusted_detail_url", "critical"),
        ("service_count_below_threshold", "critical"),
    }


def test_catalog_parser_fails_closed_without_expected_table():
    with pytest.raises(CatalogAuditError, match="priceTable"):
        parse_catalog_html(
            "<html><title>Активация продукта</title></html>",
            "https://vodc.ru/uslygi/",
            minimum_services=1,
        )


def test_catalog_parser_uses_first_amount_for_price_range():
    parsed = parse_catalog_html(
        _catalog_html(
            _service(
                "0000000001",
                "Услуга с диапазоном",
                "от 1 500 до 2 500 ₽",
                "/1/0000000001_1/",
            )
        ),
        "https://vodc.ru/pacientam/platnye/platnye.php",
        minimum_services=1,
    )

    assert parsed.observations[0].price_min_rub == 1500


def test_catalog_comparison_detects_removal_spike():
    current = parse_catalog_html(
        _catalog_html(
            _service(
                "0000000001",
                "Первая услуга",
                "100 ₽",
                "/1/0000000001_1/",
            )
        ),
        "https://vodc.ru/pacientam/platnye/platnye.php",
        minimum_services=1,
    )
    previous = PreviousCatalog(
        run_id=uuid.uuid4(),
        service_count=2,
        etag=None,
        last_modified=None,
        fingerprints={
            "0000000001": current.fingerprints["0000000001"],
            "0000000002": ("old-hash",),
        },
    )

    stats, issues = compare_catalogs(
        current,
        previous,
        max_removed_ratio=0.2,
    )

    assert stats["removed"] == 1
    assert stats["removed_ratio"] == 0.5
    assert [issue.code for issue in issues] == ["service_removal_spike"]


@pytest.mark.asyncio
async def test_catalog_fetch_is_bounded_and_requires_html():
    auditor = VodcCatalogAuditor(
        "postgresql://unused",
        "https://vodc.ru/pacientam/platnye/platnye.php",
        timeout=5,
        maximum_bytes=32,
        minimum_services=1,
        max_removed_ratio=0.2,
    )

    def handler(_request):
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"not html",
        )

    await auditor.http.aclose()
    auditor.http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    with pytest.raises(CatalogAuditError, match="Content-Type"):
        await auditor._fetch(None)
    await auditor.close()
