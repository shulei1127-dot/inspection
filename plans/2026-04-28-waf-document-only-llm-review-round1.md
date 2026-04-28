## Goal

Add a minimal WAF `document-only` LLM review mode so the platform can:

1. accept a WAF inspection DOCX without requiring a full-log preprocessing result
2. extract document-visible abnormal conditions
3. let the LLM generate:
   - `异常情况及处置操作`
   - `巡检总结`
4. keep the existing `log-grounded` audit flow intact

The focus of round1 is not full evidence-based auditing, but a safe
document-driven review mode with clear evidence-boundary wording.

## Background

The current WAF flow already supports:

1. upload full WAF archive
2. run preprocessing
3. generate structured evidence
4. upload report DOCX and reuse `preprocessing_id`
5. compare report claims against log evidence
6. generate audit opinion and augmented Word output

That flow is valuable when logs exist, but it is too strict for scenarios where
only the inspection DOCX is available.

The new round1 mode should support:

- document-only review
- no full-log dependency
- no fake `日志已核验` wording
- LLM-generated handling advice only when the report itself contains identifiable
  abnormal conditions

## Round1 Scope

Round1 only adds a new WAF review path:

- input: one WAF inspection DOCX
- output:
  - normalized document claims / extracted review input
  - LLM-generated `异常情况及处置操作`
  - LLM-generated `巡检总结`
  - optional Word appendix or review markdown output

Round1 should preserve the existing full `preprocessing_id` audit mode.

The system should support two WAF review modes side by side:

1. `log_grounded`
   - report + preprocessing evidence
   - existing strong audit path
2. `document_only`
   - report only
   - new LLM-assisted advice path

## Explicit Non-goals

- do not require full-log upload for document-only mode
- do not claim document-only results were log-verified
- do not let the LLM fabricate resource percentages, service states, or log facts
- do not merge both modes into one ambiguous output contract
- do not replace the current rule-based WAF audit result path
- do not expand round1 to x-ray changes

## Core Principle

### Full-log mode and document-only mode must remain semantically distinct

When logs exist:

- the system may say `经日志核验`
- the system may judge report/log consistency

When only the DOCX exists:

- the system must say `根据巡检文档内容`
- the system must not imply log-based confirmation
- the system may generate handling suggestions from the document’s stated
  abnormalities and grounded help-doc knowledge

## Proposed Architecture

### 1. Keep the current WAF audit chain unchanged

Existing modules remain authoritative for:

- `preprocessing_id` reuse
- log evidence extraction
- claim confirmation / conflict / insufficient judgement
- audit result persistence

### 2. Add a document-only review path

Suggested service:

- `app/services/waf_document_review_service.py`

Responsibilities:

- parse the uploaded DOCX into normalized document review input
- identify actionable abnormal topics from the report text
- assemble a safe LLM input
- return structured summary sections

### 3. Reuse existing Word/document parsing where possible

Prefer extending current WAF claim extraction logic instead of creating a second
completely separate DOCX parser.

The document-only path should still extract at least:

- CPU / memory / disk statements
- whether the report claims normal / stable / abnormal
- container or service abnormal descriptions when present
- manually written issue descriptions
- summary / conclusion paragraphs when available

### 4. Add a WAF-specific LLM section service

Suggested service:

- `app/services/waf_llm_review_section_service.py`

Responsibilities:

- build compact review input from normalized DOCX claims
- optionally merge matched help-doc snippets
- call the provider
- validate JSON output
- return narrow summary sections only

### 5. Keep provider abstraction narrow

Round1 provider mode:

- `disabled`
- `remote_api`

The remote mode should continue targeting an OpenAI-compatible
`/chat/completions` endpoint.

## Document-only Review Input Contract

The LLM should not receive the raw DOCX.

Round1 should build a compact structured input such as:

```json
{
  "review_mode": "document_only",
  "product_type": "waf",
  "host_context": {
    "hostname": "...",
    "ip": "..."
  },
  "resource_claims": [
    {
      "metric": "cpu",
      "reported_percent": 85.0,
      "report_judgement": "abnormal",
      "source_text": "CPU使用率达到85%"
    }
  ],
  "abnormal_topics": [
    {
      "topic": "memory_high",
      "title": "内存使用率偏高",
      "evidence": "文档显示内存使用率达到87%"
    },
    {
      "topic": "container_unhealthy",
      "title": "关键容器运行异常",
      "evidence": "文档描述某容器服务异常或不健康"
    }
  ],
  "matched_help_docs": [
    {
      "title": "WAF 内存高占用排查",
      "snippet": "优先通过 docker stats、free -h、容器日志核查..."
    }
  ]
}
```

## LLM Output Contract

Require strict JSON:

```json
{
  "exception_actions": [
    {
      "problem": "内存使用率达到87%",
      "evidence": "巡检文档显示当前内存使用率为87%。",
      "action": "建议通过 docker stats 查看各容器内存占用情况，并结合 free -h 核实主机内存整体使用状态。"
    }
  ],
  "inspection_summary": "根据巡检文档内容，当前系统..."
}
```

Validation rules:

- `exception_actions` may be empty when no actionable abnormality is detected
- `inspection_summary` required
- Chinese only
- no markdown tables
- no fabricated log-verification wording
- no unsupported commands outside grounded help-doc / safe generic operations

## Prompt Constraints

The WAF document-only prompt must explicitly require:

- you are not a log parser
- you are not allowed to claim log verification
- only use supplied facts and matched help-doc snippets
- if evidence is insufficient, say `需进一步核查`
- prefer conservative, operator-usable handling advice
- use formal Chinese inspection-report tone
- do not output AI self-reference
- do not invent percentages, container names, service states, or root causes

## Review-mode Wording Rules

### `document_only`

Preferred wording:

- `根据巡检文档内容`
- `文档显示`
- `建议进一步结合运行日志核查`

Forbidden wording:

- `经日志核验`
- `日志显示`
- `已确认与日志一致`

### `log_grounded`

Existing wording remains available:

- `经日志核验`
- `日志显示`
- `文档与日志一致/存在差异`

## Help-doc Grounding v1

Round1 should support a simple local file-based grounding layer.

Suggested directory:

- `docs/help_docs/waf/`

Suggested initial files:

- `resource_alerts.md`
- `container_abnormal.md`
- `service_failures.md`
- `document_only_review_guidance.md`

Round1 retrieval can stay simple:

- topic-based keyword matching
- first matching snippets
- no vector database
- no remote wiki integration yet

## API/UI Strategy

Round1 may choose either of these safe paths:

### Option A: extend current WAF audit API

Allow WAF review requests without `preprocessing_id` and branch into
`document_only` mode.

### Option B: add a dedicated endpoint

Suggested:

- `POST /api/waf-audits/document-only`

Round1 should choose the path with less ambiguity and lower regression risk.

Preferred bias:

- if the current endpoint becomes too overloaded semantically, add a dedicated
  document-only endpoint

## Storage and Outputs

Round1 should persist:

- normalized document claims / review input
- review mode marker
- LLM-generated summary sections

Suggested output files:

- `doc_review_input.json`
- `llm_document_only_review.json`
- `llm_document_only_review.md`

If Word augmentation is in scope for this round, it should append a clearly
labeled section such as:

- `文档异常情况及处置操作（未结合原始日志核验）`

## Tests

Round1 minimum coverage:

1. document-only request succeeds without `preprocessing_id`
2. resource abnormality in DOCX can produce `exception_actions`
3. no abnormality does not force fake issue rows
4. output wording in document-only mode does not claim log verification
5. invalid / empty LLM output safely falls back
6. existing `log_grounded` audit path remains unchanged

## Docs To Update

- `README.md`
- `docs/project_status.md`
- if needed, add a small WAF mode-comparison doc

## Acceptance Criteria

Round1 is complete when:

1. a WAF inspection DOCX can be reviewed without full-log preprocessing
2. the result clearly indicates document-only semantics
3. abnormal conditions in the DOCX can trigger LLM-generated handling advice
4. the generated wording remains conservative and evidence-bound
5. the existing log-grounded WAF audit flow still works unchanged

## Next Step After Round1

The most natural next step after round1 is:

- connect WAF help-doc grounding more deeply
- add richer abnormal-topic extraction
- optionally support Word appendix backfill for document-only mode
