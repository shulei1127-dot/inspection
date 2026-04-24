# WAF preprocessing API v1

## Goal

Expose the existing offline WAF full-log preprocessing chain through one minimal upload API.

## Scope

- Add `POST /api/waf/preprocessing`.
- Accept one WAF log archive upload.
- Safely persist and extract the archive.
- Resolve the extracted analysis root.
- Call the existing `run_log_preprocessing()` service.
- Return structured artifact paths:
  - `resource_history_csv_path`
  - `status_analysis_evidence_path`
  - `status_analysis_summary_path`
  - `status_analysis_md_path`
- Keep trend enhancement API out of this round.

## Non-goals

- No frontend.
- No trend-enhancement endpoint.
- No database table.
- No background jobs.
- No changes to `/api/tasks`, xray, or `waf_audits`.
- No parser or trend heuristic changes.

## Implementation Plan

1. Add WAF preprocessing response/error schemas.
2. Add a thin WAF preprocessing task service for upload validation, archive extraction, and artifact summary.
3. Add `app/api/endpoints/waf_preprocessing.py`.
4. Register the endpoint in `app/api/router.py`.
5. Add endpoint tests for:
   - successful archive upload
   - unsupported archive type
   - invalid archive
   - safe extraction / artifact path existence
   - resource history summary count
6. Update README, `docs/waf_api_v1_draft.md`, and `docs/project_status.md`.
7. Run focused tests and full regression.

## Acceptance Criteria

- `POST /api/waf/preprocessing` returns `201` with `success=true`.
- The response includes a `preprocessing_id` and all generated artifact paths.
- Uploaded archives are validated and path traversal is rejected.
- Existing offline scripts continue to work.
- Full test suite remains green.
