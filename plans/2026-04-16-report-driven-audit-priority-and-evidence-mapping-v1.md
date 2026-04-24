## Goal

Tighten the phase-1 `waf_audits` chain so it behaves as a report-driven audit
workflow instead of a log-led comparison workflow.

## Scope

This round only covers:

1. add claim priority to the parsed manual-report claims
2. make log back-checking claim-driven and explicit
3. define clearer claim-to-evidence mapping
4. upgrade the audit opinion structure

## Boundaries

- do not touch x-ray flow
- do not change `/api/tasks`
- do not add OCR
- do not add multi-product support
- do not auto-rewrite final formal reports

## Expected Changes

- `app/schemas/report_claims.py`
- `app/schemas/audit_result.py`
- `app/services/report_claim_normalizer.py`
- `app/services/audit_review_service.py`
- `app/services/audit_opinion_renderer.py`
- focused tests under `tests/`

## Acceptance

- report claims expose `high / medium / manual_only` priority
- claim records expose explicit evidence targets
- review logic uses claim-driven evidence lookup instead of only implicit per-type guessing
- audit opinion markdown clearly separates:
  - 已核验
  - 冲突 / 需修订
  - 证据不足
  - 仍需人工判断
- existing x-ray and current platform tests remain green
