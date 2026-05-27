#!/usr/bin/env node
"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const DEFAULT_ENDPOINT = "https://apiiola.yasg.ru/mcp";
const REQUIRED_NODE = "22.5.0";
const PACKAGE_NAME = "@iola_adm/yoshkar-ola-public-mcp";
const endpoint = process.env.YOSHKAR_OLA_PUBLIC_MCP_URL || DEFAULT_ENDPOINT;
const extraArgs = process.argv.slice(2);
const packageRoot = path.resolve(__dirname, "..", "..");
const skillName = "yoshkar-ola-open-data";
const skillSource = path.join(packageRoot, "skills", skillName);

function parseVersion(version) {
  return String(version).replace(/^v/, "").split(".").map((part) => Number.parseInt(part, 10) || 0);
}

function compareVersions(left, right) {
  const a = parseVersion(left);
  const b = parseVersion(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const diff = (a[index] || 0) - (b[index] || 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function assertSupportedNode() {
  if (compareVersions(process.version, REQUIRED_NODE) >= 0) return;
  console.error(`Required Node.js >=${REQUIRED_NODE}. Installed: ${process.version}.`);
  console.error("Update Node.js and run the command again.");
  process.exit(1);
}

function printHelp() {
  console.log(`Yoshkar-Ola Public MCP

Usage:
  yoshkar-ola-public-mcp
      Start local stdio proxy to ${endpoint}

  yoshkar-ola-public-mcp doctor
      Check Node.js, npm package, remote MCP health, versions and layer tools

  yoshkar-ola-public-mcp tools
      List tools exposed by the remote MCP endpoint

  yoshkar-ola-public-mcp call TOOL '{"name":"value"}'
      Call a remote MCP tool and print JSON result

  yoshkar-ola-public-mcp install-skill codex
      Install or update the Codex skill in ~/.codex/skills/${skillName}

  yoshkar-ola-public-mcp update-skill codex
      Alias for install-skill codex

  yoshkar-ola-public-mcp check-updates
      Show installed package version and update commands
`);
}

function packageVersion() {
  const packageJson = JSON.parse(fs.readFileSync(path.join(packageRoot, "package.json"), "utf8"));
  return packageJson.version;
}

function codexSkillTarget() {
  const home = os.homedir();
  if (!home) {
    throw new Error("Cannot determine user home directory.");
  }

  return path.join(home, ".codex", "skills", skillName);
}

function readSkillVersion(skillDir) {
  const skillFile = path.join(skillDir, "SKILL.md");
  if (!fs.existsSync(skillFile)) return null;
  const text = fs.readFileSync(skillFile, "utf8");
  return text.match(/^version:\s*["']?([^"'\r\n]+)["']?/m)?.[1] || null;
}

function installCodexSkill() {
  if (!fs.existsSync(skillSource)) {
    throw new Error(`Skill source not found: ${skillSource}`);
  }

  const target = codexSkillTarget();
  const sourceVersion = readSkillVersion(skillSource) || packageVersion();
  const installedVersion = readSkillVersion(target);

  if (installedVersion === sourceVersion) {
    console.log(`Skill ${skillName} is already up to date at ${target}`);
    console.log(`Version: ${sourceVersion}`);
    return;
  }

  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(skillSource, target, { recursive: true });
  console.log(`Installed ${skillName} skill to ${target}`);
  console.log(`Version: ${sourceVersion}`);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    signal: options.signal || AbortSignal.timeout(15_000),
    headers: {
      accept: "application/json, text/event-stream",
      ...(options.body ? { "content-type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${text.slice(0, 500)}`);
  }
  return parseJsonOrSse(text);
}

function parseJsonOrSse(text) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) return JSON.parse(trimmed);

  const data = [];
  for (const line of trimmed.split(/\r?\n/)) {
    if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!data.length) throw new Error(`Unexpected response: ${trimmed.slice(0, 500)}`);
  return JSON.parse(data.join("\n"));
}

function mcpUrl() {
  return new URL(endpoint);
}

function endpointBaseUrl() {
  const url = mcpUrl();
  url.pathname = url.pathname.replace(/\/mcp\/?$/, "");
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/$/, "");
}

async function getRemoteVersion() {
  return fetchJson(`${endpointBaseUrl()}/mcp-version`);
}

async function getRemoteHealth() {
  return fetchJson(`${endpointBaseUrl()}/mcp-health`);
}

async function mcpRequest(method, params = undefined) {
  const body = { jsonrpc: "2.0", id: 1, method };
  if (params !== undefined) body.params = params;
  const payload = await fetchJson(endpoint, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (payload?.error) throw new Error(payload.error.message || JSON.stringify(payload.error));
  return payload?.result;
}

async function listTools() {
  const result = await mcpRequest("tools/list", {});
  return result?.tools || [];
}

async function callTool(name, args = {}) {
  return mcpRequest("tools/call", { name, arguments: args });
}

async function checkUpdates() {
  const version = packageVersion();
  let server = null;
  try {
    server = await getRemoteVersion();
  } catch {
    server = null;
  }

  console.log(JSON.stringify(
    {
      package: PACKAGE_NAME,
      installed_version: version,
      node: process.version,
      required_node: `>=${REQUIRED_NODE}`,
      mcp_endpoint: endpoint,
      remote_server_version: server?.server_version || null,
      remote_skill_version: server?.skill_version || null,
      codex_skill_path: codexSkillTarget(),
      codex_skill_version: readSkillVersion(codexSkillTarget()),
      commands: {
        run_mcp: `npx -y ${PACKAGE_NAME}`,
        doctor: `npx -y ${PACKAGE_NAME} doctor`,
        list_tools: `npx -y ${PACKAGE_NAME} tools`,
        update_codex_skill: `npx -y ${PACKAGE_NAME} install-skill codex`,
        npm_latest: `npm view ${PACKAGE_NAME} version`,
      },
      note: "Remote MCP tools update after server deployment. Local skills update after running update_codex_skill.",
    },
    null,
    2,
  ));
}

async function doctor() {
  const report = {
    package: PACKAGE_NAME,
    package_version: packageVersion(),
    node: process.version,
    required_node: `>=${REQUIRED_NODE}`,
    node_ok: compareVersions(process.version, REQUIRED_NODE) >= 0,
    endpoint,
    health: null,
    version: null,
    tools: [],
    required_layer_tools: [
      "layer_list", "layer_schema", "layer_suggest", "layer_query", "layer_get",
      "layer_answer_context", "layer_stats", "layer_facets", "quality_summary",
      "quality_findings", "mcp_diagnostics",
    ],
    required_layer_tools_ok: false,
    codex_skill_path: codexSkillTarget(),
    codex_skill_version: readSkillVersion(codexSkillTarget()),
    ok: false,
  };

  report.health = await getRemoteHealth();
  report.version = await getRemoteVersion();
  report.tools = (await listTools()).map((tool) => tool.name).sort();
  report.required_layer_tools_ok = report.required_layer_tools.every((name) => report.tools.includes(name));
  report.ok = report.node_ok && report.health?.status === "ok" && report.required_layer_tools_ok;

  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) process.exit(1);
}

async function printTools() {
  const tools = await listTools();
  for (const tool of tools) {
    console.log(tool.name);
  }
}

async function printCallResult(args) {
  const tool = args[1];
  if (!tool) throw new Error("Usage: yoshkar-ola-public-mcp call TOOL '{\"name\":\"value\"}'");
  const rawArgs = args[2] || "{}";
  const toolArgs = JSON.parse(rawArgs);
  const result = await callTool(tool, toolArgs);
  console.log(JSON.stringify(result?.structuredContent || result, null, 2));
}

function startProxy() {
  const proxyScript = require.resolve("mcp-remote/dist/proxy.js");
  const child = spawn(process.execPath, [proxyScript, endpoint, ...extraArgs], {
    stdio: "inherit",
    windowsHide: true,
    env: process.env,
  });

  child.on("error", (error) => {
    console.error(`Failed to start MCP proxy: ${error.message}`);
    process.exit(1);
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }

    process.exit(code ?? 0);
  });

  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => {
      if (!child.killed) {
        child.kill(signal);
      }
    });
  }
}

async function main() {
  assertSupportedNode();
  const command = extraArgs[0];

  if (command === "install-skill" || command === "update-skill") {
    const target = extraArgs[1];
    if (target !== "codex") {
      console.error("Only Codex skill installation is supported: install-skill codex");
      process.exit(2);
    }

    installCodexSkill();
    return;
  }

  if (command === "check-updates") {
    await checkUpdates();
    return;
  }

  if (command === "doctor") {
    await doctor();
    return;
  }

  if (command === "tools" || command === "list-tools") {
    await printTools();
    return;
  }

  if (command === "call") {
    await printCallResult(extraArgs);
    return;
  }

  if (command === "--help" || command === "-h" || command === "help") {
    printHelp();
    return;
  }

  startProxy();
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
