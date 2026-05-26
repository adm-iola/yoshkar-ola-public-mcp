# Release process

This repository publishes two public surfaces:

- the remote MCP server at `https://apiiola.yasg.ru/mcp`;
- the npm stdio launcher package `@iola_adm/yoshkar-ola-public-mcp`.

## Required secret

Add an npm automation token to GitHub repository secrets:

```text
NPM_TOKEN
```

The token must be allowed to publish `@iola_adm/yoshkar-ola-public-mcp`.

## Version checklist

Before creating a release, update the version in:

- `package.json`;
- `package-lock.json`;
- `pyproject.toml`;
- `src/yoshkar_ola_public_mcp/__init__.py`;
- `src/yoshkar_ola_public_mcp/server.py`;
- `docs/openapi/chatgpt-actions.openapi.yaml`;
- `skills/yoshkar-ola-open-data/SKILL.md`;
- `CHANGELOG.md`.

Run:

```bash
npm ci
npm test
npm pack --dry-run
pytest
```

## Publish

Create and push a tag matching the package version:

```bash
git tag -a v0.1.4 -m "v0.1.4"
git push origin v0.1.4
```

Create a GitHub Release from the tag. The `Publish npm package` workflow will
publish the package automatically after the release is published.

## Manual fallback

If the workflow is unavailable, publish from a trusted local machine:

```bash
npm publish --access public
```
