"use strict";

const assert = require("node:assert/strict");
const { execFile } = require("node:child_process");
const { mkdtemp, rm } = require("node:fs/promises");
const { createServer } = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const bin = path.resolve(__dirname, "..", "bin", "yoshkar-ola-public-mcp.js");
const packageJson = require("../../package.json");

function run(args, env = {}) {
  return new Promise((resolve) => {
    execFile(process.execPath, [bin, ...args], {
      env: { ...process.env, ...env },
      timeout: 10_000,
    }, (error, stdout, stderr) => {
      resolve({ code: error?.code || 0, stdout, stderr });
    });
  });
}

function mockMcpServer() {
  const server = createServer((request, response) => {
    const basePayload = {
      server_name: "Yoshkar-Ola Public Data",
      server_version: "0.1.8",
      skill_version: "0.1.8",
      npm_package: "@iola_adm/yoshkar-ola-public-mcp",
      mcp_endpoint: "",
      data_layers: [],
    };

    if (request.url === "/mcp-health") {
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ status: "ok", ...basePayload }));
      return;
    }

    if (request.url === "/mcp-version") {
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify(basePayload));
      return;
    }

    if (request.url === "/mcp" && request.method === "POST") {
      let body = "";
      request.on("data", (chunk) => {
        body += chunk;
      });
      request.on("end", () => {
        const payload = JSON.parse(body);
        let result = {};
        if (payload.method === "tools/list") {
          result = {
            tools: [
              { name: "layer_list" },
              { name: "layer_schema" },
              { name: "layer_suggest" },
              { name: "layer_query" },
              { name: "layer_get" },
              { name: "layer_answer_context" },
              { name: "layer_stats" },
              { name: "layer_facets" },
              { name: "quality_summary" },
              { name: "quality_findings" },
              { name: "mcp_diagnostics" },
            ],
          };
        }
        if (payload.method === "tools/call") {
          result = { content: [{ type: "text", text: JSON.stringify({ ok: true, params: payload.params }) }] };
        }
        response.setHeader("content-type", "application/json");
        response.end(JSON.stringify({ jsonrpc: "2.0", id: payload.id, result }));
      });
      return;
    }

    response.statusCode = 404;
    response.end("not found");
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({
        endpoint: `http://127.0.0.1:${address.port}/mcp`,
        close: () => new Promise((done) => server.close(done)),
      });
    });
  });
}

test("help mentions diagnostics commands", async () => {
  const result = await run(["--help"]);

  assert.equal(result.code, 0);
  assert.match(result.stdout, /doctor/);
  assert.match(result.stdout, /tools/);
  assert.match(result.stdout, /call TOOL/);
});

test("check-updates returns JSON with versions", async () => {
  const server = await mockMcpServer();
  const home = await mkdtemp(path.join(os.tmpdir(), "yoshkar-mcp-home-"));
  try {
    const result = await run(["check-updates"], {
      HOME: home,
      USERPROFILE: home,
      YOSHKAR_OLA_PUBLIC_MCP_URL: server.endpoint,
    });

    assert.equal(result.code, 0);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.installed_version, packageJson.version);
    assert.equal(payload.remote_server_version, "0.1.8");
    assert.equal(payload.required_node, ">=22.5.0");
  } finally {
    await server.close();
    await rm(home, { recursive: true, force: true });
  }
});

test("tools lists layer tools from remote MCP", async () => {
  const server = await mockMcpServer();
  try {
    const result = await run(["tools"], { YOSHKAR_OLA_PUBLIC_MCP_URL: server.endpoint });

    assert.equal(result.code, 0);
    assert.match(result.stdout, /layer_list/);
    assert.match(result.stdout, /layer_query/);
  } finally {
    await server.close();
  }
});

test("doctor validates required layer tools", async () => {
  const server = await mockMcpServer();
  const home = await mkdtemp(path.join(os.tmpdir(), "yoshkar-mcp-home-"));
  try {
    const result = await run(["doctor"], {
      HOME: home,
      USERPROFILE: home,
      YOSHKAR_OLA_PUBLIC_MCP_URL: server.endpoint,
    });

    assert.equal(result.code, 0);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.ok, true);
    assert.equal(payload.required_layer_tools_ok, true);
  } finally {
    await server.close();
    await rm(home, { recursive: true, force: true });
  }
});
