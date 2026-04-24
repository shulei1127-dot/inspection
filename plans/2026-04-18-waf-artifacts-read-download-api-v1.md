# WAF artifacts read/download API v1

## Goal

Let users retrieve WAF preprocessing and trend-enhancement outputs by id instead of reading local `workdir/` and `outputs/` paths manually.

## Scope

- Add preprocessing read/download endpoints:
  - `GET /api/waf/preprocessing/{preprocessing_id}`
  - `GET /api/waf/preprocessing/{preprocessing_id}/status-analysis`
- Add trend read/download endpoints:
  - `GET /api/waf/trend-enhancements/{trend_id}`
  - `GET /api/waf/trend-enhancements/{trend_id}/summary`
  - `GET /api/waf/trend-enhancements/{trend_id}/augmented-report`
- Resolve artifact paths strictly from ids.
- Reuse existing artifact contracts and summaries.

## Non-goals

- No frontend.
- No database.
- No listing endpoint.
- No cleanup endpoint.
- No regeneration.
- No changes to preprocessing / trend generation logic.
- No arbitrary path download.

## Implementation Plan

1. Add service lookup helpers for preprocessing artifacts.
2. Add service lookup helpers for trend artifacts.
3. Add endpoint handlers and `FileResponse` downloads.
4. Add tests for:
   - preprocessing detail
   - preprocessing status-analysis markdown download
   - trend detail
   - trend summary markdown download
   - trend augmented report download
   - missing artifact 404
   - invalid id format 400
5. Update README, API draft, and project status.
6. Run focused tests and full regression.

## Acceptance Criteria

- Users can retrieve markdown and DOCX artifacts through API calls.
- Id validation blocks path traversal and arbitrary file reads.
- Existing creation endpoints still pass.
- Full test suite remains green.
