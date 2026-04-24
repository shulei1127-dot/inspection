import http from "node:http";
import crypto from "node:crypto";

import { RenderError, normalizeRenderOptions, renderMermaidToPng } from "./renderer.js";

const SERVICE_NAME = "mermaid-renderer-service";
const SERVICE_VERSION = process.env.SERVICE_VERSION || "0.1.0";
const PORT = Number(process.env.PORT || "8091");
const MAX_BODY_BYTES = Number(process.env.MAX_BODY_BYTES || String(1024 * 1024));

export function createServer({ renderFn = renderMermaidToPng } = {}) {
  return http.createServer(async (request, response) => {
    if (request.method === "GET" && request.url === "/health") {
      return sendJson(response, 200, {
        status: "ok",
        service: SERVICE_NAME,
        version: SERVICE_VERSION
      });
    }

    if (request.method === "POST" && request.url === "/render") {
      const requestId = createRequestId();
      try {
        const payload = await readJsonBody(request);
        const options = normalizeRenderOptions(payload);
        const pngBytes = await renderFn(options);
        response.writeHead(200, {
          "Content-Type": "image/png",
          "Cache-Control": "no-store",
          "X-Request-Id": requestId
        });
        response.end(pngBytes);
        return;
      } catch (error) {
        return sendRenderError(response, error, requestId);
      }
    }

    return sendJson(response, 404, {
      success: false,
      request_id: createRequestId(),
      error: {
        code: "not_found",
        message: "Route not found.",
        details: {}
      }
    });
  });
}

function sendRenderError(response, error, requestId) {
  if (error instanceof RenderError) {
    const status = error.code === "unsupported_format" || error.code === "invalid_request" ? 400 : 500;
    return sendJson(response, status, {
      success: false,
      request_id: requestId,
      error: {
        code: error.code,
        message: error.message,
        details: error.details ?? {}
      }
    });
  }

  return sendJson(response, 500, {
    success: false,
    request_id: requestId,
    error: {
      code: "renderer_internal_error",
      message: "Unexpected renderer error.",
      details: {}
    }
  });
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  response.end(JSON.stringify(payload));
}

function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    let raw = "";
    let size = 0;
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new RenderError("invalid_request", "Request body is too large."));
        request.destroy();
        return;
      }
      raw += chunk.toString("utf8");
    });
    request.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        reject(new RenderError("invalid_request", "Request body must be valid JSON."));
      }
    });
    request.on("error", () => {
      reject(new RenderError("invalid_request", "Failed to read request body."));
    });
  });
}

function createRequestId() {
  return `rnd_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  createServer().listen(PORT, () => {
    console.log(`${SERVICE_NAME} listening on ${PORT}`);
  });
}
