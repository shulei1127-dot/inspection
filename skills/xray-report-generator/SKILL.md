---
name: xray-report-generator
description: Generate xray inspection reports from supported xray log archives in the inspection-report-platform repository. Use when an AI agent needs to operate the xray flow, upload or submit xray logs, inspect unified.json or report_payload.json, verify rendered DOCX output, or troubleshoot xray-specific report generation issues.
---

# Xray Report Generator

Use this skill when the goal is to turn an xray log archive into a rendered inspection DOCX.

If the repository runtime is not already healthy, first use the `inspection-report-platform-operator` skill to bootstrap and verify the stack.

## Primary Flow

1. Confirm the local stack is healthy.
2. Use the xray page or xray task APIs.
3. Inspect task status.
4. Inspect `unified.json` and `report_payload.json` when the output looks incomplete.
5. Confirm the final `report.docx`.

## Entry Points

- browser page: `/xray`
- upload endpoint: `POST /api/tasks`
- task detail: `GET /api/tasks/{task_id}`
- manual render retry: `POST /api/tasks/{task_id}/render-report`
- DOCX download: `GET /api/tasks/{task_id}/report`

Use the browser page when the user wants a visible upload flow.
Use the APIs when the user already gave a local archive path and wants automation.

## Expected Artifacts

- `workdir/{task_id}/unified.json`
- `workdir/{task_id}/report_payload.json`
- `outputs/{task_id}/report.docx`

Treat statuses as:

- `rendered`: end-to-end success
- `completed`: analysis and payload are ready, but DOCX is not yet rendered
- `render_failed`: render-stage failure
- `analyze_failed`: analyzer-stage failure

## LLM Boundary

- xray can run without any LLM configuration
- xray summary enhancement only activates when `XRAY_LLM_SECTION_*` env vars are enabled and the platform has been restarted
- do not assume a missing LLM response means the xray base flow is broken

## Troubleshooting

Read `references/xray-troubleshooting.md` when:

- the DOCX has many empty fields
- old tasks look richer than new tasks
- task status is `completed` instead of `rendered`
- xray LLM summary sections do not appear

Read `references/xray-flow.md` when you need the detailed xray API/page/artifact mapping.
