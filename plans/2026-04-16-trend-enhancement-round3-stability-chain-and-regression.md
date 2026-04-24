# Trend Enhancement Round3: Stability Event Split, Failure-Chain Grouping, and Real-Sample Regression

## Goal

Strengthen the existing offline-first trend enhancement subchain without changing
`/api/tasks`, `xray`, `waf_audits`, API surface, or report mainline orchestration.

Round3 stays within the current service/script-only boundary and improves:

1. stability event granularity
2. lightweight failure-chain aggregation
3. second-batch real-sample regression coverage

## Scope

### In Scope

- split stability evidence into at least:
  - `restart_count`
  - `panic_count`
  - `abnormal_exit_count`
  - `unclean_shutdown_count`
- keep raw event evidence, but stop treating all stability signals as one flat count
- aggregate nearby events into lightweight fault-chain summaries to reduce repeated,
  noisy output
- reflect the richer stability structure consistently in:
  - `trend_input.json`
  - `trend_assessment.json`
  - `trend_summary.md`
  - optional `augmented_report.docx`
- add second-batch fixtures covering:
  - multi-point resource samples
  - low-risk stability samples
  - disk-judgeable samples
  - text-noise samples

### Out of Scope

- no new endpoint
- no `/api/tasks` changes
- no `xray` changes
- no `waf_audits` changes
- no LLM-based trend judgement
- no complex time-series model
- no report full rewrite

## Design Direction

### 1. Stability Event Split

Keep the existing event extraction pipeline, but classify event evidence into
explicit stability counters instead of one merged event pool.

Round3 should:

- retain raw `restart_events`
- add event-type-aware counters to the normalized input/assessment shape
- keep conservative parsing rules and avoid promoting predictive wording into
  historical incidents

### 2. Fault-Chain Aggregation

Build a small, explainable aggregation layer over stability events:

- same subject / component
- nearby timestamps or same report window
- same risk-chain family

Output should be a small number of grouped failure-chain summaries rather than a
long flat hit list.

### 3. Real-Sample Regression

Expand fixtures and tests so the current rule set is exercised across:

- `stable`
- `pressure_high`
- `deteriorating`
- `unknown`
- chart-generation edge conditions
- summary / appendix readability

## Implementation Notes

- prefer extending current schemas rather than introducing a parallel contract
- keep chart generation boundary unchanged: fewer than 2 points means no chart
- keep output wording conservative, especially for weak evidence
- preserve compatibility for existing round1 / round2 fixtures where possible,
  only updating expectations that intentionally become more specific

## Validation

- focused pytest for trend input / forecast / summary / augmenter / service
- full repository pytest regression
- confirm no endpoint or xray path changed
