# WAF API readiness prep v1

## Goal

Prepare the WAF preprocessing and trend-enhancement chain for future API exposure without adding new endpoints in this round.

## Scope

- Keep current offline-first services and scripts as the source of truth.
- Fix the current duplicate-sample risk where a generated `resource_history.csv` single point and a current snapshot from the same collection can be counted as two trend samples.
- Add an API draft document for the next implementation round.
- Keep `/api/tasks`, xray, `waf_audits`, analyzer routing, and parser logic unchanged.

## Non-goals

- No new FastAPI endpoints.
- No frontend.
- No database table changes.
- No report-template changes.
- No new trend prediction model.

## Implementation Plan

1. Add a plan file for this round.
2. Update `trend_input_builder` metric sample de-duplication:
   - preserve legitimate multi-point history
   - collapse same-metric / same-value / same-12-hour-bucket duplicates when one point comes from canonical `resources/resource_history.csv`
   - prefer the canonical resource-history sample over the current snapshot sample
3. Add focused tests proving a single generated resource-history point plus same-collection snapshot stays single-point and does not trigger chart-ready behavior.
4. Add `docs/waf_api_v1_draft.md` covering:
   - future endpoint candidates
   - request / response shapes
   - artifact conventions
   - failure behavior
   - explicit non-goals
5. Update README / `docs/project_status.md` minimally.
6. Run focused tests and full regression.

## Acceptance Criteria

- Snapshot + generated resource-history duplicate points no longer produce fake two-point trends.
- Existing multi-point fixtures still produce real multi-point samples.
- The API draft makes clear that this round does not expose endpoints yet.
- Full test suite remains green.
