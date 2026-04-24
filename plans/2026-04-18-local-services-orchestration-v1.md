# Local Services Orchestration v1

## Background

The project now has several independently runnable services:

- platform backend
- `log-analyzer-service`
- Carbone
- `mermaid-renderer-service`

Analyzer and Carbone already have local verification scripts or documented startup flows. The newly added `mermaid-renderer-service` has been built and remotely validated, but it is not yet part of a repeatable local startup/check workflow.

## Goal

Add a minimal local orchestration layer for `mermaid-renderer-service` so it can be started, stopped, and verified consistently during demos and report-generation validation.

## Scope

In scope:

- Add:
  - `scripts/start_mermaid_renderer.sh`
  - `scripts/stop_mermaid_renderer.sh`
  - `scripts/verify_mermaid_renderer.sh`
- Use the already built image name by default:
  - `mermaid-renderer-service:0.1.0`
- Use a stable default host port:
  - host `8092` -> container `8091`
- Start the container as a long-running local service:
  - fixed container name
  - restart policy `unless-stopped`
- Verify:
  - container health through `GET /health`
  - `POST /render` returns a PNG
  - optional platform remote trend run can produce `trend_state_graph.png`
- Update README with the local service startup convention.
- Update `docs/project_status.md`.

## Out Of Scope

- No Docker Compose in this round.
- No platform business logic changes.
- No `/api/tasks` changes.
- No xray changes.
- No `waf_audits` changes.
- No Carbone startup rewrite.
- No analyzer startup rewrite.
- No CI wiring.

## Default Convention

Ports:

```text
8091 -> log-analyzer-service
8092 -> mermaid-renderer-service
4000 -> Carbone
```

Mermaid renderer:

```text
container name: mermaid-renderer-service
image: mermaid-renderer-service:0.1.0
host port: 8092
container port: 8091
```

Platform config:

```env
MERMAID_RENDERER_MODE=remote
MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8092
```

## Acceptance Criteria

- `scripts/start_mermaid_renderer.sh` starts or reuses the renderer container.
- `scripts/stop_mermaid_renderer.sh` stops the renderer container.
- `scripts/verify_mermaid_renderer.sh` verifies `/health` and `/render`.
- Verification can optionally run platform trend enhancement in remote mode and confirm `trend_state_graph.png`.
- Existing Node service tests and Python tests pass.
