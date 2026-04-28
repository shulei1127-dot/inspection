## Goal

Add a minimal, safe LLM section-generation layer for the x-ray report flow so the
final DOCX can use model-generated:

- inspection summary
- major exception summary
- disposal advice

while keeping all fact tables, metadata fields, and parser-derived values fully
rule-based.

## Background

Current x-ray flow:

1. upload x-ray archive
2. extract into `workdir/{task_id}`
3. remote analyzer parses logs into `unified.json`
4. platform maps `unified.json` into `report_payload.json`
5. Carbone renders `report.docx`

The current rule chain is already good at producing factual fields:

- product / engine / vuln-db versions
- machine id
- IP and node info
- health check results
- CPU / memory / disk values
- service and container rows
- rule-based issues and priorities

The next step is not to replace this fact layer, but to let an LLM generate the
report’s summary-style sections from those facts.

## Round1 Scope

Round1 only lets the LLM generate these x-ray report sections:

- `xray_llm_inspection_summary`
- `xray_llm_exception_summary`
- `xray_llm_disposal_advice`

Round1 should also map these into the final template payload in a narrow way.

If the current DOCX template does not yet contain dedicated placeholders for all
three sections, round1 may:

- add them as new appendix fields in `report_payload.json`
- keep existing rule-based fields untouched
- optionally mirror one LLM section into an existing summary paragraph field only
  after explicit validation

## Explicit Non-goals

- do not let the LLM parse raw x-ray archives
- do not let the LLM modify `unified.json`
- do not let the LLM rewrite versions, machine id, IPs, health-check results,
  resource values, service states, or container states
- do not replace the existing issue generation logic
- do not replace the whole `report_payload.json` generation path
- do not broaden this round to WAF or other products

## Design Principle

### Fact layer remains rule-based

These stay authoritative:

- `unified.json`
- `issue_rows`
- `container_rows`
- `service_rows`
- x-ray metadata fields
- x-ray observation priority rules

### LLM only owns summary-style sections

The model should not build tables or low-level factual payload fields.

Its role is:

1. summarize the current inspection state
2. describe major abnormal situations in formal report tone
3. propose disposal advice tied to the supplied evidence

## Proposed Architecture

### 1. Keep the existing mapper as the fact payload builder

`app/services/report_payload_mapper.py` continues to build:

- report meta
- host info
- service/container rows
- issue rows
- appendix fact fields

### 2. Add a dedicated x-ray LLM section service

Suggested file:

- `app/services/xray_llm_section_service.py`

Responsibilities:

- build a compact x-ray LLM input context from `UnifiedJsonV1` and mapped payload
- call the provider adapter
- validate structured output
- return a narrow section result object

### 3. Add a narrow provider client

Suggested file:

- `app/services/llm_client.py`

Round1 provider mode:

- `disabled`
- `remote_api`

The remote mode should target an OpenAI-compatible chat completions endpoint.

### 4. Merge LLM sections after fact payload generation

Suggested execution order:

1. analyzer creates `unified.json`
2. mapper creates normal `report_payload.json`
3. if x-ray and LLM section generation enabled:
   - build LLM input
   - request section output
   - validate output
   - merge only the LLM section fields into payload appendix
4. persist final payload
5. render DOCX with Carbone

## LLM Input Contract

Do not send raw logs.

Round1 should send a compact structured summary such as:

```json
{
  "product_type": "xray",
  "overall_status": "warning",
  "executive_status": "整体状态为告警，存在需要优先处理的运行风险",
  "primary_problem": "管理节点健康检查告警",
  "key_alerts": [
    "管理节点健康检查告警（失败项：HEALTH COMMAND ERROR）",
    "引擎节点健康检查告警（失败项：REDIS PORT STATUS）",
    "管理节点磁盘使用率偏高（98.00%）"
  ],
  "resource_signals": {
    "mgmt_cpu": "...",
    "mgmt_memory": "...",
    "mgmt_disk": "..."
  },
  "health_checks": {
    "mgmt": {"result": "告警", "note": "..."},
    "engine": {"result": "告警", "note": "..."}
  },
  "top_issue_rows": [
    {"title": "...", "description": "...", "suggestion": "..."}
  ],
  "rule_based_recommendations": [
    "...",
    "..."
  ]
}
```

## LLM Output Contract

Require strict JSON output:

```json
{
  "inspection_summary": "...",
  "exception_summary": "...",
  "disposal_advice": "..."
}
```

Validation rules:

- all three fields required
- Chinese only
- non-empty strings
- no markdown tables
- no fabricated factual values

## Prompt Constraints

Round1 prompt must explicitly require:

- only use supplied facts
- do not invent versions, IPs, machine ids, statuses, or percentages
- if evidence is insufficient, use `需进一步核查`
- output Chinese
- output formal inspection-report tone
- do not use AI self-reference such as `我认为` or `根据我的判断`
- focus on concise, customer-facing delivery language

## Payload Merge Strategy

Round1 should add new appendix fields first:

- `xray_llm_inspection_summary`
- `xray_llm_exception_summary`
- `xray_llm_disposal_advice`

This keeps the LLM content clearly separated from the current rule-based fields.

Template integration options:

### Option A: safest round1

- keep existing rule-based summary fields
- add a new appendix section in the template for the three LLM blocks

### Option B: controlled replacement

- replace only the final summary paragraph field with the LLM inspection summary
- keep the other LLM sections in additional appendix blocks

Recommended round1 choice: Option A.

## Failure Behavior

LLM section generation must be non-blocking.

If the model call fails because of:

- timeout
- network error
- provider non-200
- invalid JSON
- missing fields

then:

- report generation still succeeds
- payload keeps rule-based content
- LLM section fields fall back to `-` or a stable default
- task status must not become failed because of LLM section generation

## Configuration

Recommended env vars:

- `XRAY_LLM_SECTION_ENABLED=false`
- `XRAY_LLM_SECTION_MODE=disabled`
- `XRAY_LLM_SECTION_BASE_URL=`
- `XRAY_LLM_SECTION_API_KEY=`
- `XRAY_LLM_SECTION_MODEL=`
- `XRAY_LLM_SECTION_TIMEOUT_SECONDS=30`
- `XRAY_LLM_SECTION_TEMPERATURE=0.2`

## Tests

Minimum round1 tests:

1. disabled mode
   - payload remains rule-based
   - LLM section fields stay empty/default

2. remote happy path
   - valid JSON populates the three LLM fields

3. invalid JSON
   - fallback path works

4. timeout / provider error
   - DOCX rendering still succeeds

5. fact immutability
   - versions, IPs, health results, and resource values remain unchanged

6. template compatibility
   - if new placeholders are added, DOCX still renders successfully

## Documentation

Update:

- `README.md`
- `docs/project_status.md`

Document clearly:

- LLM is optional
- LLM only generates summary-style sections
- LLM does not replace analyzer facts

## Verification

Local verification target:

1. run focused tests for the LLM section service and payload merge path
2. run one real x-ray task end-to-end
3. confirm:
   - `unified.json` stays unchanged
   - `report_payload.json` contains new LLM section fields
   - `report.docx` renders successfully
   - LLM sections read like formal inspection report text

## Acceptance Criteria

Round1 is complete when:

- x-ray reports still render with LLM disabled
- x-ray reports still render when LLM calls fail
- LLM successfully produces the three summary-style sections on happy path
- factual x-ray fields remain rule-based and unchanged
- the implementation establishes a reusable pattern for future product-specific
  summary generation without letting LLM replace the parser or fact payload
