# WAF Resource Time-Series 12h Bucketing

## Background

The preprocessing layer can now read explicit resource history files and render a `资源历史样本` table that the trend subchain can parse. The next small step is to make the output cadence stable so dense or uneven resource samples do not produce noisy charts.

## Goal

Normalize supported resource history inputs into one point per 12-hour bucket across the recent 30-day analysis window.

## Scope

In scope:

- Keep using explicit resource history sources only:
  - `resources/resource_history.csv`
  - `resources/resource_timeseries.csv`
  - `resources/resource_history.txt`
  - `system/resource_history.csv`
  - `system/resource_history.txt`
- Bucket parsed CPU / memory / disk values into 12-hour windows.
- Use the average of available values in each bucket.
- Keep missing metric values empty instead of filling or interpolating.
- Preserve the existing markdown handoff to `trend_input.json`.
- Add tests that prove dense samples become stable 12-hour points and still drive chart-eligible trend input.

## Out Of Scope

- No `/api/tasks` changes.
- No xray changes.
- No `waf_audits` changes.
- No LLM prediction.
- No complex time-series model.
- No interpolation or forecasted future numeric points.
- No broad scanning of ambiguous large raw logs.

## Bucketing Rule

V1 uses UTC calendar-aligned buckets:

- `00:00:00` to `11:59:59`
- `12:00:00` to `23:59:59`

Each bucket emits at most one point. If multiple samples exist in the same bucket, each metric is averaged independently from the available values.

## Completion Criteria

- `status_analysis_summary.json.resource_time_series` contains normalized 12-hour points.
- Generated `状态分析报告.md` continues to include the `资源历史样本` table.
- Existing trend subchain parses those points without manual edits.
- Focused preprocessing tests and full repository tests pass.
