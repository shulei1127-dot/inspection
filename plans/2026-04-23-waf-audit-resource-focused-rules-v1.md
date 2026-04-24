# WAF audit resource-focused rules v1

## Goal

Adjust WAF audit rules so device information in the report is treated as report-provided metadata rather than something that must be verified from logs. The audit should focus mainly on CPU, memory, and disk resource status.

## Scope

- Stop promoting product/component version rows into log-backed audit claims during WAF report claim normalization.
- Treat explicit product/component version claims as manual/report-sourced if they appear from another path.
- Keep CPU / memory / disk resource claims log-backed and reviewable.
- Keep existing manual-only behavior for UI/config/business checks.
- Update tests to reflect the narrower audit scope.
- Update project status notes.

## Non-goals

- Do not remove device information from the original Word report.
- Do not rewrite the original report body.
- Do not add LLM judgment.
- Do not change WAF preprocessing.
- Do not remove exception or overall conclusion rules in this round, but resource checks are the primary focus.

## Verification

- `pytest tests/test_report_claim_normalizer.py tests/test_audit_review_service.py tests/test_waf_audit_endpoints.py tests/test_report_augmenter.py`
