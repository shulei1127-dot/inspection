## Goal

Define the phase-1 implementation plan for a new `雷池 WAF 巡检报告审核平台`
capability inside the current repository without affecting the existing x-ray
upload, analyzer, payload, template, or rendering flow.

This phase does not implement code. It only locks the first coding scope so the
next step can proceed with clear contracts and module ownership.

## Hard Boundaries

- do not modify `/api/tasks`
- do not modify the current x-ray main flow
- do not modify current x-ray schemas, template selection, template assets, or
  payload mapping
- new capability must use separate endpoints, separate schemas, and separate
  services
- phase 1 supports only:
  - `雷池 WAF`
  - one manual `docx` report
  - one corresponding log archive
- phase-1 output is fixed to `audit_opinion.md`
- do not expand into screenshot OCR, multi-product support, or automatic final
  report rewriting

## Expected Files To Add

Platform side:

- `app/api/endpoints/waf_audits.py`
- `app/schemas/report_claims.py`
- `app/schemas/log_evidence.py`
- `app/schemas/audit_result.py`
- `app/services/waf_audit_task_service.py`
- `app/services/manual_report_parser.py`
- `app/services/report_claim_normalizer.py`
- `app/services/audit_review_service.py`
- `app/services/audit_opinion_renderer.py`

Analyzer side:

- `log-analyzer-service/app/api/endpoints/waf_evidence.py`
- `log-analyzer-service/app/schemas/waf_evidence.py`
- `log-analyzer-service/app/services/waf_log_evidence_extractor.py`

Tests:

- `tests/test_waf_audit_endpoints.py`
- `tests/test_manual_report_parser.py`
- `tests/test_audit_review_service.py`
- `log-analyzer-service/tests/test_waf_evidence.py`

Potential docs update after implementation only if needed:

- `docs/project_status.md`

## 1. Schema Draft

### `report_claims.py`

Purpose:

- persist structured claims extracted from the manual `docx` report
- keep claim extraction separate from log evidence extraction

Suggested enums:

- `ClaimType`
  - `product_version`
  - `component_version`
  - `component_runtime_status`
  - `component_health_status`
  - `resource_usage_assessment`
  - `exception_presence`
  - `exception_cause`
  - `overall_inspection_conclusion`
- `ClaimAuditability`
  - `direct`
  - `partial`
  - `manual_only`

Suggested models:

- `ReportClaim`
  - `claim_id: str`
  - `claim_type: ClaimType`
  - `source_section: str | None`
  - `source_text: str`
  - `subject: str`
  - `metric: str | None`
  - `assertion: str`
  - `expected_value: str`
  - `auditability: ClaimAuditability`
- `ReportClaimsV1`
  - `schema_version: Literal["report-claims/v1"]`
  - `task_id: str`
  - `product_type: Literal["waf"]`
  - `claims: list[ReportClaim]`

Notes:

- raw report text should not be fully persisted in this schema
- only normalized, audit-relevant claims are included
- manual-only items may still appear here but will map to
  `无法由日志判断`

### `log_evidence.py`

Purpose:

- persist structured evidence extracted from the WAF log archive
- keep only stable, high-value fields that can support rule-based review

Suggested enums:

- `RuntimeStatus`
  - `running`
  - `stopped`
  - `failed`
  - `restarting`
  - `unknown`
- `HealthStatus`
  - `healthy`
  - `unhealthy`
  - `unknown`
- `ResourceMetric`
  - `cpu`
  - `memory`
  - `disk`
- `ResourceLevel`
  - `normal`
  - `high`
  - `critical`
  - `unknown`
- `FindingType`
  - `health_fail`
  - `restart`
  - `oom`
  - `error_log`
  - `disk_high`
  - `dependency_fail`
  - `port_bind_fail`

Suggested models:

- `RuntimeComponentEvidence`
  - `component_name: str`
  - `source_type: str`
  - `status: RuntimeStatus`
  - `health: HealthStatus`
  - `image_or_version: str | None`
  - `restart_signal: bool`
  - `evidence_text: str`
  - `source_refs: list[str]`
- `ResourceSignal`
  - `scope: str`
  - `subject: str`
  - `metric: ResourceMetric`
  - `observed_value: float | None`
  - `unit: str | None`
  - `level: ResourceLevel`
  - `threshold_hit: bool`
  - `raw_text: str`
  - `source_refs: list[str]`
- `LogFinding`
  - `finding_id: str`
  - `finding_type: FindingType`
  - `subject: str`
  - `severity: str`
  - `summary: str`
  - `evidence_text: str`
  - `source_refs: list[str]`
- `DerivedSummary`
  - `overall_runtime_state: str`
  - `abnormal_component_count: int`
  - `high_resource_items: list[str]`
  - `key_risks: list[str]`
- `LogEvidenceV1`
  - `schema_version: Literal["log-evidence/v1"]`
  - `task_id: str`
  - `product_type: Literal["waf"]`
  - `product_version: str | None`
  - `host_hostname: str | None`
  - `host_ip_list: list[str]`
  - `host_os_name: str | None`
  - `host_kernel_version: str | None`
  - `runtime_components: list[RuntimeComponentEvidence]`
  - `resource_signals: list[ResourceSignal]`
  - `log_findings: list[LogFinding]`
  - `derived_summary: DerivedSummary`

Notes:

- phase 1 intentionally avoids broad raw-log indexing
- evidence schema should stay review-oriented, not collector-oriented

### `audit_result.py`

Purpose:

- persist structured review output for each claim and the overall audit summary

Suggested enums:

- `AuditStatus`
  - `证实`
  - `部分证实`
  - `冲突`
  - `证据不足`
  - `无法由日志判断`

Suggested models:

- `ClaimReviewResult`
  - `claim_id: str`
  - `claim_type: str`
  - `status: AuditStatus`
  - `reason: str`
  - `evidence_refs: list[str]`
  - `suggested_revision: str | None`
- `AuditSummary`
  - `overall_conclusion: str`
  - `confirmed_count: int`
  - `partially_confirmed_count: int`
  - `conflict_count: int`
  - `insufficient_count: int`
  - `manual_only_count: int`
  - `key_conflicts: list[str]`
  - `key_risks: list[str]`
- `AuditResultV1`
  - `schema_version: Literal["audit-result/v1"]`
  - `task_id: str`
  - `product_type: Literal["waf"]`
  - `summary: AuditSummary`
  - `claim_results: list[ClaimReviewResult]`

Notes:

- `claim_results` are the system-of-record review outputs
- `audit_opinion.md` is a rendered summary derived from this schema

## 2. Endpoint Request / Response Draft

All new endpoints live outside `/api/tasks`.

### `POST /api/waf-audits`

Request:

- `multipart/form-data`
- fields:
  - `report_file`
  - `log_file`
  - `report_lang` default `zh-CN`

Behavior:

- store the uploaded `docx` and log archive
- parse manual report into raw claim candidates
- normalize claims into `report_claims.json`
- call analyzer-side WAF evidence extraction
- review claims against evidence
- render `audit_opinion.md`
- persist task record and return artifact paths

Success response shape:

- `task_id`
- `status`
- `report_file_path`
- `log_file_path`
- `report_claims_path`
- `log_evidence_path`
- `audit_result_path`
- `audit_opinion_path`
- `summary`
  - `claim_count`
  - `confirmed_count`
  - `conflict_count`

Error families:

- `missing_file`
- `unsupported_media_type`
- `report_parse_failed`
- `log_extract_failed`
- `review_failed`
- `internal_error`

### `GET /api/waf-audits`

Purpose:

- list latest WAF audit tasks

List item fields:

- `task_id`
- `status`
- `created_at`
- `report_filename`
- `log_filename`
- `claim_count`
- `conflict_count`
- `audit_opinion_path`

### `GET /api/waf-audits/{task_id}`

Purpose:

- return one WAF audit task summary and artifact paths

Response fields:

- `task_id`
- `status`
- `report_file_path`
- `log_file_path`
- `report_claims_path`
- `log_evidence_path`
- `audit_result_path`
- `audit_opinion_path`
- `summary`

### `GET /api/waf-audits/{task_id}/claims`

Purpose:

- return parsed and normalized claims

Response:

- `ReportClaimsV1`

### `GET /api/waf-audits/{task_id}/audit-result`

Purpose:

- return structured audit result

Response:

- `AuditResultV1`

### `GET /api/waf-audits/{task_id}/audit-opinion`

Purpose:

- download or return the rendered markdown audit opinion

Response:

- markdown file or text response for `audit_opinion.md`

## 3. Service Call Order

### Orchestrator: `waf_audit_task_service`

Primary responsibility:

- own the end-to-end task lifecycle for the new WAF review flow
- keep the new flow isolated from the current x-ray task flow

Phase-1 sequence:

1. validate `report_file` and `log_file`
2. create task id and task record with status `parsing_report`
3. persist uploads under task-specific paths
4. call `manual_report_parser`
5. call `report_claim_normalizer`
6. update task status to `extracting_evidence`
7. call analyzer-side `waf_log_evidence_extractor`
8. persist `log_evidence.json`
9. update task status to `reviewing`
10. call `audit_review_service`
11. persist `audit_result.json`
12. call `audit_opinion_renderer`
13. persist `outputs/{task_id}/audit_opinion.md`
14. update task status to `completed`

Failure handling:

- any failure updates the task to `failed`
- detailed failure cause remains in `error_code` and `error_message`
- failed tasks should keep already generated intermediate artifacts when useful
  for debugging

### `manual_report_parser`

Responsibility:

- extract review-relevant text fragments from `docx`
- focus on paragraphs, headings, and tables
- do not normalize into final claims yet

Output:

- intermediate raw report fragments in memory or a narrow internal structure

Scope for phase 1:

- version text
- deployment/basic environment text
- runtime status tables
- resource assessment text
- exception summary text
- final conclusion text

### `report_claim_normalizer`

Responsibility:

- convert raw report fragments into `ReportClaim` entries
- map free-form wording into the fixed phase-1 claim types

Normalization approach:

- section-title cues
- table header mapping
- keyword mapping
- conservative subject normalization

Non-goal:

- broad semantic extraction driven by LLM

### `waf_log_evidence_extractor`

Responsibility:

- extract phase-1 WAF evidence fields from the log archive
- output `LogEvidenceV1`

Placement:

- analyzer service side

Non-goal:

- generate report claims
- generate review verdicts

### `audit_review_service`

Responsibility:

- apply deterministic review rules by `claim_type`
- generate `AuditResultV1`

Rule order:

1. detect manual-only / not-log-auditable claims
2. detect hard conflicts
3. detect full confirmation
4. detect partial confirmation
5. fall back to insufficient evidence

Non-goal:

- free-form black-box reasoning

### `audit_opinion_renderer`

Responsibility:

- render `audit_result.json` into `audit_opinion.md`
- keep wording compact, readable, and grouped by review outcome

Suggested markdown sections:

1. 总体审核结论
2. 已证实项
3. 冲突项
4. 证据不足 / 无法由日志判断项
5. 建议修订项

Non-goal:

- final customer-facing polished report replacement

## 4. Test Checklist

### A. Report parsing

- parse `docx` paragraphs and tables into review-relevant raw fragments
- extract at least:
  - version claim candidate
  - runtime-status claim candidate
  - resource-assessment claim candidate
  - overall conclusion candidate
- ensure unsupported or irrelevant sections do not break parsing

### B. Evidence extraction

- extract stable WAF evidence from a representative fixture log bundle
- verify:
  - product version
  - runtime component statuses
  - resource signals
  - key findings
  - derived summary
- verify missing files degrade gracefully instead of crashing

### C. Claim review verdicts

- `product_version`
  - confirmed
  - conflict
  - insufficient evidence
- `component_runtime_status`
  - confirmed
  - partial
  - conflict
- `resource_usage_assessment`
  - confirmed when threshold + anomaly evidence both exist
  - partial when threshold hit exists without anomaly evidence
  - conflict when report says abnormal but evidence is below threshold
- `exception_cause`
  - confirmed when direct cause evidence exists
  - partial when only correlation exists
  - insufficient when anomaly exists but cause is unsupported
- `overall_inspection_conclusion`
  - confirmed
  - partial
  - conflict

### D. Audit opinion rendering

- render markdown successfully from a valid `AuditResultV1`
- include all fixed sections
- include conflict items and suggested revisions
- handle empty sections without malformed output

### E. Endpoint flow

- `POST /api/waf-audits` end-to-end success
- `GET /api/waf-audits` returns latest-first list
- `GET /api/waf-audits/{task_id}` returns artifact paths
- `GET /claims` returns `ReportClaimsV1`
- `GET /audit-result` returns `AuditResultV1`
- `GET /audit-opinion` returns markdown content

### F. Regression isolation

- existing `/api/tasks` tests stay green
- existing x-ray upload flow stays green
- existing x-ray template selector tests stay green
- existing x-ray render path stays green
- no shared schema changes leak into current x-ray payload contracts

## Acceptance For Phase-1 Implementation

1. A WAF audit task can accept one manual `docx` report and one matching log bundle.
2. The system persists:
   - `report_claims.json`
   - `log_evidence.json`
   - `audit_result.json`
   - `audit_opinion.md`
3. The review output uses only the fixed phase-1 audit statuses.
4. The review logic is rule-first and does not depend on black-box model
   judgments.
5. Existing x-ray behavior remains unchanged.
