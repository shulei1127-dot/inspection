---
name: waf-report-reviewer
description: Run the WAF preprocessing, WAF audit, and WAF document-only review flows in the inspection-report-platform repository. Use when an AI agent needs to preprocess WAF logs, reuse a preprocessing_id, audit a WAF report against log-derived evidence, or review a WAF report directly and generate document-grounded abnormal handling advice.
---

# WAF Report Reviewer

Use this skill when the goal is to work on the WAF side of the repository.

If the repository runtime is not already healthy, first use the `inspection-report-platform-operator` skill to bootstrap and verify the stack.

## Supported Modes

### Log-grounded mode

Use when both WAF logs and a WAF report are available.

Typical path:

1. preprocessing
2. obtain `preprocessing_id`
3. WAF audit with the report DOCX

### Document-only mode

Use when only the report DOCX is available.

This mode may generate `异常情况及处置操作` and `巡检总结`, but it must stay conservative and must not claim log-grounded verification.

## Entry Points

- browser page: `/waf`
- browser page: `/waf-audits/ui`
- preprocessing endpoint: `POST /api/waf/preprocessing`
- audit endpoint: `POST /api/waf-audits`
- document-only endpoint: `POST /api/waf-audits/document-only`

## Expected Artifacts

Preprocessing:

- `status_analysis_evidence.json`
- `status_analysis_summary.json`
- `状态分析报告.md`

Audit:

- `report_claims.json`
- `log_evidence.json` for log-grounded mode
- `document_review_input.json` for document-only mode
- `audit_result.json`
- `audit_opinion.md`
- `audit_augmented_report.docx`

## LLM Boundary

- WAF can run without any LLM configuration
- WAF LLM review only activates when `WAF_LLM_REVIEW_*` env vars are enabled and the platform has been restarted
- document-only mode must never pretend that log verification happened when it did not

## Troubleshooting

Read `references/waf-flow.md` when you need the exact preprocessing/audit/document-only sequence.

Read `references/waf-troubleshooting.md` when:

- you need to decide between log-grounded and document-only mode
- the review wording seems too strong for the available evidence
- the expected preprocessing or audit artifacts are missing
