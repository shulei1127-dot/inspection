# WAF Log Preprocessing Round3: Resource Time-Series Extraction

## Background

The WAF log preprocessing chain can now generate:

- `status_analysis_evidence.json`
- `status_analysis_summary.json`
- `status_analysis.md`
- downstream `trend_input.json` and `trend_assessment.json`

Round1/round2 already cover current resource snapshots, stability event split, selective scan coverage, service finding aggregation, and disk fallback. The current gap is that resource trend charts still rely on the cleaned markdown containing at least two low-ambiguity time points. Most current inputs only expose one snapshot.

## Goal

Add a minimal, conservative resource multi-timepoint extraction path so that when a WAF full-log directory contains an explicit resource history source, preprocessing can emit a table that the existing trend enhancement subchain can parse without manual markdown edits.

## Scope

In scope:

- Add structured resource time-series records to `status_analysis_evidence.json` and `status_analysis_summary.json`.
- Support explicit low-ambiguity resource history files first, such as:
  - `resources/resource_history.csv`
  - `resources/resource_timeseries.csv`
  - `resources/resource_history.txt`
  - `system/resource_history.csv`
  - `system/resource_history.txt`
- Extract timestamp, CPU percent, memory percent, and disk percent when present.
- Render a markdown table with `时间 / CPU / 内存 / 磁盘` columns so the existing trend input builder can parse it.
- Keep missing metrics empty rather than inventing values.
- Add tests proving the generated markdown can flow into `trend_input.json` and `trend_assessment.json`.
- Update project status and README minimally.

## Out Of Scope

- No `/api/tasks` changes.
- No xray chain changes.
- No `waf_audits` changes.
- No new endpoint.
- No LLM trend judgment.
- No complex time-series model.
- No broad scan of large raw logs.
- No use of ambiguous app-internal metrics, such as Ripley mempool stats, as system memory/CPU.

## Source Priority

V1 only reads explicit resource-history style files. Supported columns can use English or Chinese labels:

- timestamp: `timestamp`, `time`, `时间`, `采集时间`
- CPU: `cpu`, `CPU使用率`
- memory: `memory`, `mem`, `内存`
- disk: `disk`, `磁盘`, `root`

Values may be plain numbers or percentages such as `81.5%`.

## Completion Criteria

- Preprocessing summary/evidence include resource time-series records when a supported source exists.
- `status_analysis.md` includes a resource history table.
- Existing trend subchain can parse at least two resource samples from that markdown.
- Existing tests continue to pass.
- If a real full-log sample lacks explicit resource history, the chain remains conservative and explains missing trend data through existing trend warnings instead of fabricating points.
