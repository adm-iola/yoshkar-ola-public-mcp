"use strict";

const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..", "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function fail(message) {
  console.error(message);
  process.exitCode = 1;
}

function matchVersion(relativePath, pattern, label) {
  const text = read(relativePath);
  const match = text.match(pattern);
  if (!match) {
    fail(`Cannot read ${label} from ${relativePath}`);
    return null;
  }
  return match[1];
}

const packageJson = JSON.parse(read("package.json"));
const version = packageJson.version;
const checks = [
  ["package-lock root", JSON.parse(read("package-lock.json")).version],
  ["package-lock package", JSON.parse(read("package-lock.json")).packages[""].version],
  ["pyproject", matchVersion("pyproject.toml", /^version = "([^"]+)"/m, "project version")],
  ["__init__", matchVersion("src/yoshkar_ola_public_mcp/__init__.py", /__version__ = "([^"]+)"/, "module version")],
  ["server", matchVersion("src/yoshkar_ola_public_mcp/server.py", /SERVER_VERSION = "([^"]+)"/, "server version")],
  ["skill", matchVersion("src/yoshkar_ola_public_mcp/server.py", /SKILL_VERSION = "([^"]+)"/, "skill version")],
  ["openapi", matchVersion("docs/openapi/chatgpt-actions.openapi.yaml", /^\s*version: ([^\s]+)/m, "OpenAPI version")],
  ["skill frontmatter", matchVersion("skills/yoshkar-ola-open-data/SKILL.md", /^version: "([^"]+)"/m, "skill frontmatter version")],
  ["skill text", matchVersion("skills/yoshkar-ola-open-data/SKILL.md", /Версия skill: `([^`]+)`/, "skill text version")],
];

for (const [label, actual] of checks) {
  if (actual !== version) {
    fail(`${label} version ${actual} does not match package version ${version}`);
  }
}

if (!read("CHANGELOG.md").includes(`## ${version} - `)) {
  fail(`CHANGELOG.md does not contain section for ${version}`);
}

const requiredNode = ">=22.5.0";
if (packageJson.engines?.node !== requiredNode) {
  fail(`package.json engines.node must be ${requiredNode}`);
}

const lockEngines = JSON.parse(read("package-lock.json")).packages[""].engines?.node;
if (lockEngines !== requiredNode) {
  fail(`package-lock.json engines.node must be ${requiredNode}`);
}

if (!process.exitCode) {
  console.log(`release-check passed for ${version}`);
}
