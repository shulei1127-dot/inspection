# Trend Enhancement Round4: WAF Status Report Shape Adaptation

## Goal

Adapt the existing offline-first trend enhancement subchain to better consume the
current real SafeLine / WAF status-analysis markdown shape without changing:

- `/api/tasks`
- `xray`
- `waf_audits`
- API surface
- LLM usage
- the current weak-prediction boundary

Round4 is a narrow parser-compatibility pass aimed at one real report family that
already proved valuable in local acceptance.

## Scope

### In Scope

1. support resource snapshot tables shaped like:
   - `指标 | 采集快照值 | 备注`
2. support uptime extraction from dedicated uptime/runtime subsections that use
   a small key-value table instead of top-level metadata
3. tighten stability-event noise filtering for the real WAF report family
4. add/extend fixtures and regression tests for this report shape
5. validate the real local sample again after parser changes

### Out of Scope

- no new endpoint
- no `/api/tasks` change
- no `xray` change
- no `waf_audits` change
- no complex time-series model
- no LLM-based trend judgement
- no full report rewrite

## Intended Improvements

### 1. Resource Snapshot Adaptation

The current builder already handles:

- multi-point history tables
- simple snapshot tables like `指标 | 数值 | 状态`

Round4 should additionally recognize the current WAF shape:

- `指标 | 采集快照值 | 备注`

The parser should extract at least:

- CPU snapshot from `us + sy`
- memory percentage from explicit percentage text
- disk usage from small metric tables inside disk sections when a low-ambiguity
  usage row exists

### 2. Uptime Section Adaptation

Round4 should extract uptime from section-local tables such as:

- `当前 uptime`
- `当前启动时间`
- `上一启动时间`

Only low-ambiguity values should be promoted.

### 3. Stability Noise Tightening

The real sample currently still promotes some explanatory prose into events.
Round4 should prevent false events from lines such as:

- effect / impact explanation
- recommendation bullets
- explicit negative statements like `无 OOM / panic`
- numbered recommendation headings becoming fake event subjects

The stability chain should remain conservative but cleaner.

## Validation

- focused trend-chain pytest
- full repo pytest
- one real local markdown rerun against `状态分析报告.md`
- compare before/after for:
  - CPU / memory / disk extraction
  - uptime extraction
  - stability fault-chain readability
