import assert from "node:assert/strict";
import test from "node:test";

import { createServer } from "../app/main.js";
import { RenderError } from "../app/renderer.js";

test("GET /health returns service metadata", async () => {
  const { baseUrl, close } = await startTestServer();
  try {
    const response = await fetch(`${baseUrl}/health`);
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.equal(body.status, "ok");
    assert.equal(body.service, "mermaid-renderer-service");
    assert.equal(body.version, "0.1.0");
  } finally {
    await close();
  }
});

test("POST /render returns PNG bytes and no-store cache header", async () => {
  const { baseUrl, close } = await startTestServer({
    renderFn: async () => Buffer.from("fake-png")
  });
  try {
    const response = await fetch(`${baseUrl}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "flowchart LR\nA --> B", format: "png" })
    });
    const body = Buffer.from(await response.arrayBuffer());

    assert.equal(response.status, 200);
    assert.equal(response.headers.get("content-type"), "image/png");
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.match(response.headers.get("x-request-id"), /^rnd_/);
    assert.equal(body.toString(), "fake-png");
  } finally {
    await close();
  }
});

test("POST /render rejects missing source with request_id", async () => {
  const { baseUrl, close } = await startTestServer();
  try {
    const response = await fetch(`${baseUrl}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format: "png" })
    });
    const body = await response.json();

    assert.equal(response.status, 400);
    assert.equal(body.success, false);
    assert.match(body.request_id, /^rnd_/);
    assert.equal(body.error.code, "invalid_request");
  } finally {
    await close();
  }
});

test("POST /render returns structured render errors", async () => {
  const { baseUrl, close } = await startTestServer({
    renderFn: async () => {
      throw new RenderError("render_failed", "Failed to render Mermaid source.", {
        reason: "mmdc_non_zero_exit"
      });
    }
  });
  try {
    const response = await fetch(`${baseUrl}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "flowchart LR\nA --> B" })
    });
    const body = await response.json();

    assert.equal(response.status, 500);
    assert.equal(body.success, false);
    assert.match(body.request_id, /^rnd_/);
    assert.equal(body.error.code, "render_failed");
    assert.equal(body.error.details.reason, "mmdc_non_zero_exit");
  } finally {
    await close();
  }
});

async function startTestServer(options = {}) {
  const server = createServer(options);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  return {
    baseUrl,
    close: () => new Promise((resolve) => server.close(resolve))
  };
}
