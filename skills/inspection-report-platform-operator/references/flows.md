# Local Flow Map

## Standard stack

Run in this order:

1. `scripts/bootstrap_local_env.sh`
2. `scripts/start_local_stack.sh`
3. `scripts/verify_local_stack.sh`

Default local ports in a fresh checkout:

- platform: `8000`
- analyzer: `8090`
- Carbone: `4000`

The actual runtime may differ if `.env` overrides them. Prefer the values printed by `scripts/start_local_stack.sh`.

## Xray flow

Browser path:

- page: `/xray`
- upload endpoint: `POST /api/tasks`
- task detail: `GET /api/tasks/{task_id}`
- manual render retry: `POST /api/tasks/{task_id}/render-report`
- DOCX download: `GET /api/tasks/{task_id}/report`

Main artifacts:

- `workdir/{task_id}/unified.json`
- `workdir/{task_id}/report_payload.json`
- `outputs/{task_id}/report.docx`

## WAF preprocessing flow

Browser path:

- page: `/waf`
- upload endpoint: `POST /api/waf/preprocessing`

Main artifacts:

- `workdir/prep_*/status_analysis_evidence.json`
- `workdir/prep_*/status_analysis_summary.json`
- `workdir/prep_*/状态分析报告.md`

## WAF audit flow

Browser path:

- page: `/waf-audits/ui`
- audit endpoint: `POST /api/waf-audits`
- document-only endpoint: `POST /api/waf-audits/document-only`

Main artifacts:

- `workdir/waf_audit_*/report_claims.json`
- `workdir/waf_audit_*/log_evidence.json` when log-grounded
- `workdir/waf_audit_*/document_review_input.json` when document-only
- `workdir/waf_audit_*/audit_result.json`
- `outputs/waf_audit_*/audit_opinion.md`
- `outputs/waf_audit_*/audit_augmented_report.docx`

## LLM modes

The repository can run without any LLM configuration.

LLM takes effect only when the matching env vars are enabled, for example:

- xray summary sections: `XRAY_LLM_SECTION_*`
- WAF document review / grounded review: `WAF_LLM_REVIEW_*`
