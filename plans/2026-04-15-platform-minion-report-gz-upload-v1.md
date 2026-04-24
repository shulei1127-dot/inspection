## Goal

Let the platform accept xray's built-in `minion_report.gz` archive directly and
keep the existing `upload -> analyze -> unified.json -> report_payload.json`
chain working without renaming the file first.

## Scope

- Keep the existing `POST /api/tasks` API shape
- Accept the native upload name `minion_report.gz`
- Reuse the existing tar-based validation and extraction path
- Keep the current analyzer contract unchanged
- Add a focused platform-side test that proves:
  - native `minion_report.gz` upload is accepted
  - extraction lands in `workdir/{task_id}/`
  - analyzer output is persisted to `unified.json`
  - xray payload mapping reaches `report_payload.json`
- Update docs to state the native xray upload path clearly

## Non-goals

- No analyzer archive-upload API
- No platform-side parser refactor
- No broader `.gz` upload support for arbitrary products
- No DOCX render runtime changes in this iteration

## Safety Rules

- Keep archive acceptance narrow and explicit
- Continue using tar validation for the native xray bundle
- Keep task archive discovery compatible with `.gz` artifacts once stored

## Validation

1. Run focused platform tests covering `minion_report.gz` upload.
2. Re-run analyzer tests to confirm the existing `minion_report` parser path still passes.
