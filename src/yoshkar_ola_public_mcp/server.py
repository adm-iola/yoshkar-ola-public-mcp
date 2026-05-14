from __future__ import annotations

import os
import time
from typing import Any, Literal

import httpx
from fastmcp import FastMCP

API_BASE_URL = os.getenv("CPR_PUBLIC_API_BASE_URL", "https://apiiola.yasg.ru/api/v1").rstrip("/")
HTTP_TIMEOUT_SECONDS = float(os.getenv("CPR_PUBLIC_API_TIMEOUT", "20"))
CACHE_TTL_SECONDS = int(os.getenv("CPR_PUBLIC_API_CACHE_TTL", "300"))

DatasetName = Literal["schools", "kindergartens"]

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


def _dataset_path(dataset: DatasetName) -> str:
    if dataset not in ("schools", "kindergartens"):
        raise ValueError(f"Unknown dataset: {dataset}")
    return dataset


def _load_items(dataset: DatasetName) -> list[dict[str, Any]]:
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


mcp = FastMCP(
    name="Yoshkar-Ola Public Data",
    instructions=(
        "Публичный MCP-сервер администрации городского округа Йошкар-Ола. "
        "Сервер предоставляет только заранее одобренные открытые данные: школы и детские сады. "
        "Источник данных: публичный API ЦПР и открытые сведения ФНС России."
    ),
    version="0.1.0",
)


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
    """Получить дату последнего обновления данных ФНС/ЕГРЮЛ в публичном API."""
    payload = _get_json("fns-egrul/last-update")
    return {
        "last_updated_at": payload.get("last_updated_at"),
        "source": "ФНС России / ЕГРЮЛ через публичный API ЦПР",
    }


def main() -> None:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8001"))
    path = os.getenv("MCP_PATH", "/mcp")
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path=path,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
