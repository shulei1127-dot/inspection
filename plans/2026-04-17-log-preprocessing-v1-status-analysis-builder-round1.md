# Log Preprocessing v1 Round1: Full-Log Cleanup to `状态分析报告.md`

## Goal

Add a new, isolated preprocessing layer that converts one full log bundle (or one
extracted log directory) into a structured `状态分析报告.md` that can be consumed
by the existing trend-enhancement subchain.

Round1 is intentionally narrow:

- it does **not** change `/api/tasks`
- it does **not** change `xray`
- it does **not** change `waf_audits`
- it does **not** introduce new endpoints
- it does **not** add LLM-based judgement
- it does **not** add a complex time-series model

The focus is to establish a stable **preprocessing seam**:

`full logs -> cleaned status-analysis markdown -> existing trend chain`

## Why This Round Exists

The current trend-enhancement subchain already works when given a cleaned
`状态分析报告.md`, and it can now:

- extract resource snapshots and limited history
- extract uptime and stability evidence
- build `trend_input.json`
- build `trend_assessment.json`
- build `trend_summary.md`
- optionally append a trend appendix into a base docx report

What is still missing is the upstream step that turns a **full log bundle**
into the cleaned markdown input expected by that chain.

Round1 addresses that missing step without collapsing preprocessing, trend
assessment, and report augmentation into one module.

## Scope

### In Scope

1. define a dedicated preprocessing/service boundary for:
   - full log directory input
   - recent-window filtering
   - structured evidence extraction
   - fixed-layout markdown rendering
2. define the minimum schema and output shape for:
   - `status_analysis_evidence.json`
   - `status_analysis_summary.json`
   - `状态分析报告.md`
3. implement the Round1 plan only against one current real report family:
   - SafeLine / WAF style full logs
4. keep the output format aligned with the current trend-enhancement parser shape
5. keep the time window fixed to:
   - recent 30 days
6. keep “current snapshot” content even if it is not part of a multi-point series
7. document how this preprocessing layer connects to the current trend chain

### Out of Scope

- no new API endpoint
- no `/api/tasks` integration
- no xray-path changes
- no `waf_audits` changes
- no direct raw-log-to-Word rendering
- no multi-product abstraction pass
- no OCR
- no LLM summarization
- no complex forecasting
- no broad all-log-type support in one round

## Proposed Boundary

Round1 should introduce a new isolated layer before the existing
trend-enhancement chain:

```text
full log bundle / extracted directory
  -> preprocessing service
  -> status_analysis_evidence.json
  -> status_analysis_summary.json
  -> 状态分析报告.md
  -> existing trend_enhancement_service
  -> trend_input.json
  -> trend_assessment.json
  -> trend_summary.md
  -> optional augmented_report.docx
```

The preprocessing layer should be responsible only for:

- recent-window filtering
- evidence extraction
- normalized summary building
- rendering a stable markdown report

It should **not** be responsible for final trend judgement.

## Round1 Inputs and Outputs

### Input

Round1 should accept:

- one extracted full-log directory

Optional future input modes such as direct archive upload can stay outside this
round.

### Output

Round1 should produce at least:

1. `status_analysis_evidence.json`
2. `status_analysis_summary.json`
3. `状态分析报告.md`

The output layering should be:

- `evidence.json`: source-near evidence and extracted facts
- `summary.json`: cleaned, normalized, report-ready structured summary
- markdown: deterministic human-readable rendering of the summary

The markdown output should be intentionally shaped so the current
`trend_input_builder` can consume it with minimal or no additional adaptation.

## Proposed Module Layout

Round1 should keep changes inside the current offline/service path and avoid
touching HTTP surfaces.

Suggested files:

- `app/schemas/status_analysis.py`
- `app/services/log_preprocessing_service.py`
- `app/services/status_analysis_builder.py`
- `app/services/status_analysis_renderer.py`
- optional script:
  - `scripts/run_log_preprocessing.py`

### Responsibility Split

#### `log_preprocessing_service.py`

- validate input path
- create run/work/output directories
- orchestrate builder + renderer
- persist intermediate artifacts
- resolve the recent-window reference time with explicit precedence:
  1. collection time extracted from logs/metadata
  2. caller-provided `reference_time`
  3. current system time

#### `status_analysis_builder.py`

- scan relevant log sources
- filter evidence to recent 30 days where timestamps exist
- preserve current snapshot information
- build:
  - one source-near evidence model
  - one cleaned structured summary model

#### `status_analysis_renderer.py`

- render one fixed-structure markdown report
- keep output wording deterministic and parser-friendly

#### `status_analysis.py`

- define normalized intermediate models for:
  - metadata
  - resource snapshots
  - uptime data
  - stability events
  - 30-day stability counters:
    - `restart_count_30d`
    - `panic_count_30d`
    - `abnormal_exit_count_30d`
    - `unclean_shutdown_count_30d`
  - service/container anomalies
  - historical associations outside the 30-day window

## Round1 Extraction Targets

Round1 should stay focused on the minimum data that the existing trend chain can
already benefit from.

### Resource State

- CPU
- memory
- disk
- uptime

### Stability Evidence

- restart
- panic
- abnormal exit
- unclean shutdown

### Key Abnormal Findings

- key service failures
- key container failures
- explicit system/runtime anomalies with clear timestamps

## Resource Snapshot Source Priority

Round1 should not guess resource extraction opportunistically at implementation
time. The source priority should be explicit and stable.

### CPU

1. `system/top.txt`
2. `resources/resource_summary.txt`
3. `logs/*` or other sources are out of scope for Round1

### Memory

1. `system/free.txt`
2. `resources/resource_summary.txt`
3. `system/top.txt` only as a narrow fallback if a low-ambiguity memory summary
   line exists

### Disk

1. `system/df.txt`
2. `resources/resource_summary.txt`
3. explicit application-disk usage snippets from known logs only if they carry a
   low-ambiguity single usage value

### Uptime

1. `system/uptime.txt`
2. `system/top.txt` only as a narrow fallback if the `top - ... up ...` header
   contains a low-ambiguity uptime value
3. explicit collection metadata / boot metadata
4. no synthetic uptime backfill beyond direct derivation from those sources

## Time-Window Rules

Round1 should define and enforce these rules explicitly:

1. resolve the reference time in this order:
   - extracted collection time
   - collection epoch suffix in known full-log directory names such as
     `minion-command-collect-...-1765356785`
   - caller-provided `reference_time`
   - current system time
2. if a log line or record has a parseable timestamp:
   - keep it only if it falls within the most recent 30 days
3. if a record is a current snapshot and has no historical series semantics:
   - keep it as current-state evidence
4. if a record is older than 30 days but materially explains current stability:
   - allow it only under a separate “历史关联” style section
   - do not mix it into “30 天内关键风险”
5. do not invent missing time points

## Markdown Shape

Round1 should render a stable markdown structure aligned with the current
trend-enhancement input expectations.

Recommended structure:

- title and metadata block
- `## 1. 系统资源状态`
  - CPU
  - memory
  - disk
  - uptime
- `## 2. 关键风险发现`
  - panic / abnormal exit
  - unclean shutdown / restart
  - service anomalies
  - container anomalies
- `## 3. 系统重启时间线与稳定性分析`
- `## 4. 状态摘要与风险线索`

The exact prose can remain conservative, but the headings and table shapes should
remain machine-friendly and stable.

## Product Focus for Round1

Round1 should target one current, high-value family only:

- SafeLine / WAF full logs

This is enough to prove the preprocessing seam before generalizing.

## Validation Plan

Round1 validation should include:

1. focused unit tests for:
   - recent-30-day filtering
   - snapshot preservation
   - stability event extraction
   - historical-association separation
2. fixture-based regression for:
   - multi-point resource sample
   - single-snapshot sample
   - low-risk stable sample
   - noisy-text sample
   - one real SafeLine/WAF full-log sample
3. end-to-end offline verification:
   - full-log directory
   - generated `状态分析报告.md`
   - handoff into existing trend-enhancement chain
   - confirm this chain works under one real sample without manually rewriting markdown:
     - `full-log directory -> 状态分析报告.md -> trend_input.json -> trend_assessment.json`

## Acceptance Criteria

Round1 is complete when:

- one full-log directory can produce a stable `状态分析报告.md`
- the same run also produces:
  - `status_analysis_evidence.json`
  - `status_analysis_summary.json`
- that markdown can be consumed by the existing trend-enhancement service
- no `/api/tasks`, `xray`, or `waf_audits` path is changed
- the module remains offline-first and service/script-based
- the generated markdown is structured enough that trend extraction no longer
  requires manual rewriting for the tested report family

## Risks and Guardrails

### Risks

- overreaching into a universal log parser too early
- mixing historical associations into recent-window findings
- letting preprocessing judgement bleed into trend judgement
- making markdown too free-form for downstream parsing

### Guardrails

- keep Round1 single-product and recent-window focused
- keep builder output structured
- keep renderer deterministic
- keep trend judgement in the existing trend subchain

## Suggested Next Step After Round1

If Round1 lands cleanly, the next likely step is:

- Round2: extend the preprocessing layer with a second real SafeLine/WAF full-log
  sample and tighten evidence extraction where the first real sample still needs
  manual cleanup
