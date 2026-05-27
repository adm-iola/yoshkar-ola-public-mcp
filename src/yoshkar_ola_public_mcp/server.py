from __future__ import annotations

import os
import time
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

API_BASE_URL = os.getenv("CPR_PUBLIC_API_BASE_URL", "https://apiiola.yasg.ru/api/v1").rstrip("/")
HTTP_TIMEOUT_SECONDS = float(os.getenv("CPR_PUBLIC_API_TIMEOUT", "20"))
CACHE_TTL_SECONDS = int(os.getenv("CPR_PUBLIC_API_CACHE_TTL", "300"))
SERVER_VERSION = "0.1.6"
SKILL_VERSION = "0.1.6"
NPM_PACKAGE = "@iola_adm/yoshkar-ola-public-mcp"
GUIDANCE_RESOURCE_URI = "yoshkar-ola://guidance/open-data"
LAYERS_RESOURCE_URI = "yoshkar-ola://layers"

DatasetName = Literal["schools", "kindergartens"]

DATA_LAYERS = (
    {
        "id": "schools",
        "name": "Муниципальные школы",
        "status": "available",
        "category": "Образование",
        "endpoint": "schools",
        "aliases": ["школ", "лицей", "гимнази"],
        "search_fields": ["inn", "fns_full_name", "fns_short_name", "fns_head_name", "legal_address", "address", "email", "website"],
        "person_fields": ["fns_head_name"],
        "source_fields": ["id", "name", "inn"],
    },
    {
        "id": "kindergartens",
        "name": "Муниципальные детские сады",
        "status": "available",
        "category": "Образование",
        "endpoint": "kindergartens",
        "aliases": ["сад", "детсад", "детский сад", "доу", "мбдоу"],
        "search_fields": ["inn", "fns_full_name", "fns_short_name", "fns_head_name", "legal_address", "address", "email", "website"],
        "person_fields": ["fns_head_name"],
        "source_fields": ["id", "name", "inn"],
    },
)
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


def _get_json(path: str) -> Any:
    now = time.time()
    cached = _cache.get(path)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    url = f"{API_BASE_URL}/{path.lstrip('/')}"
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        data = response.json()

    _cache[path] = (now, data)
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
        "name": layer["name"],
        "status": layer["status"],
        "category": layer["category"],
        "endpoint": layer["endpoint"],
        "aliases": layer["aliases"],
        "search_fields": layer["search_fields"],
        "person_fields": layer["person_fields"],
        "source_fields": layer["source_fields"],
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


def _score_item(item: dict[str, Any], terms: list[str]) -> int:
    if not terms:
        return 1
    haystack = " ".join(str(item.get(field) or "") for field in PUBLIC_FIELDS).casefold()
    head = str(item.get("fns_head_name") or "").casefold()
    score = 0
    for term in terms:
        if term in haystack:
            score += 1
        if term in head:
            score += 5
    return score


def _query_layer(layer_id: str, query: str, limit: int = 20) -> dict[str, Any]:
    if layer_id not in DATA_LAYER_BY_ID:
        raise ValueError(f"Unknown layer: {layer_id}")
    terms = _extract_terms(query)
    scored = [
        {"item": item, "score": _score_item(item, terms)}
        for item in _load_items(layer_id)
    ]
    items = [
        entry["item"]
        for entry in sorted(scored, key=lambda entry: entry["score"], reverse=True)
        if entry["score"] > 0
    ]
    page = _paginate(items, limit=limit, offset=0)
    return {
        "layer": _layer_schema(layer_id),
        "query": query,
        "terms": terms,
        "total": page["total"],
        "limit": page["limit"],
        "items": page["items"],
    }


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
        "npm_package": NPM_PACKAGE,
        "mcp_endpoint": "https://apiiola.yasg.ru/mcp",
        "data_layers": list(DATA_LAYERS),
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
def layer_query(layer: str, query: str, limit: int = 20) -> dict[str, Any]:
    """Найти записи в универсальном слое данных по текстовому запросу."""
    return _query_layer(layer, query=query, limit=limit)


@mcp.tool
def layer_get(layer: str, inn: str = "", query: str = "") -> dict[str, Any]:
    """Получить одну запись универсального слоя по ИНН или ближайшему текстовому совпадению."""
    return _get_layer_item(layer, inn=inn, query=query)


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
    return JSONResponse({"status": "ok", **_version_payload()})


@mcp.custom_route("/mcp-version", methods=["GET"], include_in_schema=False)
async def mcp_version(_: Request) -> JSONResponse:
    return JSONResponse(_version_payload())


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
