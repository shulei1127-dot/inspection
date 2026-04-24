# Trend Mermaid Image Rendering v1

## Background

Mermaid text v1 is already stable:

- `trend_state_graph.mmd` is generated from `trend_assessment.json`
- the Mermaid block is embedded in `trend_summary.md`
- the graph focuses on the current highest-risk metric
- the flow remains offline-first and does not touch `/api/tasks`, xray, or `waf_audits`

The next step is to add optional image rendering so the existing Mermaid source can become a PNG artifact when a local Mermaid CLI runtime is available.

## Goal

Add an optional Mermaid image rendering layer:

```text
trend_state_graph.mmd
  -> optional mmdc
  -> outputs/trd_*/trend_state_graph.png
```

This must not make Node.js, Chromium, or Mermaid CLI a required dependency for the current trend workflow.

## Scope

In scope:

- Add a small renderer that calls Mermaid CLI (`mmdc`) when available.
- Keep rendering optional and non-blocking.
- Preserve `.mmd` generation even when image rendering is unavailable.
- Write rendered PNG to `outputs/trd_*/trend_state_graph.png`.
- If a base DOCX is provided and PNG rendering succeeds, include the Mermaid PNG in the existing trend appendix image list.
- Add config knobs:
  - `MERMAID_RENDERING_ENABLED`
  - `MERMAID_CLI_PATH`
  - `MERMAID_CLI_TIMEOUT_SECONDS`
- Add tests for:
  - missing CLI skips cleanly
  - fake CLI can render a target PNG
  - trend enhancement artifact exposes the optional PNG path

## Out Of Scope

- No Mermaid CLI installation automation.
- No Node.js / Chromium dependency in `requirements.txt`.
- No API changes.
- No xray changes.
- No `waf_audits` changes.
- No change to existing metric PNG chart behavior.
- No numeric future extrapolation.

## Failure Behavior

Rendering failures must not fail the trend enhancement run:

- missing CLI: skip and return no image path
- disabled rendering: skip and return no image path
- CLI timeout/non-zero exit: skip and return no image path
- `.mmd` file remains available for later manual or automated rendering

## Acceptance Criteria

- Trend runs continue to work when `mmdc` is not installed.
- If `mmdc` is available, `outputs/trd_*/trend_state_graph.png` is generated.
- If PNG is generated and a base DOCX is provided, the PNG can be appended through the existing DOCX augmentation path.
- Focused tests and full repository tests pass.
