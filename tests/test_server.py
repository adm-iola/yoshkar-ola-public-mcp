from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.testclient import TestClient

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


def test_version_payload_is_shared_by_server_info_and_http_routes() -> None:
    payload = server._version_payload()

    assert payload["server_version"] == server.SERVER_VERSION
    assert payload["skill_version"] == server.SKILL_VERSION
    assert payload["contract_version"] == server.CONTRACT_VERSION
    assert payload["npm_package"] == "@iola_adm/yoshkar-ola-public-mcp"
    assert [layer["id"] for layer in payload["data_layers"]] == ["schools", "kindergartens"]
    assert "layer_answer_context" in payload["capabilities"]


def test_contract_info_exposes_layer_capabilities() -> None:
    result = server.get_contract_info()

    assert result["contract_version"] == server.CONTRACT_VERSION
    assert result["layer_count"] == 2
    assert "layer_suggest" in result["tools"]
    assert "quality_summary" in result["tools"]
    assert server.LAYERS_RESOURCE_URI in result["resources"]


def test_layer_registry_files_match_schema_requirements() -> None:
    schema = json.loads(server.LAYER_SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema["required"])

    for file_path in server.LAYERS_DIR.glob("*.json"):
        layer = json.loads(file_path.read_text(encoding="utf-8"))
        assert required.issubset(layer)
        server._validate_layer_definition(layer, file_path)


def test_list_data_layers_returns_available_layers() -> None:
    result = server.list_data_layers()

    assert result["total"] == 2
    assert [item["id"] for item in result["items"]] == ["schools", "kindergartens"]


def test_layer_list_returns_search_schemas_and_filters_category() -> None:
    result = server.layer_list(category="образование")

    assert result["total"] == 2
    assert result["items"][0]["id"] == "schools"
    assert result["items"][0]["endpoint"] == "schools"
    assert "fns_head_name" in result["items"][0]["search_fields"]
    assert result["items"][1]["id"] == "kindergartens"
    assert server.layer_list(category="нет") == {"total": 0, "items": []}


def test_layer_schema_returns_one_layer() -> None:
    result = server.layer_schema("schools")

    assert result["id"] == "schools"
    assert result["category"] == "Образование"
    assert "школ" in result["aliases"]
    assert "display_fields" in result
    assert result["weighted_fields"]["fns_head_name"] == 10


def test_layer_query_scores_head_name_matches() -> None:
    result = server.layer_query("schools", "в какой школе директор Кузнецов", limit=5)

    assert result["layer"]["id"] == "schools"
    assert result["terms"] == ["кузнецов"]
    assert result["total"] == 1
    assert result["items"][0]["inn"] == "1215066204"
    assert result["items"][0]["_match"]["confidence"] > 0
    assert "fns_head_name" in result["items"][0]["_match"]["matched_fields"]


def test_layer_get_returns_by_inn_or_query() -> None:
    by_inn = server.layer_get("kindergartens", inn="1215-000001")
    by_query = server.layer_get("kindergartens", query="Пчелка")

    assert by_inn["found"] is True
    assert by_inn["item"]["inn"] == "1215000001"
    assert by_query["found"] is True
    assert by_query["item"]["fns_short_name"] == "МДОУ Детский сад Пчелка"


def test_open_data_layers_resource_matches_layer_list() -> None:
    assert server.open_data_layers_resource() == server.layer_list()


def test_layer_suggest_routes_school_questions() -> None:
    result = server.layer_suggest("в какой школе директор Кузнецов")

    assert result["items"][0]["layer"]["id"] == "schools"
    assert result["items"][0]["confidence"] > 0


def test_layer_answer_context_returns_facts_and_guidance() -> None:
    result = server.layer_answer_context("в какой школе директор Кузнецов", limit=2)

    assert result["contract_version"] == server.CONTRACT_VERSION
    assert result["answer_type"] == "single_match"
    assert result["needs_clarification"] is False
    assert result["confidence_summary"]["max"] > 0
    assert result["facts"][0]["layer"] == "schools"
    assert result["facts"][0]["head"] == "Кузнецов Александр Иванович"
    assert "Кузнецов Александр Иванович" in result["recommended_answer_ru"]
    assert "Не добавляй реквизиты" in result["answer_guidance"]


def test_layer_answer_context_no_match() -> None:
    result = server.layer_answer_context("школа с директором Несуществующий", layer="schools", limit=2)

    assert result["answer_type"] == "no_match"
    assert result["facts"] == []
    assert result["recommended_answer_ru"] == "В доступных открытых данных такие сведения не найдены."


def test_layer_stats_facets_and_quality_tools() -> None:
    stats = server.layer_stats("schools")
    facets = server.layer_facets("schools", "fns_head_name")
    summary = server.quality_summary()
    findings = server.quality_findings(layer="schools")

    assert stats["total"] == 1
    assert stats["with_phone"] == 1
    assert facets["items"] == [{"value": "Кузнецов Александр Иванович", "count": 1}]
    assert summary["total_findings"] >= 0
    assert "items" in findings


def test_mcp_diagnostics_payload() -> None:
    result = server.mcp_diagnostics()

    assert result["status"] == "ok"
    assert result["api_status"] == "ok"
    assert result["version"]["server_version"] == server.SERVER_VERSION
    assert "layer_stats" in result["tools"]
    assert result["cache"]["entries"] >= 0


def test_search_all_searches_every_available_layer() -> None:
    result = server.search_all("Пчелка", limit_per_layer=500)

    assert result["limit_per_layer"] == 50
    assert result["layers_searched"] == 2
    assert result["total"] == 1
    assert result["results"][0]["layer"]["id"] == "schools"
    assert result["results"][0]["total"] == 0
    assert result["results"][1]["layer"]["id"] == "kindergartens"
    assert result["results"][1]["total"] == 1
    assert result["results"][1]["items"][0]["inn"] == "1215000001"


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


def test_http_health_and_version_routes() -> None:
    app = server.mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=True)

    with TestClient(app) as client:
        health = client.get("/mcp-health")
        version = client.get("/mcp-version")
        diagnostics = client.get("/mcp-diagnostics")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["api_status"] == "ok"
    assert "metrics" in health.json()
    assert health.json()["server_version"] == server.SERVER_VERSION
    assert version.status_code == 200
    assert version.json()["server_version"] == server.SERVER_VERSION
    assert "status" not in version.json()
    assert diagnostics.status_code == 200
    assert diagnostics.json()["version"]["server_version"] == server.SERVER_VERSION
