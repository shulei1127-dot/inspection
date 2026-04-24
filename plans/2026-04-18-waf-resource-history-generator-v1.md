# WAF resource_history.csv generator v1

## Goal

Stabilize the SafeLine / WAF preprocessing layer so each preprocessing run materializes a canonical
`resources/resource_history.csv` artifact that can feed the existing status-analysis and trend-enhancement
subchains.

## Scope

- Add an offline-first resource-history generator under `app/services/`.
- Wire the generator into `run_log_preprocessing()` before status-analysis markdown rendering.
- Keep the generated CSV under `workdir/prep_*/resources/resource_history.csv`.
- Prefer explicit low-ambiguity resource history sources when present.
- Normalize explicit history into 12-hour average points.
- When no explicit history exists, generate at most one current snapshot point from low-ambiguity CPU / memory / disk sources.
- Keep no-data behavior explicit by writing a header-only CSV instead of inventing points.
- Keep `/api/tasks`, xray, `waf_audits`, parser routing, and report rendering untouched.

## Non-goals

- No interpolation.
- No synthetic future trend points.
- No parsing of ambiguous app-internal counters as system resource history.
- No API endpoint.
- No changes to Mermaid rendering or DOCX generation.

## Source Priority v1

Explicit history sources:

- `resources/resource_history.csv`
- `resources/resource_timeseries.csv`
- `resources/resource_history.txt`
- `system/resource_history.csv`
- `system/resource_history.txt`

Current snapshot fallback:

- CPU: `system/top.txt`, then `resources/resource_summary.txt`
- memory: `system/free.txt`, then `resources/resource_summary.txt`, then `system/top.txt`
- disk: `system/df.txt`, `system/disk.txt`, `system/filesystem.txt`, `system/filesystems.txt`, then resource summary fallbacks

Reference time precedence:

- collection metadata
- directory epoch suffix such as `minion-command-collect-...-1765356785`
- caller-provided `reference_time`
- current system time

## Implementation Plan

1. Add `app/services/resource_history_builder.py`.
2. Materialize `workdir/prep_*/resources/resource_history.csv` for every preprocessing run.
3. Extend `LogPreprocessingArtifacts` with `resource_history_csv_path`.
4. Let status-analysis read the generated canonical CSV first, then fall back to existing source-priority files.
5. Add focused tests for:
   - explicit history normalization into 12-hour points
   - current-snapshot fallback producing one row
   - header-only no-data behavior
   - generated CSV handoff into existing trend chain
6. Update README and `docs/project_status.md`.

## Acceptance Criteria

- `run_log_preprocessing()` always returns a `resource_history_csv_path`.
- The generated CSV always exists and uses header `timestamp,cpu,memory,disk`.
- Explicit resource history with dense rows becomes 12-hour averaged points.
- Snapshot-only logs produce at most one point, never a fabricated series.
- No-source logs keep an empty CSV with header only and trend output stays conservative.
- Existing tests remain green.
