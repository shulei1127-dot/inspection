# Mermaid Renderer Service v1

## Background

The platform side already has a `MermaidRenderer` abstraction with:

- `disabled`
- `local_cli`
- `remote`

The `remote` mode assumes a future renderer service that accepts Mermaid source text and returns PNG bytes. This round defines and implements that independent service boundary without changing trend business logic.

## Goal

Create a lightweight `mermaid-renderer-service` that encapsulates Node.js, Mermaid CLI, Chromium, and font dependencies behind a small HTTP API.

Target chain:

```text
inspection-report-platform
  -> POST mermaid-renderer-service /render
  -> image/png
  -> outputs/trd_*/trend_state_graph.png
```

## Scope

In scope:

- Initialize a minimal `mermaid-renderer-service/` subproject.
- Implement:
  - `GET /health`
  - `POST /render`
- Use Node.js service code.
- Use Mermaid CLI (`mmdc`) internally.
- Use temporary files for render input/output.
- Return `image/png` on success.
- Return structured JSON errors on failure.
- Add a Dockerfile that encapsulates:
  - Node.js
  - `@mermaid-js/mermaid-cli`
  - Chromium
  - CJK fonts
- Add README instructions for local and Docker usage.
- Add minimal service tests where practical.

## Out Of Scope

- No platform trend business logic changes.
- No `/api/tasks` changes.
- No xray changes.
- No `waf_audits` changes.
- No Carbone changes.
- No Mermaid image insertion changes beyond the platform abstraction already implemented.
- No public authentication layer in v1.
- No persistent storage.
- No queue/background rendering.

## Proposed Directory

```text
mermaid-renderer-service/
  Dockerfile
  README.md
  package.json
  package-lock.json
  app/
    main.js
    renderer.js
  test/
    renderer.test.js
```

If keeping the first implementation even smaller, `app/main.js` may contain both HTTP routing and render orchestration, but renderer-specific logic should still be easy to split later.

## API Contract v1

### GET /health

Response:

```json
{
  "status": "ok",
  "service": "mermaid-renderer-service",
  "version": "0.1.0"
}
```

### POST /render

Request:

```json
{
  "source": "flowchart LR\nA --> B",
  "format": "png",
  "theme": "default",
  "background": "white"
}
```

Rules:

- `source` is required.
- `format` v1 only supports `png`.
- `theme` is optional and defaults to `default`.
- `background` is optional and defaults to `white`.
- Local filesystem paths are not accepted from callers.
- Service writes `source` to a temporary `.mmd` file internally.
- Service calls `mmdc` with argument array, not shell string interpolation.
- Service returns PNG bytes with:
  - `Content-Type: image/png`
  - `Cache-Control: no-store`

Error response:

```json
{
  "success": false,
  "request_id": "rnd_...",
  "error": {
    "code": "render_failed",
    "message": "Failed to render Mermaid source.",
    "details": {
      "reason": "mmdc_non_zero_exit"
    }
  }
}
```

Suggested v1 error codes:

- `invalid_request`
- `unsupported_format`
- `render_timeout`
- `render_failed`
- `renderer_internal_error`

## Runtime Configuration

Environment variables:

- `PORT=8091`
- `SERVICE_VERSION=0.1.0`
- `MMD_TIMEOUT_SECONDS=30`
- `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium`

## Docker Notes

Dockerfile should avoid relying on host-level Mermaid CLI installation. The image owns all render dependencies.

Version strategy:

- pin the Node base image major line
- pin `@mermaid-js/mermaid-cli` in `package.json`
- install Chromium from the base distribution package repository
- document the image build date / package versions in README so rendering differences can be traced when Mermaid or Chromium changes

Expected future compose shape:

```text
inspection-report-platform
log-analyzer-service
mermaid-renderer-service
carbone
```

The platform should use:

```env
MERMAID_RENDERER_MODE=remote
MERMAID_RENDERER_BASE_URL=http://mermaid-renderer-service:8091
```

## Testing Plan

Minimum tests:

- `GET /health` returns status/service/version.
- `POST /render` rejects missing source.
- `POST /render` rejects unsupported format.
- renderer calls `mmdc` with safe argument array.
- renderer returns PNG bytes when the command succeeds.
- renderer returns structured error when the command fails.

If real Mermaid CLI is not available in local test env, use a fake command path for unit tests and leave real render validation to Docker smoke/manual validation.

## Acceptance Criteria

- `mermaid-renderer-service/` can be installed independently.
- `GET /health` works.
- `POST /render` contract is implemented.
- Service tests pass.
- Dockerfile documents and encapsulates the Mermaid CLI / Chromium dependency.
- Platform code does not need to change in this round.

## Next Round

After this service exists, run a full remote integration:

```text
platform MERMAID_RENDERER_MODE=remote
  -> mermaid-renderer-service /render
  -> outputs/trd_*/trend_state_graph.png
  -> optional augmented_report.docx
```
