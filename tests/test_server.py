from __future__ import annotations

from typing import Any

import pytest

from yoshkar_ola_public_mcp import server


SCHOOL_ITEM = {
    "display_order": 1,
    "inn": "1215066204",
    "legal_address": "424038, Йошкар-Ола, Ленинский проспект, дом 10А",
    "address": "424038, Йошкар-Ола, Ленинский проспект, дом 10А",
    "phone": "8(8362)21-56-88",
    "email": "yola.sosh29@mari-el.gov.ru",
    "website": "http://edu.mari.ru/mouo-yoshkarola/sh29/default.aspx",
    "fns_kpp": "121501001",
    "fns_ogrn": "1021200761438",
    "fns_full_name": "Муниципальное бюджетное общеобразовательное учреждение Школа № 29",
    "fns_short_name": "МБОУ Школа № 29",
    "fns_entity_type": "legal_entity",
    "fns_registration_date": "2002-10-27",
    "fns_region_name": "Республика Марий Эл",
    "fns_status": "Действующая",
    "fns_address": None,
    "fns_head_position": "Директор",
    "fns_head_name": "Кузнецов Александр Иванович",
    "license_number": "Л035-01267-12/00272543",
    "license_date": "2019-05-20",
    "license_order": "Приказ от 20.05.2019 №505",
    "license_term": "Бессрочная",
    "license_status": "Действующая",
    "license_issuing_organ": "Министерство образования и науки Республики Марий Эл",
    "fns_head_raw": "ДИРЕКТОР: Кузнецов Александр Иванович",
    "fns_fetched_at": "2026-05-25T02:08:48Z",
    "license_source_url": "https://example.invalid/license",
}

KINDERGARTEN_ITEM = {
    **SCHOOL_ITEM,
    "display_order": 2,
    "inn": "1215000001",
    "fns_full_name": "Муниципальное дошкольное образовательное учреждение Детский сад Пчелка",
    "fns_short_name": "МДОУ Детский сад Пчелка",
    "address": "Йошкар-Ола, бульвар Чавайна, дом 1",
}


@pytest.fixture(autouse=True)
def fake_api(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads: dict[str, Any] = {
        "schools": {"data": [SCHOOL_ITEM]},
        "kindergartens": {"data": [KINDERGARTEN_ITEM]},
        "fns-egrul/last-update": {"last_updated_at": "2026-05-25T02:10:37Z"},
    }

    def get_json(path: str) -> Any:
        return payloads[path]

    monkeypatch.setattr(server, "_get_json", get_json)


def test_public_item_uses_allowlist_only() -> None:
    result = server.list_schools(limit=1, offset=0)

    item = result["items"][0]
    assert set(item) == set(server.PUBLIC_FIELDS)
    assert "fns_head_raw" not in item
    assert "fns_fetched_at" not in item
    assert "license_source_url" not in item


def test_pagination_clamps_limit_and_offset() -> None:
    result = server._paginate([{"id": i} for i in range(3)], limit=999, offset=-10)

    assert result["total"] == 3
    assert result["limit"] == 200
    assert result["offset"] == 0
    assert result["items"] == [{"id": 0}, {"id": 1}, {"id": 2}]


def test_search_schools_matches_name_address_and_inn() -> None:
    assert server.search_schools("Школа № 29", limit=5)["total"] == 1
    assert server.search_schools("Ленинский", limit=5)["total"] == 1
    assert server.search_schools("1215066204", limit=5)["total"] == 1
    assert server.search_schools("нет такого", limit=5)["total"] == 0


def test_search_kindergartens_matches_public_fields() -> None:
    result = server.search_kindergartens("Пчелка", limit=5)

    assert result["total"] == 1
    assert result["items"][0]["inn"] == "1215000001"


def test_get_by_inn_normalizes_input() -> None:
    result = server.get_school_by_inn(" 121-506-6204 ")

    assert result["found"] is True
    assert result["item"]["inn"] == "1215066204"


def test_get_by_inn_returns_not_found() -> None:
    result = server.get_kindergarten_by_inn("0000000000")

    assert result == {"found": False, "item": None}


def test_data_update_info_is_minimal() -> None:
    result = server.get_data_update_info()

    assert result == {
        "last_updated_at": "2026-05-25T02:10:37Z",
        "source": "Публичный API открытых данных городского округа",
    }


def test_server_info_exposes_versions_layers_and_update_commands() -> None:
    result = server.get_server_info()

    assert result["server_version"] == server.SERVER_VERSION
    assert result["skill_version"] == server.SKILL_VERSION
    assert result["npm_package"] == "@iola_adm/yoshkar-ola-public-mcp"
    assert result["guidance_resource_uri"] == server.GUIDANCE_RESOURCE_URI
    assert [layer["id"] for layer in result["data_layers"]] == ["schools", "kindergartens"]
    assert "install-skill codex" in result["update_commands"]["codex_skill"]


def test_guidance_text_mentions_server_info() -> None:
    guidance = server.open_data_guidance_resource()

    assert server.SKILL_VERSION in guidance
    assert "get_server_info" in guidance
    assert "муниципальные школы" in guidance
    assert server.open_data_guidance_prompt() == guidance


def test_main_stdio_uses_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(server.mcp, "run", fake_run)

    server.main_stdio()

    assert calls == [{"transport": "stdio"}]
