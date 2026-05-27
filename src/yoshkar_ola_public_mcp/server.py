from __future__ import annotations

import os
import time
import json
from pathlib import Path
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

API_BASE_URL = os.getenv("CPR_PUBLIC_API_BASE_URL", "https://apiiola.yasg.ru/api/v1").rstrip("/")
HTTP_TIMEOUT_SECONDS = float(os.getenv("CPR_PUBLIC_API_TIMEOUT", "20"))
CACHE_TTL_SECONDS = int(os.getenv("CPR_PUBLIC_API_CACHE_TTL", "300"))
SERVER_VERSION = "0.1.8"
SKILL_VERSION = "0.1.8"
CONTRACT_VERSION = "2026-05-27"
NPM_PACKAGE = "@iola_adm/yoshkar-ola-public-mcp"
GUIDANCE_RESOURCE_URI = "yoshkar-ola://guidance/open-data"
LAYERS_RESOURCE_URI = "yoshkar-ola://layers"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
LAYERS_DIR = PACKAGE_ROOT / "layers"
LAYER_SCHEMA_PATH = PACKAGE_ROOT / "schemas" / "layer.schema.json"

DatasetName = Literal["schools", "kindergartens"]

def _load_layer_registry() -> tuple[dict[str, Any], ...]:
    layers: list[dict[str, Any]] = []
    for file_path in sorted(LAYERS_DIR.glob("*.json")):
        with file_path.open("r", encoding="utf-8") as file:
            layer = json.load(file)
        _validate_layer_definition(layer, file_path)
        layer.setdefault("aliases", [])
        layer.setdefault("search_fields", [])
        layer.setdefault("person_fields", [])
        layer.setdefault("source_fields", ["id", "name", "inn"])
        layer.setdefault("display_fields", layer["search_fields"])
        layer.setdefault("exact_fields", ["inn"])
        layer.setdefault("weighted_fields", {})
        layer.setdefault("answer_templates", {})
        layers.append(layer)
    return tuple(sorted(layers, key=lambda item: (int(item.get("display_order") or 999), str(item.get("id") or ""))))


def _validate_layer_definition(layer: dict[str, Any], file_path: Path | None = None) -> None:
    required = {
        "id", "display_order", "name", "status", "category", "endpoint", "aliases",
        "search_fields", "person_fields", "source_fields", "display_fields",
        "exact_fields", "weighted_fields", "answer_templates",
    }
    missing = sorted(required - set(layer))
    if missing:
        raise ValueError(f"Layer {file_path or layer.get('id')}: missing required fields: {', '.join(missing)}")
    if layer["status"] not in {"available", "planned", "disabled"}:
        raise ValueError(f"Layer {file_path or layer.get('id')}: invalid status {layer['status']}")
    for field in ("aliases", "search_fields", "person_fields", "source_fields", "display_fields", "exact_fields"):
        if not isinstance(layer[field], list):
            raise ValueError(f"Layer {file_path or layer.get('id')}: {field} must be a list")
    if not layer["search_fields"] or not layer["display_fields"]:
        raise ValueError(f"Layer {file_path or layer.get('id')}: search_fields and display_fields must not be empty")
    if not isinstance(layer["weighted_fields"], dict):
        raise ValueError(f"Layer {file_path or layer.get('id')}: weighted_fields must be an object")
    templates = layer["answer_templates"]
    if not isinstance(templates, dict) or not templates.get("single") or not templates.get("multiple"):
        raise ValueError(f"Layer {file_path or layer.get('id')}: answer_templates.single and multiple are required")


DATA_LAYERS = _load_layer_registry()
DATA_LAYER_BY_ID = {layer["id"]: layer for layer in DATA_LAYERS}

PUBLIC_FIELDS = (
    "display_order",
    "inn",
    "legal_address",
    "address",
    "phone",
    "email",
    "website",
    "fns_kpp",
    "fns_ogrn",
    "fns_full_name",
    "fns_short_name",
    "fns_entity_type",
    "fns_registration_date",
    "fns_region_name",
    "fns_status",
    "fns_address",
    "fns_head_position",
    "fns_head_name",
    "license_number",
    "license_date",
    "license_order",
    "license_term",
    "license_status",
    "license_issuing_organ",
)

_cache: dict[str, tuple[float, Any]] = {}
_cache_meta: dict[str, dict[str, Any]] = {}
_metrics: dict[str, Any] = {
    "started_at": time.time(),
    "requests": {},
    "cache": {"hits": 0, "misses": 0, "stale_hits": 0},
}


def _record_metric(name: str, started_at: float, ok: bool) -> None:
    entry = _metrics["requests"].setdefault(name, {"count": 0, "errors": 0, "total_ms": 0.0, "last_ms": 0.0})
    elapsed_ms = round((time.time() - started_at) * 1000, 2)
    entry["count"] += 1
    entry["total_ms"] = round(entry["total_ms"] + elapsed_ms, 2)
    entry["last_ms"] = elapsed_ms
    if not ok:
        entry["errors"] += 1


def _get_json(path: str) -> Any:
    now = time.time()
    cached = _cache.get(path)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        _metrics["cache"]["hits"] += 1
        _cache_meta[path] = {"cached_at": cached[0], "stale": False}
        return cached[1]

    url = f"{API_BASE_URL}/{path.lstrip('/')}"
    _metrics["cache"]["misses"] += 1
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        if cached:
            _metrics["cache"]["stale_hits"] += 1
            _cache_meta[path] = {"cached_at": cached[0], "stale": True}
            return cached[1]
        raise

    _cache[path] = (now, data)
    _cache_meta[path] = {"cached_at": now, "stale": False}
    return data


def _dataset_path(dataset: str) -> str:
    if dataset not in DATA_LAYER_BY_ID:
        raise ValueError(f"Unknown dataset: {dataset}")
    return str(DATA_LAYER_BY_ID[dataset]["endpoint"])


def _load_items(dataset: str) -> list[dict[str, Any]]:
    payload = _get_json(_dataset_path(dataset))
    items = payload.get("data", [])
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected API response for {dataset}")
    return [_public_item(item) for item in items if isinstance(item, dict)]


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {field: item.get(field) for field in PUBLIC_FIELDS}


def _matches(item: dict[str, Any], query: str) -> bool:
    needle = query.strip().casefold()
    if not needle:
        return True

    haystack = " ".join(
        str(item.get(field) or "")
        for field in (
            "inn",
            "fns_full_name",
            "fns_short_name",
            "fns_head_name",
            "fns_head_position",
            "legal_address",
            "address",
            "email",
            "website",
    )
    ).casefold()
    return needle in haystack


def _layer_schema(layer_id: str) -> dict[str, Any]:
    if layer_id not in DATA_LAYER_BY_ID:
        raise ValueError(f"Unknown layer: {layer_id}")
    layer = DATA_LAYER_BY_ID[layer_id]
    return {
        "id": layer["id"],
        "display_order": layer.get("display_order"),
        "name": layer["name"],
        "status": layer["status"],
        "category": layer["category"],
        "endpoint": layer["endpoint"],
        "aliases": layer["aliases"],
        "search_fields": layer["search_fields"],
        "person_fields": layer["person_fields"],
        "source_fields": layer["source_fields"],
        "display_fields": layer["display_fields"],
        "exact_fields": layer["exact_fields"],
        "weighted_fields": layer["weighted_fields"],
    }


def _list_layer_schemas(category: str | None = None) -> list[dict[str, Any]]:
    normalized_category = (category or "").strip().casefold()
    schemas = [_layer_schema(str(layer["id"])) for layer in DATA_LAYERS]
    if normalized_category:
        schemas = [
            schema
            for schema in schemas
            if str(schema.get("category") or "").casefold() == normalized_category
        ]
    return schemas


def _extract_terms(query: str) -> list[str]:
    stop_words = {
        "в", "во", "на", "по", "и", "а", "ну", "так", "слушай", "скажи", "подскажи",
        "какие", "какая", "какой", "каком", "есть", "найди", "покажи", "контакты",
        "адрес", "телефон", "школы", "школа", "школе", "сад", "детский", "детские",
        "сады", "улица", "ул", "директор", "руководитель",
    }
    cleaned = "".join(ch.casefold() if ch.isalnum() else " " for ch in query)
    return [term for term in cleaned.split() if (term not in stop_words and (len(term) > 2 or term.isdigit()))]


def _score_item(item: dict[str, Any], terms: list[str], layer: dict[str, Any] | None = None) -> dict[str, Any]:
    if not terms:
        return {"score": 1, "matched_fields": []}
    active_layer = layer or {}
    search_fields = active_layer.get("search_fields") or PUBLIC_FIELDS
    weighted_fields = active_layer.get("weighted_fields") or {}
    exact_fields = active_layer.get("exact_fields") or []
    score = 0
    matched_fields: set[str] = set()
    for term in terms:
        for field in search_fields:
            value = str(item.get(field) or "").casefold()
            if not value:
                continue
            weight = int(weighted_fields.get(field, 1))
            if field in exact_fields and term == value:
                score += weight * 3
                matched_fields.add(field)
            elif term in value:
                score += weight
                matched_fields.add(field)
    confidence = min(1.0, round(score / max(len(terms) * 10, 1), 2))
    return {"score": score, "matched_fields": sorted(matched_fields), "confidence": confidence}


def _query_layer(layer_id: str, query: str, limit: int = 20) -> dict[str, Any]:
    if layer_id not in DATA_LAYER_BY_ID:
        raise ValueError(f"Unknown layer: {layer_id}")
    started_at = time.time()
    ok = False
    layer = DATA_LAYER_BY_ID[layer_id]
    terms = _extract_terms(query)
    scored = []
    for item in _load_items(layer_id):
        match = _score_item(item, terms, layer)
        scored.append({"item": item, **match})
    items = [
        {
            **entry["item"],
            "_match": {
                "score": entry["score"],
                "confidence": entry["confidence"],
                "matched_fields": entry["matched_fields"],
            },
        }
        for entry in sorted(scored, key=lambda entry: entry["score"], reverse=True)
        if entry["score"] > 0
    ]
    page = _paginate(items, limit=limit, offset=0)
    ok = True
    result = {
        "layer": _layer_schema(layer_id),
        "query": query,
        "terms": terms,
        "total": page["total"],
        "limit": page["limit"],
        "items": page["items"],
    }
    _record_metric("layer_query", started_at, ok)
    return result


def _get_layer_item(layer_id: str, inn: str = "", query: str = "") -> dict[str, Any]:
    if layer_id not in DATA_LAYER_BY_ID:
        raise ValueError(f"Unknown layer: {layer_id}")

    normalized_inn = "".join(ch for ch in str(inn) if ch.isdigit())
    if normalized_inn:
        return _get_by_inn(layer_id, normalized_inn)

    cleaned_query = query.strip()
    if not cleaned_query:
        return {"found": False, "item": None}

    result = _query_layer(layer_id, cleaned_query, limit=1)
    items = result["items"]
    return {"found": bool(items), "item": items[0] if items else None}


def _suggest_layers(query: str, limit: int = 5) -> dict[str, Any]:
    terms = _extract_terms(query)
    normalized = query.casefold()
    suggestions = []
    for layer in DATA_LAYERS:
        score = 0
        matched_aliases = []
        for alias in layer.get("aliases", []):
            if str(alias).casefold() in normalized:
                score += 10
                matched_aliases.append(alias)
        for term in terms:
            if term in str(layer.get("name", "")).casefold() or term in str(layer.get("category", "")).casefold():
                score += 3
        if score > 0:
            suggestions.append({
                "layer": _layer_schema(str(layer["id"])),
                "score": score,
                "confidence": min(1.0, round(score / 20, 2)),
                "matched_aliases": matched_aliases,
            })
    suggestions.sort(key=lambda item: item["score"], reverse=True)
    if not suggestions:
        suggestions = [{"layer": _layer_schema(str(layer["id"])), "score": 1, "confidence": 0.1, "matched_aliases": []} for layer in DATA_LAYERS]
    return {"query": query, "total": len(suggestions), "items": suggestions[: max(1, min(int(limit), 20))]}


def _answer_context(question: str, layer: str = "", limit: int = 5) -> dict[str, Any]:
    target_layers = [layer] if layer else [item["layer"]["id"] for item in _suggest_layers(question)["items"]]
    results = []
    facts = []
    for layer_id in target_layers:
        query_result = _query_layer(layer_id, question, limit=limit)
        results.append(query_result)
        for item in query_result["items"]:
            facts.append({
                "layer": layer_id,
                "title": item.get("fns_short_name") or item.get("fns_full_name") or item.get("inn"),
                "inn": item.get("inn"),
                "address": item.get("address") or item.get("legal_address"),
                "phone": item.get("phone"),
                "email": item.get("email"),
                "website": item.get("website"),
                "head": item.get("fns_head_name"),
                "match": item.get("_match"),
            })
    return {
        "question": question,
        "contract_version": CONTRACT_VERSION,
        "layers": target_layers,
        "facts": facts[: max(1, min(int(limit), 20))],
        "sources": [{"type": "mcp", "server": "Yoshkar-Ola Public Data", "endpoint": "https://apiiola.yasg.ru/mcp"}],
        "results": results,
        "answer_type": _answer_type(facts),
        "needs_clarification": len(facts) > 1,
        "confidence_summary": _confidence_summary(facts),
        "missing_fields": _missing_fields(facts),
        "recommended_answer_ru": _recommended_answer(question, facts),
        "answer_guidance": (
            "Отвечай только на основе facts/results. Если facts пустой, скажи, что в доступных открытых данных сведения не найдены. "
            "Не добавляй реквизиты, которых нет в MCP-ответе."
        ),
    }


def _answer_type(facts: list[dict[str, Any]]) -> str:
    if not facts:
        return "no_match"
    if len(facts) == 1:
        return "single_match"
    return "multiple_matches"


def _confidence_summary(facts: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(fact.get("match", {}).get("confidence") or 0) for fact in facts]
    if not values:
        return {"max": 0, "average": 0}
    return {"max": max(values), "average": round(sum(values) / len(values), 2)}


def _missing_fields(facts: list[dict[str, Any]]) -> list[str]:
    important = ("title", "address", "phone", "email", "website", "inn", "head")
    missing: set[str] = set()
    for fact in facts:
        for field in important:
            if not fact.get(field):
                missing.add(field)
    return sorted(missing)


def _recommended_answer(question: str, facts: list[dict[str, Any]]) -> str:
    if not facts:
        return "В доступных открытых данных такие сведения не найдены."
    if len(facts) > 1:
        names = "; ".join(str(fact.get("title") or fact.get("inn")) for fact in facts[:5])
        return f"Найдено несколько подходящих записей: {names}. Уточните, какая организация нужна."
    fact = facts[0]
    parts = [str(fact.get("title") or "Организация")]
    if fact.get("head"):
        parts.append(f"руководитель: {fact['head']}")
    if fact.get("address"):
        parts.append(f"адрес: {fact['address']}")
    if fact.get("phone"):
        parts.append(f"телефон: {fact['phone']}")
    if fact.get("email"):
        parts.append(f"email: {fact['email']}")
    if fact.get("website"):
        parts.append(f"сайт: {fact['website']}")
    if fact.get("inn"):
        parts.append(f"ИНН: {fact['inn']}")
    return "; ".join(parts) + "."


def _layer_stats(layer_id: str) -> dict[str, Any]:
    if layer_id not in DATA_LAYER_BY_ID:
        raise ValueError(f"Unknown layer: {layer_id}")
    items = _load_items(layer_id)
    total = len(items)
    def count_with(field: str) -> int:
        return sum(1 for item in items if item.get(field))
    return {
        "layer": _layer_schema(layer_id),
        "total": total,
        "with_phone": count_with("phone"),
        "with_email": count_with("email"),
        "with_website": count_with("website"),
        "with_head": count_with("fns_head_name"),
        "with_license": count_with("license_number"),
        "cache": _cache_meta.get(_dataset_path(layer_id), {}),
    }


def _layer_facets(layer_id: str, field: str, limit: int = 50) -> dict[str, Any]:
    if layer_id not in DATA_LAYER_BY_ID:
        raise ValueError(f"Unknown layer: {layer_id}")
    if field not in PUBLIC_FIELDS and field not in DATA_LAYER_BY_ID[layer_id].get("display_fields", []):
        raise ValueError(f"Field is not public for {layer_id}: {field}")
    counts: dict[str, int] = {}
    for item in _load_items(layer_id):
        value = item.get(field)
        if value is None or value == "":
            continue
        text = str(value)
        counts[text] = counts.get(text, 0) + 1
    values = [{"value": value, "count": count} for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]
    return {"layer": layer_id, "field": field, "total": len(values), "items": values[: max(1, min(int(limit), 200))]}


def _quality_findings(layer_id: str = "", limit: int = 100) -> dict[str, Any]:
    target_layers = [layer_id] if layer_id else [str(layer["id"]) for layer in DATA_LAYERS]
    findings = []
    for target in target_layers:
        items = _load_items(target)
        inn_counts: dict[str, int] = {}
        for item in items:
            inn = str(item.get("inn") or "")
            if inn:
                inn_counts[inn] = inn_counts.get(inn, 0) + 1
        for item in items:
            title = item.get("fns_short_name") or item.get("fns_full_name") or item.get("inn")
            checks = {
                "missing_phone": not item.get("phone"),
                "missing_email": not item.get("email"),
                "missing_address": not (item.get("address") or item.get("legal_address")),
                "missing_head": not item.get("fns_head_name"),
                "missing_license": not item.get("license_number"),
                "duplicate_inn": bool(item.get("inn") and inn_counts.get(str(item.get("inn"))) > 1),
            }
            for check, failed in checks.items():
                if failed:
                    findings.append({"layer": target, "check": check, "title": title, "inn": item.get("inn")})
    return {"total": len(findings), "items": findings[: max(1, min(int(limit), 500))]}


def _quality_summary() -> dict[str, Any]:
    layers = []
    for layer in DATA_LAYERS:
        layer_id = str(layer["id"])
        stats = _layer_stats(layer_id)
        findings = _quality_findings(layer_id=layer_id, limit=1000)
        by_check: dict[str, int] = {}
        for item in findings["items"]:
            by_check[item["check"]] = by_check.get(item["check"], 0) + 1
        layers.append({"layer": layer_id, "total": stats["total"], "findings": findings["total"], "by_check": by_check})
    return {"layers": layers, "total_findings": sum(layer["findings"] for layer in layers)}


def _diagnostics_payload() -> dict[str, Any]:
    tools = [
        "get_server_info", "get_contract_info", "mcp_diagnostics", "list_data_layers",
        "layer_list", "layer_schema", "layer_suggest", "layer_query", "layer_get",
        "layer_answer_context", "layer_stats", "layer_facets", "quality_summary",
        "quality_findings", "search_all", "list_schools", "search_schools",
        "get_school_by_inn", "list_kindergartens", "search_kindergartens",
        "get_kindergarten_by_inn", "get_data_update_info",
    ]
    api_status = "ok"
    api_error = ""
    try:
        _get_json(_dataset_path(str(DATA_LAYERS[0]["id"])))
    except Exception as error:
        api_status = "error"
        api_error = str(error)
    return {
        "status": "ok" if api_status == "ok" else "degraded",
        "api_status": api_status,
        "api_error": api_error,
        "uptime_seconds": round(time.time() - float(_metrics["started_at"]), 2),
        "version": _version_payload(),
        "tools": tools,
        "resources": [GUIDANCE_RESOURCE_URI, LAYERS_RESOURCE_URI],
        "layers": [_layer_schema(str(layer["id"])) for layer in DATA_LAYERS],
        "cache": {"entries": len(_cache), "meta": _cache_meta, **_metrics["cache"]},
        "metrics": _metrics,
    }


def _paginate(items: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    return {
        "total": len(items),
        "limit": safe_limit,
        "offset": safe_offset,
        "items": items[safe_offset : safe_offset + safe_limit],
    }


def _search(dataset: DatasetName, query: str, limit: int) -> dict[str, Any]:
    items = [item for item in _load_items(dataset) if _matches(item, query)]
    return _paginate(items, limit=limit, offset=0)


def _get_by_inn(dataset: DatasetName, inn: str) -> dict[str, Any]:
    normalized_inn = "".join(ch for ch in str(inn) if ch.isdigit())
    for item in _load_items(dataset):
        if str(item.get("inn") or "") == normalized_inn:
            return {"found": True, "item": item}

    return {"found": False, "item": None}


def _version_payload() -> dict[str, Any]:
    return {
        "server_name": "Yoshkar-Ola Public Data",
        "server_version": SERVER_VERSION,
        "skill_version": SKILL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "npm_package": NPM_PACKAGE,
        "mcp_endpoint": "https://apiiola.yasg.ru/mcp",
        "data_layers": list(DATA_LAYERS),
        "capabilities": [
            "layer_list", "layer_schema", "layer_suggest", "layer_query", "layer_get",
            "layer_answer_context", "layer_stats", "layer_facets", "quality_summary",
            "quality_findings", "mcp_diagnostics",
        ],
    }


mcp = FastMCP(
    name="Yoshkar-Ola Public Data",
    instructions=(
        "MCP-сервер открытых данных городского округа \"Город Йошкар-Ола\". "
        "Сервер предоставляет доступ к открытым наборам данных. "
        "Основной эталонный источник данных - \"Цифровой мозг городского округа\"."
    ),
    version=SERVER_VERSION,
)


def _guidance_text() -> str:
    return f"""# Открытые данные городского округа "Город Йошкар-Ола"

Актуальная версия инструкций: {SKILL_VERSION}.

Используй MCP-инструменты этого сервера, когда пользователь спрашивает о
наборах открытых данных городского округа "Город Йошкар-Ола".

Доступные наборы первого релиза:

- муниципальные школы;
- муниципальные детские сады.

Правила:

- не отвечай из памяти, если сведения можно получить через MCP;
- не добавляй телефоны, адреса, сайты, ФИО, ИНН, лицензии и другие реквизиты,
  которых нет в ответе MCP;
- если данных нет в открытом наборе, прямо скажи, что в доступном открытом
  наборе такие сведения не найдены;
- если найдено несколько похожих организаций, покажи короткий список
  совпадений и уточни, какая запись нужна пользователю;
- если пользователь сообщает о неточности, не исправляй данные самостоятельно,
  а скажи, что сведения нужно проверить в источнике и передать сопровождающим
  набора данных.

Для проверки актуальности локального skill используй инструмент
`get_server_info`.

Для работы со слоями используй универсальные инструменты `layer_list`,
`layer_schema`, `layer_query` и `layer_get`; список схем также доступен в
resource `yoshkar-ola://layers`.
"""


@mcp.tool
def get_server_info() -> dict[str, Any]:
    """Получить версию сервера, доступные слои и команды обновления локального skill."""
    return {
        **_version_payload(),
        "skill_name": "yoshkar-ola-open-data",
        "guidance_resource_uri": GUIDANCE_RESOURCE_URI,
        "guidance_prompt": "yoshkar_ola_open_data_guidance",
        "update_commands": {
            "codex_skill": f"npx -y {NPM_PACKAGE} install-skill codex",
            "codex_mcp": f"codex mcp add yoshkarOlaPublicDataNpm -- npx -y {NPM_PACKAGE}",
        },
    }


@mcp.tool
def get_contract_info() -> dict[str, Any]:
    """Получить версию MCP-контракта и список поддерживаемых универсальных возможностей."""
    return {
        "contract_version": CONTRACT_VERSION,
        "server_version": SERVER_VERSION,
        "skill_version": SKILL_VERSION,
        "resources": [GUIDANCE_RESOURCE_URI, LAYERS_RESOURCE_URI],
        "tools": [
            "layer_list", "layer_schema", "layer_suggest", "layer_query", "layer_get",
            "layer_answer_context", "layer_stats", "layer_facets", "quality_summary",
            "quality_findings", "mcp_diagnostics",
        ],
        "layer_count": len(DATA_LAYERS),
    }


@mcp.tool
def mcp_diagnostics() -> dict[str, Any]:
    """Получить подробную диагностику MCP-сервера, API, cache, tools и слоев."""
    return _diagnostics_payload()


@mcp.tool
def list_data_layers() -> dict[str, Any]:
    """Получить список доступных открытых слоев данных."""
    return {
        "total": len(DATA_LAYERS),
        "items": list(DATA_LAYERS),
    }


@mcp.tool
def layer_list(category: str | None = None) -> dict[str, Any]:
    """Получить список универсальных слоев данных и их поисковых схем."""
    items = _list_layer_schemas(category=category)
    return {
        "total": len(items),
        "items": items,
    }


@mcp.tool
def layer_schema(layer: str) -> dict[str, Any]:
    """Получить схему универсального слоя данных по идентификатору."""
    return _layer_schema(layer)


@mcp.tool
def layer_suggest(query: str, limit: int = 5) -> dict[str, Any]:
    """Подобрать наиболее подходящие слои данных для вопроса пользователя."""
    return _suggest_layers(query=query, limit=limit)


@mcp.tool
def layer_query(layer: str, query: str, limit: int = 20) -> dict[str, Any]:
    """Найти записи в универсальном слое данных по текстовому запросу."""
    return _query_layer(layer, query=query, limit=limit)


@mcp.tool
def layer_get(layer: str, inn: str = "", query: str = "") -> dict[str, Any]:
    """Получить одну запись универсального слоя по ИНН или ближайшему текстовому совпадению."""
    return _get_layer_item(layer, inn=inn, query=query)


@mcp.tool
def layer_answer_context(question: str, layer: str = "", limit: int = 5) -> dict[str, Any]:
    """Подготовить компактный RAG-контекст с фактами и источниками для ответа модели."""
    return _answer_context(question=question, layer=layer, limit=limit)


@mcp.tool
def layer_stats(layer: str) -> dict[str, Any]:
    """Получить статистику заполненности публичных полей слоя."""
    return _layer_stats(layer)


@mcp.tool
def layer_facets(layer: str, field: str, limit: int = 50) -> dict[str, Any]:
    """Получить частотный список значений публичного поля слоя."""
    return _layer_facets(layer, field=field, limit=limit)


@mcp.tool
def quality_summary() -> dict[str, Any]:
    """Получить сводку проверок качества по всем слоям."""
    return _quality_summary()


@mcp.tool
def quality_findings(layer: str = "", limit: int = 100) -> dict[str, Any]:
    """Получить список найденных проблем качества данных."""
    return _quality_findings(layer_id=layer, limit=limit)


@mcp.tool
def search_all(query: str, limit_per_layer: int = 10) -> dict[str, Any]:
    """Искать по всем доступным слоям данных."""
    safe_limit = max(1, min(int(limit_per_layer), 50))
    results = []

    for layer in DATA_LAYERS:
        layer_id = layer["id"]
        if layer_id not in ("schools", "kindergartens"):
            continue
        search_result = _search(layer_id, query=query, limit=safe_limit)
        results.append(
            {
                "layer": layer,
                "total": search_result["total"],
                "items": search_result["items"],
            }
        )

    return {
        "query": query,
        "limit_per_layer": safe_limit,
        "layers_searched": len(results),
        "total": sum(result["total"] for result in results),
        "results": results,
    }


@mcp.resource(
    GUIDANCE_RESOURCE_URI,
    name="yoshkar_ola_open_data_guidance",
    description="Актуальные инструкции по работе с открытыми данными городского округа.",
    mime_type="text/markdown",
)
def open_data_guidance_resource() -> str:
    return _guidance_text()


@mcp.resource(
    LAYERS_RESOURCE_URI,
    name="yoshkar_ola_open_data_layers",
    description="Список универсальных слоев открытых данных и их поисковых схем.",
    mime_type="application/json",
)
def open_data_layers_resource() -> dict[str, Any]:
    return layer_list()


@mcp.prompt(
    name="yoshkar_ola_open_data_guidance",
    description="Инструкции для агента по работе с открытыми данными городского округа.",
)
def open_data_guidance_prompt() -> str:
    return _guidance_text()


@mcp.custom_route("/mcp-health", methods=["GET"], include_in_schema=False)
async def mcp_health(_: Request) -> JSONResponse:
    diagnostics = _diagnostics_payload()
    return JSONResponse({
        "status": diagnostics["status"],
        "api_status": diagnostics["api_status"],
        "metrics": _metrics,
        **_version_payload(),
    })


@mcp.custom_route("/mcp-version", methods=["GET"], include_in_schema=False)
async def mcp_version(_: Request) -> JSONResponse:
    return JSONResponse(_version_payload())


@mcp.custom_route("/mcp-diagnostics", methods=["GET"], include_in_schema=False)
async def mcp_diagnostics_route(_: Request) -> JSONResponse:
    return JSONResponse(_diagnostics_payload())


@mcp.tool
def list_schools(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Получить список школ с публичными реквизитами, контактами, данными ФНС и лицензии."""
    return _paginate(_load_items("schools"), limit=limit, offset=offset)


@mcp.tool
def search_schools(query: str, limit: int = 20) -> dict[str, Any]:
    """Найти школы по названию, ИНН, адресу, руководителю, email или сайту."""
    return _search("schools", query=query, limit=limit)


@mcp.tool
def get_school_by_inn(inn: str) -> dict[str, Any]:
    """Получить одну школу по ИНН."""
    return _get_by_inn("schools", inn=inn)


@mcp.tool
def list_kindergartens(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Получить список детских садов с публичными реквизитами, контактами, данными ФНС и лицензии."""
    return _paginate(_load_items("kindergartens"), limit=limit, offset=offset)


@mcp.tool
def search_kindergartens(query: str, limit: int = 20) -> dict[str, Any]:
    """Найти детские сады по названию, ИНН, адресу, руководителю, email или сайту."""
    return _search("kindergartens", query=query, limit=limit)


@mcp.tool
def get_kindergarten_by_inn(inn: str) -> dict[str, Any]:
    """Получить один детский сад по ИНН."""
    return _get_by_inn("kindergartens", inn=inn)


@mcp.tool
def get_data_update_info() -> dict[str, Any]:
    """Получить дату последнего обновления открытых данных."""
    payload = _get_json("fns-egrul/last-update")
    return {
        "last_updated_at": payload.get("last_updated_at"),
        "source": "Публичный API открытых данных городского округа",
    }


def main() -> None:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8001"))
    path = os.getenv("MCP_PATH", "/mcp")
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        path=path,
        stateless_http=True,
    )


def main_stdio() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
