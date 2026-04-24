# Mermaid Renderer Remote Integration v1

## Background

The platform now has a `MermaidRenderer` abstraction with `disabled`, `local_cli`, and `remote` modes. The independent `mermaid-renderer-service/` subproject has also been implemented with:

- `GET /health`
- `POST /render`
- Dockerfile
- Node.js + Mermaid CLI + Chromium encapsulation

This round validates the real remote path end-to-end.

## Goal

Build and run `mermaid-renderer-service` in Docker, then verify that the platform can call it through `MERMAID_RENDERER_MODE=remote` and produce:

```text
outputs/trd_*/trend_state_graph.png
```

## Scope

In scope:

- Run service tests.
- Build Docker image:
  - `mermaid-renderer-service:0.1.0`
- Start container on port `8091`.
- Verify:
  - `GET /health`
  - `POST /render`
- Run platform trend enhancement with:
  - `MERMAID_RENDERER_MODE=remote`
  - `MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8091`
- Confirm:
  - `.mmd` source still exists
  - `trend_state_graph.png` exists
  - normal metric PNG charts still exist
- If practical, run with a base DOCX and confirm `augmented_report.docx` is produced.
- Update README / project status with the verified remote flow.

## Out Of Scope

- No `/api/tasks` changes.
- No xray changes.
- No `waf_audits` changes.
- No compose file in this round unless needed for verification notes.
- No CI wiring in this round.
- No authentication.
- No service persistence or queues.

## Validation Commands

Renderer service:

```bash
cd mermaid-renderer-service
npm test
docker build -t mermaid-renderer-service:0.1.0 .
docker run --rm -p 8091:8091 mermaid-renderer-service:0.1.0
```

Platform:

```bash
MERMAID_RENDERER_MODE=remote \
MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8091 \
.venv/bin/python scripts/run_trend_enhancement.py tests/fixtures/trend_reports/multi_point_status_analysis.md
```

## Acceptance Criteria

- Docker image builds successfully.
- Container starts and `GET /health` returns `ok`.
- `POST /render` returns `image/png` with `Cache-Control: no-store`.
- Platform remote mode writes `outputs/trd_*/trend_state_graph.png`.
- Platform trend run remains successful.
- Existing service and platform tests pass.
