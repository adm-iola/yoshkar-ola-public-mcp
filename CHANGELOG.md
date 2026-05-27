# Changelog

## 0.1.5 - 2026-05-27

- Added generic layer MCP tools: `layer_list`, `layer_schema`, `layer_query` and `layer_get`.
- Added `yoshkar-ola://layers` resource with searchable layer schemas.
- Updated the Codex skill to prefer MCP layer tools for future datasets.

## 0.1.4 - 2026-05-26

- Added public HTTP endpoints `/mcp-health` and `/mcp-version`.
- Added connection examples in `docs/examples/`.
- Reworked `SECURITY.md` as a Russian public data and reporting policy.

## 0.1.3 - 2026-05-26

- Added `list_data_layers` MCP tool.
- Added `search_all` MCP tool for cross-layer search.
- Added tests for layer listing and cross-layer search.

## 0.1.2 - 2026-05-26

- Added `get_server_info` MCP tool with server, skill, npm and layer metadata.
- Added MCP resource `yoshkar-ola://guidance/open-data`.
- Added MCP prompt `yoshkar_ola_open_data_guidance`.
- Added npm commands `check-updates`, `install-skill codex` and `update-skill codex`.
- Included Codex skill in the npm package.

## 0.1.1 - 2026-05-26

- Published npm package `@iola_adm/yoshkar-ola-public-mcp`.
- Switched README image assets to public npm CDN URLs.
- Clarified public open data wording.

## 0.1.0 - 2026-05-26

- Initial public MCP server for open datasets of the urban district "Город Йошкар-Ола".
- Added schools and kindergartens tools.
- Added streamable HTTP and local stdio transports.
