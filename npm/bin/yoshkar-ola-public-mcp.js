#!/usr/bin/env node
"use strict";

const { spawn } = require("node:child_process");

const DEFAULT_ENDPOINT = "https://apiiola.yasg.ru/mcp";
const endpoint = process.env.YOSHKAR_OLA_PUBLIC_MCP_URL || DEFAULT_ENDPOINT;
const extraArgs = process.argv.slice(2);

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
