# Platform MermaidRenderer Abstraction v1

## Background

The trend subchain already has:

- Mermaid text generation from `trend_assessment.json`
- `.mmd` persistence under both `workdir/trd_*` and `outputs/trd_*`
- optional local `mmdc` rendering to `outputs/trd_*/trend_state_graph.png`
- optional insertion of the rendered PNG into the existing DOCX appendix image list

However, the current image rendering path is still local-CLI oriented. Before building an independent `mermaid-renderer-service`, the platform should first formalize a renderer abstraction so deployment modes can be swapped without changing trend business logic.

## Goal

Introduce a platform-side `MermaidRenderer` abstraction with three explicit modes:

- `disabled`
- `local_cli`
- `remote`

The trend enhancement service should depend on this abstraction instead of directly calling local CLI rendering.

## Scope

In scope:

- Add a unified renderer interface / protocol:

  ```text
  render(source_path, target_path) -> MermaidRenderResult
  ```

- Use a lightweight result object instead of bare `Path | None` so later logging,
  diagnostics, and DOCX insertion can reuse:
  - `success`
  - `output_path`
  - `reason`
- Add three implementations:
  - `DisabledMermaidRenderer`
  - `LocalCliMermaidRenderer`
  - `RemoteMermaidRenderer`
- Keep all rendering modes non-blocking:
  - disabled returns `None`
  - local CLI missing / timeout / non-zero exit returns `None`
  - remote unavailable / timeout / non-200 / invalid response returns `None`
- Add platform config:
  - `MERMAID_RENDERER_MODE=disabled|local_cli|remote`
  - `MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8091`
  - `MERMAID_RENDERER_TIMEOUT_SECONDS=30`
  - keep existing local CLI config:
    - `MERMAID_CLI_PATH=mmdc`
    - `MERMAID_CLI_TIMEOUT_SECONDS=30`
- Update trend enhancement service to call the renderer abstraction.
- Keep writing `.mmd` regardless of image rendering result.
- Keep PNG output convention:

  ```text
  outputs/trd_*/trend_state_graph.png
  ```

- `RemoteMermaidRenderer` must send only the Mermaid source string to the remote
  service. It must not expose local filesystem paths to the renderer service.
- Update `.env.example` and `README.md` with:
  - default `disabled`
  - local development `local_cli`
  - future service deployment `remote`

- Add tests for:
  - disabled mode skips rendering
  - local CLI fake renderer succeeds
  - local CLI missing fails softly
  - remote renderer succeeds with mocked HTTP response
  - remote unavailable / non-200 fails softly
  - existing trend output still includes `.mmd` and summary Mermaid block

## Out Of Scope

- No independent `mermaid-renderer-service` implementation in this round.
- No Dockerfile for renderer service.
- No Mermaid CLI installation automation.
- No API endpoint changes.
- No `/api/tasks` changes.
- No xray changes.
- No `waf_audits` changes.
- No change to trend assessment logic.
- No numeric future extrapolation.

## Remote Contract Draft

The platform-side remote client should assume the future renderer service shape:

```text
GET /health
POST /render
```

V1 `POST /render` request:

```json
{
  "source": "flowchart LR\nA --> B",
  "format": "png"
}
```

Successful response:

```text
Content-Type: image/png
<PNG bytes>
```

Failure response may be JSON, but platform v1 only needs to treat it as a soft rendering failure.

## Default Behavior

Default mode should be `disabled` for deployment safety. This avoids requiring Mermaid CLI or a remote renderer service unless the operator explicitly enables rendering.

Recommended local development values:

```env
MERMAID_RENDERER_MODE=local_cli
MERMAID_CLI_PATH=mmdc
```

Recommended future server deployment values:

```env
MERMAID_RENDERER_MODE=remote
MERMAID_RENDERER_BASE_URL=http://mermaid-renderer-service:8091
```

## Acceptance Criteria

- Trend runs still succeed with `MERMAID_RENDERER_MODE=disabled`.
- Trend runs can generate `trend_state_graph.png` with a fake local CLI in tests.
- Trend runs can generate `trend_state_graph.png` with a mocked remote renderer in tests.
- Failed rendering never prevents `trend_input.json`, `trend_assessment.json`, `.mmd`, `trend_summary.md`, or normal metric PNG charts from being produced.
- Focused tests and full repository tests pass.

## Next Round

After this platform abstraction lands, implement:

```text
mermaid-renderer-service v1
  GET /health
  POST /render
  Dockerfile
  Node + Mermaid CLI encapsulation
```
