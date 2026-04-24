## Goal

Use one real `雷池 WAF` manual `docx` report plus one corresponding real log
bundle to validate the new phase-1 `waf_audits` chain, then perform one narrow
rule-tuning round based only on issues exposed by that real sample.

## Scope

This round covers only:

1. real-sample end-to-end acceptance
2. narrow rule tuning based on the observed sample output
3. one structured replay / review summary

## Hard Boundaries

- do not expand OCR or screenshot parsing
- do not add multi-product support
- do not modify the current x-ray flow
- do not change `/api/tasks`
- do not refactor the new WAF chain broadly
- keep phase-1 output fixed to `audit_opinion.md`

## Expected Files To Touch

- `app/services/manual_report_parser.py`
- `app/services/report_claim_normalizer.py`
- `app/services/audit_review_service.py`
- `app/services/audit_opinion_renderer.py`
- `app/services/waf_audit_task_service.py`
- `log-analyzer-service/app/services/waf_log_evidence_extractor.py`
- focused tests for the touched rule areas
- `docs/project_status.md`

## Acceptance Focus

For the provided real sample, explicitly review:

- whether `report_claims.json` extracts useful and correctly typed claims
- whether `log_evidence.json` has enough stable support signals
- whether `audit_result.json` verdicts feel appropriately strong or conservative
- whether `audit_opinion.md` reads like a usable review memo

## Rule-Tuning Focus

Only tighten:

- component name normalization
- exception type mapping
- exception cause mapping
- overall conclusion wording
- the boundary between:
  - `冲突`
  - `证据不足`
  - `无法由日志判断`

## Deliverable

At the end of this round, provide:

- actual modified files
- local verification results
- short real-sample replay summary
- explicit review of:
  - correct claims
  - missed / wrong claims
  - useful evidence
  - over-strong / over-weak verdicts
  - next-best rule improvements
