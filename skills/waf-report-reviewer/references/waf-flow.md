# WAF Flow

## Mode 1: preprocessing only

Use when the user wants cleaned WAF status-analysis artifacts from a full-log archive.

- page: `/waf`
- endpoint: `POST /api/waf/preprocessing`

Outputs include:

- `status_analysis_evidence.json`
- `status_analysis_summary.json`
- `状态分析报告.md`

## Mode 2: log-grounded audit

Use when the user has:

- a WAF report DOCX
- a `preprocessing_id`

Path:

1. run preprocessing
2. capture `preprocessing_id`
3. submit the report through `/waf-audits/ui` or `POST /api/waf-audits`

Outputs include:

- `report_claims.json`
- `log_evidence.json`
- `audit_result.json`
- `audit_opinion.md`
- `audit_augmented_report.docx`

## Mode 3: document-only review

Use when only the report DOCX exists.

- endpoint: `POST /api/waf-audits/document-only`

Outputs include:

- `document_review_input.json`
- `audit_result.json`
- `audit_opinion.md`
- `audit_augmented_report.docx`

This mode must remain conservative in wording.
