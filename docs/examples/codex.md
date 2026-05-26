# Codex

## Удаленный MCP

```bash
codex mcp add yoshkarOlaPublicData --url https://apiiola.yasg.ru/mcp
codex mcp list
```

## Локальный stdio-прокси через npm

```bash
codex mcp add yoshkarOlaPublicDataNpm -- npx -y @iola_adm/yoshkar-ola-public-mcp
codex mcp list
```

## Установка или обновление Codex skill

```bash
npx -y @iola_adm/yoshkar-ola-public-mcp install-skill codex
```

## Проверка доступных обновлений

```bash
npx -y @iola_adm/yoshkar-ola-public-mcp check-updates
```
