#!/usr/bin/env node
"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const DEFAULT_ENDPOINT = "https://apiiola.yasg.ru/mcp";
const endpoint = process.env.YOSHKAR_OLA_PUBLIC_MCP_URL || DEFAULT_ENDPOINT;
const extraArgs = process.argv.slice(2);
const packageRoot = path.resolve(__dirname, "..", "..");
const skillName = "yoshkar-ola-open-data";
const skillSource = path.join(packageRoot, "skills", skillName);

function printHelp() {
  console.log(`Yoshkar-Ola Public MCP

Usage:
  yoshkar-ola-public-mcp
      Start local stdio proxy to ${endpoint}

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

function installCodexSkill() {
  if (!fs.existsSync(skillSource)) {
    throw new Error(`Skill source not found: ${skillSource}`);
  }

  const target = codexSkillTarget();
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(skillSource, target, { recursive: true });
  console.log(`Installed ${skillName} skill to ${target}`);
  console.log(`Version: ${packageVersion()}`);
}

function checkUpdates() {
  const version = packageVersion();
  console.log(JSON.stringify(
    {
      package: "@iola_adm/yoshkar-ola-public-mcp",
      installed_version: version,
      mcp_endpoint: endpoint,
      codex_skill_path: codexSkillTarget(),
      commands: {
        run_mcp: "npx -y @iola_adm/yoshkar-ola-public-mcp",
        update_codex_skill: "npx -y @iola_adm/yoshkar-ola-public-mcp install-skill codex",
        npm_latest: "npm view @iola_adm/yoshkar-ola-public-mcp version",
      },
      note: "MCP tools update after server deployment. Local skills update after running update_codex_skill.",
    },
    null,
    2,
  ));
}

const command = extraArgs[0];

try {
  if (command === "install-skill" || command === "update-skill") {
    const target = extraArgs[1];
    if (target !== "codex") {
      console.error("Only Codex skill installation is supported: install-skill codex");
      process.exit(2);
    }

    installCodexSkill();
    process.exit(0);
  }

  if (command === "check-updates") {
    checkUpdates();
    process.exit(0);
  }

  if (command === "--help" || command === "-h" || command === "help") {
    printHelp();
    process.exit(0);
  }
} catch (error) {
  console.error(error.message);
  process.exit(1);
}

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
