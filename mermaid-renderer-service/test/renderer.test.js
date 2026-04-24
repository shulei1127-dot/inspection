import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { writeFile } from "node:fs/promises";
import test from "node:test";

import {
  RenderError,
  buildMmdcArgs,
  normalizeRenderOptions,
  renderMermaidToPng
} from "../app/renderer.js";

test("normalizeRenderOptions accepts v1 defaults", () => {
  const options = normalizeRenderOptions({
    source: "flowchart LR\n  A --> B\n"
  });

  assert.equal(options.format, "png");
  assert.equal(options.theme, "default");
  assert.equal(options.background, "white");
});

test("normalizeRenderOptions rejects missing source", () => {
  assert.throws(
    () => normalizeRenderOptions({ format: "png" }),
    (error) => error instanceof RenderError && error.code === "invalid_request"
  );
});

test("normalizeRenderOptions rejects unsupported format", () => {
  assert.throws(
    () => normalizeRenderOptions({ source: "flowchart LR\nA --> B", format: "svg" }),
    (error) => error instanceof RenderError && error.code === "unsupported_format"
  );
});

test("buildMmdcArgs uses safe argument array", () => {
  const args = buildMmdcArgs({
    inputPath: "/tmp/input.mmd",
    outputPath: "/tmp/output.png",
    theme: "default",
    background: "white",
    puppeteerConfigFile: "/app/puppeteer-config.json"
  });

  assert.deepEqual(args, [
    "-i",
    "/tmp/input.mmd",
    "-o",
    "/tmp/output.png",
    "-t",
    "default",
    "-b",
    "white",
    "-p",
    "/app/puppeteer-config.json"
  ]);
});

test("renderMermaidToPng returns PNG bytes when command succeeds", async () => {
  const pngBytes = await renderMermaidToPng(
    normalizeRenderOptions({ source: "flowchart LR\nA --> B" }),
    {
      mmdcPath: "fake-mmdc",
      spawnFn: fakeSpawnSuccess
    }
  );

  assert.equal(pngBytes.toString(), "fake-png");
});

test("renderMermaidToPng returns structured error when command fails", async () => {
  await assert.rejects(
    () =>
      renderMermaidToPng(
        normalizeRenderOptions({ source: "flowchart LR\nA --> B" }),
        {
          mmdcPath: "fake-mmdc",
          spawnFn: fakeSpawnFailure
        }
      ),
    (error) => error instanceof RenderError && error.code === "render_failed"
  );
});

function fakeSpawnSuccess(command, args) {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => {};
  const outputPath = args[args.indexOf("-o") + 1];
  process.nextTick(async () => {
    await writeFile(outputPath, Buffer.from("fake-png"));
    child.emit("close", 0);
  });
  return child;
}

function fakeSpawnFailure() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => {};
  process.nextTick(() => {
    child.stderr.emit("data", Buffer.from("boom"));
    child.emit("close", 1);
  });
  return child;
}
