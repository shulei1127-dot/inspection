# Mermaid Renderer Service

Small HTTP service that renders Mermaid source text to PNG. It is intended to be called by `inspection-report-platform` in `MERMAID_RENDERER_MODE=remote`.

## Scope

- `GET /health`
- `POST /render`
- v1 output format: `png`
- no persistent storage
- no queue/background rendering
- no host-level Mermaid CLI dependency when running through Docker

## API

### GET /health

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

Fields:

- `source`: required Mermaid source text.
- `format`: optional, v1 only supports `png`.
- `theme`: optional, defaults to `default`; supported values are `default`, `dark`, `forest`, `neutral`, and `base`.
- `background`: optional, defaults to `white`.

Success response:

```text
Content-Type: image/png
Cache-Control: no-store
X-Request-Id: rnd_...
<PNG bytes>
```

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

## Local Development

Install dependencies:

```bash
npm install
```

Run tests:

```bash
npm test
```

Start service:

```bash
PORT=8091 npm start
```

If you want local real rendering outside Docker, make sure `mmdc` is available or install dependencies first and use:

```bash
MMD_CLI_PATH=./node_modules/.bin/mmdc npm start
```

## Docker

Build:

```bash
docker build -t mermaid-renderer-service:0.1.0 .
```

Run:

```bash
docker run --rm -p 8091:8091 mermaid-renderer-service:0.1.0
```

If `8091` is already occupied on the host, use another host port:

```bash
docker run --rm -p 8092:8091 mermaid-renderer-service:0.1.0
```

Platform config:

```env
MERMAID_RENDERER_MODE=remote
MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8091
```

For docker compose, use the service name:

```env
MERMAID_RENDERER_BASE_URL=http://mermaid-renderer-service:8091
```

From the repository root, local helper scripts are available:

```bash
./scripts/start_mermaid_renderer.sh
./scripts/verify_mermaid_renderer.sh --platform
./scripts/stop_mermaid_renderer.sh
```

The default helper-script mapping is host `8092` to container `8091`, because
`8091` is commonly used by `log-analyzer-service` in this workspace.

## Version Strategy

Rendering can vary across Mermaid CLI, Chromium, fonts, and base image versions. Keep these traceable:

- Base image: `node:20-alpine`
- Mermaid CLI: pinned in `package.json` as `@mermaid-js/mermaid-cli@11.12.0`
- Chromium: installed from Alpine package repositories during image build
- Fonts: `font-noto-cjk`, `font-noto-emoji`, and `ttf-freefont`

When rendering output changes unexpectedly, compare:

- image build date
- `node --version`
- `npm ls @mermaid-js/mermaid-cli`
- `chromium --version`

The first local validation on this workstation used:

- Node.js `v20.20.1`
- `@mermaid-js/mermaid-cli@11.12.0`
- Chromium `147.0.7727.55 Alpine Linux`

## Notes

The service accepts Mermaid source text only. It does not accept caller-provided file paths, so platform-local paths are never exposed to this service.
