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

Optional deployment uses the same release workflow after npm publish. Enable it
with repository variable:

```text
MCP_DEPLOY_ENABLED=true
```

Then add repository secrets:

```text
MCP_DEPLOY_HOST
MCP_DEPLOY_USER
MCP_DEPLOY_SSH_KEY
MCP_DEPLOY_PATH
MCP_DEPLOY_SERVICE
```

Defaults are `root`, `/opt/yoshkar-ola-public-mcp` and
`yoshkar-ola-public-mcp.service` for user, path and service when the
corresponding optional secrets are empty. The deploy job uploads the release
tree with `tar | ssh`, installs the Python package in the existing venv,
restarts systemd and verifies `/mcp-version` plus MCP tools.

Runtime diagnostics are available at:

```text
https://apiiola.yasg.ru/mcp-diagnostics
```

## Runtime

The npm wrapper requires Node.js `>=22.5.0`. CI, publish jobs and local release
checks must use Node.js 22 or newer.

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

`npm test` includes syntax checks, wrapper tests and `npm run release-check`,
which verifies that all version files are synchronized.

## Publish

Create and push a tag matching the package version:

```bash
git tag -a v0.1.6 -m "v0.1.6"
git push origin v0.1.6
```

Create a GitHub Release from the tag. The `Publish npm package` workflow will
publish the package automatically after the release is published. If
`MCP_DEPLOY_ENABLED=true`, the same workflow also deploys the remote MCP server
and verifies the public endpoint.

## Manual fallback

If the workflow is unavailable, publish from a trusted local machine:

```bash
npm publish --access public --provenance
```
