import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const ALLOWED_THEMES = new Set(["default", "dark", "forest", "neutral", "base"]);

export class RenderError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "RenderError";
    this.code = code;
    this.details = details;
  }
}

export function normalizeRenderOptions(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new RenderError("invalid_request", "Request body must be a JSON object.");
  }

  const source = typeof payload.source === "string" ? payload.source : "";
  if (!source.trim()) {
    throw new RenderError("invalid_request", "Field 'source' is required.");
  }

  const format = payload.format ?? "png";
  if (format !== "png") {
    throw new RenderError("unsupported_format", "Only png format is supported in v1.", { format });
  }

  const theme = payload.theme ?? "default";
  if (typeof theme !== "string" || !ALLOWED_THEMES.has(theme)) {
    throw new RenderError("invalid_request", "Unsupported Mermaid theme.", { theme });
  }

  const background = payload.background ?? "white";
  if (typeof background !== "string" || !/^[A-Za-z0-9#(),.%\s-]{1,64}$/.test(background)) {
    throw new RenderError("invalid_request", "Invalid background value.", { background });
  }

  return {
    source,
    format,
    theme,
    background
  };
}

export async function renderMermaidToPng(options, runtime = {}) {
  const {
    mmdcPath = process.env.MMD_CLI_PATH || "mmdc",
    timeoutSeconds = Number(process.env.MMD_TIMEOUT_SECONDS || "30"),
    puppeteerConfigFile = process.env.PUPPETEER_CONFIG_FILE || "",
    spawnFn = spawn
  } = runtime;
  const tempDir = await mkdtemp(path.join(os.tmpdir(), "mermaid-render-"));
  const inputPath = path.join(tempDir, "input.mmd");
  const outputPath = path.join(tempDir, "output.png");

  try {
    await writeFile(inputPath, options.source, "utf8");
    await runMmdc({
      mmdcPath,
      inputPath,
      outputPath,
      theme: options.theme,
      background: options.background,
      puppeteerConfigFile,
      timeoutSeconds,
      spawnFn
    });
    return await readFile(outputPath);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

export function buildMmdcArgs({ inputPath, outputPath, theme, background, puppeteerConfigFile = "" }) {
  const args = [
    "-i",
    inputPath,
    "-o",
    outputPath,
    "-t",
    theme,
    "-b",
    background
  ];
  if (puppeteerConfigFile) {
    args.push("-p", puppeteerConfigFile);
  }
  return args;
}

async function runMmdc({ mmdcPath, inputPath, outputPath, theme, background, puppeteerConfigFile, timeoutSeconds, spawnFn }) {
  const args = buildMmdcArgs({ inputPath, outputPath, theme, background, puppeteerConfigFile });
  const child = spawnFn(mmdcPath, args, {
    stdio: ["ignore", "pipe", "pipe"]
  });
  let stderr = "";
  let stdout = "";

  child.stderr?.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  child.stdout?.on("data", (chunk) => {
    stdout += chunk.toString();
  });

  const exitCode = await waitForChild(child, timeoutSeconds);
  if (exitCode === "timeout") {
    throw new RenderError("render_timeout", "Mermaid rendering timed out.", {
      reason: "mmdc_timeout"
    });
  }
  if (exitCode !== 0) {
    throw new RenderError("render_failed", "Failed to render Mermaid source.", {
      reason: "mmdc_non_zero_exit",
      exit_code: exitCode,
      stderr: truncate(stderr.trim(), 1200),
      stdout: truncate(stdout.trim(), 1200)
    });
  }
}

function waitForChild(child, timeoutSeconds) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      resolve("timeout");
    }, Math.max(timeoutSeconds, 1) * 1000);

    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(new RenderError("renderer_internal_error", "Failed to start Mermaid renderer.", {
        reason: "mmdc_spawn_failed",
        message: error.message
      }));
    });
    child.on("close", (code) => {
      clearTimeout(timeout);
      resolve(code ?? 1);
    });
  });
}

function truncate(value, maxLength) {
  if (!value || value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 3)}...`;
}
