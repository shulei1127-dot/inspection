# WAF audit use preprocessing_id v1

## Goal

Change the WAF audit flow from "manual DOCX + full WAF log archive" to "manual DOCX + existing WAF preprocessing result". The full WAF log archive should be uploaded only once through `/waf`, and report audit should reuse the generated `preprocessing_id`.

## Current Problem

Current frontend/API flow:

```text
/waf
  WAF full-log archive -> POST /api/waf/preprocessing -> preprocessing_id

/waf-audits/ui
  manual report DOCX + WAF full-log archive -> POST /api/waf-audits
```

This causes:

- large WAF logs are uploaded twice
- preprocessing artifacts are not reused
- WAF audit duplicates evidence extraction responsibilities
- users cannot clearly understand whether audit is based on raw logs or cleaned evidence

## Target Flow

```text
1. /waf
   upload WAF full-log archive
   -> preprocessing_id
   -> status_analysis_summary.json
   -> 状态分析报告.md

2. /waf-audits/ui
   upload manual report DOCX
   input/select preprocessing_id
   -> audit reads cleaned preprocessing artifacts
   -> report_claims.json
   -> log_evidence.json or preprocessing_evidence.json
   -> audit_result.json
   -> audit_opinion.md
```

## Scope

### 1. API shape

Add or extend the existing `POST /api/waf-audits` contract to support:

```text
report_file: DOCX upload, required
preprocessing_id: string, required in new frontend flow
report_lang: string, optional, default zh-CN
```

Recommended compatibility strategy:

- keep the existing `log_file` parameter optional for one transition round
- if `preprocessing_id` is provided, use preprocessing artifacts and ignore `log_file`
- if `preprocessing_id` is missing but `log_file` is provided, keep old behavior for compatibility
- frontend should only expose the new `preprocessing_id` path

This avoids breaking existing tests and API users while making the correct path the default.

### 2. Service layer

Add a new service entry point, for example:

```python
create_waf_audit_from_preprocessing(
    report_upload: UploadFile | None,
    preprocessing_id: str,
    report_lang: str = "zh-CN",
) -> WafAuditCreateData
```

Responsibilities:

- validate DOCX upload
- validate `preprocessing_id` format and existence
- read preprocessing metadata via existing WAF preprocessing result lookup
- load cleaned artifacts, priority:
  - `status_analysis_summary.json`
  - `status_analysis_evidence.json`
  - `状态分析报告.md`
- convert cleaned preprocessing artifacts into the existing `LogEvidenceV1` shape, or introduce a very small adapter layer if direct mapping is safer
- reuse existing report parsing:
  - `parse_manual_report`
  - `normalize_report_claims`
  - `review_report_claims`
  - `render_audit_opinion_markdown`

### 3. Data model and response

Keep response contract mostly compatible:

```json
{
  "task_id": "waf_audit_...",
  "status": "completed",
  "report_file_path": "...",
  "log_file_path": null,
  "preprocessing_id": "prep_...",
  "report_claims_path": "...",
  "log_evidence_path": "...",
  "audit_result_path": "...",
  "audit_opinion_path": "...",
  "summary": {}
}
```

Minimal schema updates:

- add optional `preprocessing_id` to `WafAuditCreateData`
- allow `log_file_path` to be `str | None`
- add optional `preprocessing_id` to `WafAuditResultData`

Repository persistence options:

- preferred v1: add nullable `preprocessing_id` column to WAF audit records if the repository currently has a stable place to extend
- fallback v1: store `preprocessing_id` in `workdir/{task_id}/audit_source.json` and return it from artifacts if repository schema extension is too invasive

Decision during implementation should favor the smallest safe change.

### 4. Frontend changes

Update `/waf`:

- show the returned `preprocessing_id` prominently
- add one-click copy for `preprocessing_id`
- keep the status-analysis and preprocessing-detail links
- make the copy failure non-blocking and keep the ID visible for manual copy

Update `/waf-audits/ui`:

- remove WAF full-log archive upload from the visible default form
- add `preprocessing_id` text input
- add helper copy:
  - "先在 /waf 上传并清洗日志，复制 preprocessing_id 到这里"
- keep manual report DOCX upload required
- submit:
  - `report_file`
  - `preprocessing_id`
  - `report_lang`
- result links remain:
  - task detail JSON
  - claims JSON
  - audit-result JSON
  - audit-opinion Markdown

Optional UI nicety:

- add a small link back to `/waf` with label "先去清洗 WAF 日志"

### 5. Evidence mapping strategy

v1 should not re-run full evidence extraction from raw logs.

Use cleaned preprocessing artifacts as evidence:

- `status_analysis_summary.json` provides structured counts, resource summary, service findings, scan limitations
- `status_analysis_evidence.json` provides lower-level evidence snippets and source coverage
- `状态分析报告.md` provides readable fallback evidence

The mapping should stay conservative:

- do not invent evidence not present in preprocessing artifacts
- preserve coverage warnings so audit can explain "日志证据不足"
- if a claim cannot be confirmed from cleaned data, mark it as unknown / insufficient evidence rather than conflict by default

### 6. Tests

Add or update tests for:

- `POST /api/waf-audits` succeeds with `report_file + preprocessing_id`
- frontend `/waf-audits/ui` no longer asks for WAF full-log upload by default
- invalid `preprocessing_id` returns a stable error
- missing preprocessing artifacts returns a stable error
- old `report_file + log_file` API path remains compatible if compatibility is kept
- audit output still includes claims, audit result, and audit opinion artifacts

### 7. Docs

Update:

- `README.md`
- `docs/project_status.md`
- `docs/waf_api_v1_draft.md` if needed

Document the intended user flow:

```text
/waf -> preprocessing_id -> /waf-audits/ui + DOCX -> audit opinion
```

## Non-goals

- Do not remove WAF preprocessing API.
- Do not remove WAF trend-enhancement API.
- Do not implement final Word report generation in this round.
- Do not implement a preprocessing task picker/list UI yet.
- Do not re-run full log extraction during audit when `preprocessing_id` is provided.
- Do not add LLM-based audit judgment.

## Acceptance Criteria

- A user can upload WAF full logs once on `/waf`.
- The user can copy the returned `preprocessing_id`.
- The user can open `/waf-audits/ui`, upload only the Word report, paste `preprocessing_id`, and generate audit artifacts.
- The frontend no longer asks users to upload the full WAF log archive a second time.
- Existing WAF audit result downloads still work.
- Focused tests pass.
