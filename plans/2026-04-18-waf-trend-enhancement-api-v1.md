# WAF trend enhancement API v1

## Goal

Expose the existing WAF trend-enhancement service through one minimal API endpoint that consumes a completed WAF preprocessing run.

## Scope

- Add `POST /api/waf/trend-enhancements`.
- Accept `preprocessing_id`.
- Optionally accept one base DOCX report to append the trend appendix.
- Resolve `workdir/{preprocessing_id}/status_analysis.md`.
- Call the existing `run_trend_enhancement()` service.
- Return structured paths for `trend_input.json`, `trend_assessment.json`, `trend_summary.md`, Mermaid artifacts, chart files, and optional `augmented_report.docx`.

## Non-goals

- No trend listing or detail endpoints.
- No download endpoint yet.
- No frontend.
- No database table.
- No changes to `/api/tasks`, xray, `waf_audits`, preprocessing output semantics, or trend rules.
- No new prediction model.

## Implementation Plan

1. Add WAF trend enhancement response/error schemas.
2. Add a thin service that:
   - validates `preprocessing_id`
   - resolves the preprocessing markdown artifact
   - validates optional DOCX input
   - calls `run_trend_enhancement()`
   - summarizes generated `trend_input.json` and `trend_assessment.json`
3. Add `app/api/endpoints/waf_trend_enhancements.py`.
4. Register the endpoint in `app/api/router.py`.
5. Add endpoint tests for:
   - preprocessing id happy path
   - optional DOCX augmentation
   - missing preprocessing id artifact
   - invalid DOCX upload
6. Update README, `docs/waf_api_v1_draft.md`, and `docs/project_status.md`.
7. Run focused tests and full regression.

## Acceptance Criteria

- `POST /api/waf/trend-enhancements` returns `201` with `success=true` for a valid preprocessing id.
- Single-snapshot preprocessing output remains conservative and does not generate fake trend charts.
- Optional DOCX upload produces `augmented_report.docx`.
- Existing offline script remains usable.
- Full test suite remains green.
