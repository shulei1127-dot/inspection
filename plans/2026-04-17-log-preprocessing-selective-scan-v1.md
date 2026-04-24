# Log Preprocessing Selective Scan v1: No Full Source Copy

## Goal

Add a conservative selective-scan mode to the offline log preprocessing layer so
large SafeLine / WAF full-log directories can be analyzed without copying the
entire source tree into `workdir/prep_*/source_logs`.

The target is to reduce disk usage and improve real-sample runtime while keeping
the generated trend inputs at least as trustworthy as the current full-copy
mode.

This round is intentionally narrow:

- do **not** change `/api/tasks`
- do **not** change xray
- do **not** change `waf_audits`
- do **not** add endpoints
- do **not** introduce LLM judgement
- do **not** add complex time-series forecasting
- do **not** change trend assessment rules
- do **not** discard evidence silently

## Why This Round Exists

The current preprocessing round can already turn a SafeLine / WAF full-log
directory into:

```text
status_analysis_evidence.json
status_analysis_summary.json
状态分析报告.md
```

and the generated markdown can feed the existing trend-enhancement subchain:

```text
状态分析报告.md -> trend_input.json -> trend_assessment.json
```

However, the current service copies the full input directory into
`workdir/prep_*/source_logs` before scanning it. A real WAF sample compressed to
around tens of MB can expand to around GB-level source logs, which means each
preprocessing run can duplicate a very large amount of customer data.

This is expensive for:

- disk usage
- runtime
- repeated local validation
- future batch processing
- sensitive raw-log retention

Selective scan addresses that storage/runtime problem without changing the
current status/trend contracts.

## Core Principle

Selective scan should mean:

```text
read only the source files needed for extraction
persist only structured outputs and bounded evidence excerpts
do not copy the whole source directory by default
```

It must **not** mean:

```text
analyze less evidence without telling the user
hide skipped files
invent missing trends
weaken status or anomaly conclusions silently
```

## Scope

### In Scope

1. add a configurable no-full-copy mode for `run_log_preprocessing`
2. keep the current full-copy mode available for debugging
3. scan currently supported SafeLine / WAF sources in place
4. read large files with bounded strategies instead of loading/copying all raw
   content blindly
5. persist scan coverage metadata into `status_analysis_evidence.json`
6. surface coverage warnings in `status_analysis_summary.json` and
   `状态分析报告.md`
7. verify the handoff chain remains valid:
   - full-log directory
   - `状态分析报告.md`
   - `trend_input.json`
   - `trend_assessment.json`

### Out of Scope

- no direct archive streaming in this round
- no automatic archive extraction changes
- no new product family
- no new trend rule
- no new chart rule
- no broad log-cleaning DSL
- no database persistence
- no API exposure
- no raw-log redaction framework beyond bounded evidence excerpts

## Proposed Behavior

### Default Mode

Prefer making selective scan the preprocessing default:

```text
LOG_PREPROCESSING_COPY_SOURCE=false
```

In this mode:

- `workdir/prep_*` stores generated artifacts
- the original source directory is not copied
- evidence records retain source-relative paths and limited excerpts
- scan coverage is recorded

### Debug Mode

Keep a full-copy mode available:

```text
LOG_PREPROCESSING_COPY_SOURCE=true
```

In this mode, the service can keep the current behavior for local debugging,
fixture inspection, and reproducing parsing issues.

## Proposed Configuration

Add minimal settings, names can be adjusted during implementation:

- `LOG_PREPROCESSING_COPY_SOURCE`
  - default: `false`
  - when true, copy the full source directory into `workdir/prep_*/source_logs`
- `LOG_PREPROCESSING_LARGE_FILE_BYTES`
  - default suggestion: `50MB`
  - files above this threshold use bounded scanning
- `LOG_PREPROCESSING_MAX_EXCERPT_LINES`
  - default suggestion: `200`
  - maximum retained evidence lines per scan category or source file
- `LOG_PREPROCESSING_SCAN_WINDOW_DAYS`
  - default: `30`
  - keep aligned with current preprocessing and trend assumptions

Avoid adding too many knobs in v1. The first version should be easy to explain
and stable to operate.

## Scan Coverage Model

Extend the preprocessing evidence model minimally with scan coverage metadata.

Suggested shape:

```json
{
  "scan_coverage": {
    "mode": "selective",
    "copied_source": false,
    "coverage_level": "partial",
    "scanned_files": [
      {
        "path": "system/top.txt",
        "strategy": "full_read",
        "size_bytes": 1234,
        "evidence_categories": ["resource", "uptime"]
      }
    ],
    "skipped_files": [
      {
        "path": "safeline/logs/detector/snserver.log",
        "strategy": "skipped_or_limited",
        "size_bytes": 541000000,
        "reason": "large_file_not_in_v1_priority"
      }
    ],
    "warnings": []
  }
}
```

This does not need to be perfect in v1, but it must answer:

- which files were scanned
- which files were skipped or limited
- why a file was skipped or limited
- which evidence category a scanned file contributed to
- whether the scan is best described as `full`, `partial`, or `minimal`

Suggested `coverage_level` semantics:

- `full`: all v1-priority sources that exist were scanned and no major source
  category was skipped
- `partial`: core priority files were scanned, but at least one major or large
  non-priority source was skipped or limited
- `minimal`: only a small subset of priority sources was available or scanned,
  so trend consumers should treat the evidence as strongly incomplete

## Summary-Level Scan Limitations

`status_analysis_summary.json` should not require downstream consumers to read
the full evidence document just to understand scan constraints.

Add summary-level fields:

- `coverage_level`
- `scan_limitations`
- `major_skipped_sources`
- `coverage_warnings`

These fields should be short and delivery-friendly:

```json
{
  "coverage_level": "partial",
  "scan_limitations": [
    "Large non-priority files were not scanned in v1 selective mode."
  ],
  "major_skipped_sources": [
    "safeline/logs/detector/snserver.log"
  ],
  "coverage_warnings": [
    "Scan coverage is partial; trend conclusions remain conservative."
  ]
}
```

## Source Priority

Selective scan should preserve the current extraction priority before adding
new coverage.

### Resource Snapshot Sources

Always scan if present:

- `system/top.txt`
- `system/free.txt`
- `system/df.txt`
- `system/uptime.txt`
- `resources/resource_summary.txt`
- `metadata/collection_info.txt`
- root or directory-name collection-time hint

### Stability Sources

Scan these sources with timestamp filtering and bounded evidence retention:

- `system/current-boot.log`
- `system/dmesg.log`
- `system/last-boot.log`
- `container/*.log`
- `safeline/logs/minion/*.log`
- `safeline/logs/management/*.log`

### Large / High-Volume Sources

Treat these conservatively in v1:

- `safeline/logs/detector/snserver.log`
- `safeline/logs/ripley/stats/*`
- very large rotated access-like logs

Initial v1 default strategy:

- do not fully copy them
- do not fully persist them
- skip them by default and record them in `skipped_files`
- only scan them with bounded line-by-line reads if they are already part of
  the explicit v1 source priority
- do not implement tail scanning, mmap scanning, multi-pass indexing, or other
  advanced large-file modes in v1

Future rounds can add tail scanning, mmap/stream scanning, or product-specific
key pattern scanning for these files.

## Bounded Read Strategy

Avoid reading very large files into memory as one string.

Recommended v1 implementation:

1. small priority files:
   - normal `read_text`
2. medium log files:
   - stream line by line
   - keep only matched evidence excerpts
3. large files:
   - if explicitly supported, stream line by line with match limits
   - if not explicitly supported, skip and record coverage metadata

Do not add complex indexing in v1.

## Effect On Trend Prediction

The expected effect on trend prediction should be neutral or positive.

### No Loss Expected For Current Supported Signals

The current trend subchain needs cleaned evidence, not raw full logs. As long as
selective scan still extracts:

- CPU snapshots
- memory snapshots
- disk snapshots when a supported source exists
- uptime snapshots
- restart / panic / abnormal exit / unclean shutdown counters
- service/container/system findings

then `trend_input.json` and `trend_assessment.json` should remain compatible.

### Main Risk

The main risk is scan coverage becoming too narrow and missing an anomaly that
only exists in a large or unsupported source.

Mitigation:

- record skipped/limited files
- add warnings when major source categories are not scanned
- keep full-copy debug mode
- keep trend judgements conservative when data is incomplete

## Artifact Behavior

### Selective Mode Workdir

Expected `workdir/prep_*` layout:

```text
workdir/prep_*/
  status_analysis_evidence.json
  status_analysis_summary.json
  status_analysis.md
```

Optional small metadata files are acceptable, but there should be no full
`source_logs/` copy by default.

### Full-Copy Debug Mode Workdir

Expected layout remains compatible with current behavior:

```text
workdir/prep_*/
  source_logs/
  status_analysis_evidence.json
  status_analysis_summary.json
  status_analysis.md
```

## Testing Plan

Add focused tests for:

1. selective mode does not create a full `source_logs/` copy
2. full-copy debug mode still creates `source_logs/`
3. resource extraction still works from `system/top.txt`
4. collection time can still come from directory epoch suffix
5. scan coverage records scanned files
6. scan coverage records skipped or limited large files
7. generated markdown still feeds the existing trend subchain:
   - `状态分析报告.md -> trend_input.json -> trend_assessment.json`
8. full existing test suite still passes

If adding scan coverage fields to schemas, keep defaults backward-compatible so
existing fixtures and tests do not need noisy rewrites.

## Real-Sample Acceptance

Use the real SafeLine / WAF package:

```text
minion-command-collect-CT0101202309048DA0-chaitin_safeline-1765356785.tar.gz
```

Acceptance should record:

- source directory expanded size
- selective-mode `workdir/prep_*` size
- whether `source_logs/` was avoided
- extracted collection time
- extracted CPU
- extracted memory
- extracted uptime
- disk status
- number of scanned files
- number of skipped/limited files
- trend handoff result

Expected result:

- workdir size is much smaller than the expanded source directory
- CPU / memory / uptime remain extracted
- disk remains `unknown` unless a supported disk source exists
- trend handoff remains successful
- skipped large files are visible in evidence metadata

## Documentation Updates

Update:

- `README.md`
- `docs/project_status.md`

Mention:

- selective scan is now the default preprocessing mode
- full-copy mode exists for debugging
- scan coverage is recorded
- incomplete scan coverage leads to warnings, not silent assumptions

## Risks

- Scan coverage may initially be too conservative for very large product logs.
- Some anomaly-only evidence may live in skipped large files.
- A no-copy mode means users must retain the original source bundle if they want
  to manually inspect full raw logs later.
- If bounded scanning is implemented poorly, it could hide important repeated
  events by stopping after a small number of matches.

## Risk Controls

- Keep full-copy debug mode.
- Persist scan coverage metadata.
- Use conservative trend outputs when data is incomplete.
- Prefer source-priority additions over broad recursive scanning.
- Keep v1 large-file handling simple and explicit.

## Non-Goals

- no raw log archival policy redesign
- no customer-data retention productization
- no UI toggle
- no scheduled cleanup
- no end-to-end API integration
- no smarter forecasting
- no second product support

## Suggested Implementation Order

1. add settings for copy mode and large-file threshold
2. adjust `log_preprocessing_service` to support source-reference mode without
   full `copytree`
3. add scan coverage schema fields with backward-compatible defaults
4. refactor builder reads through small helper functions that record coverage
5. preserve existing extraction behavior for current priority files
6. add skipped/limited metadata for large unsupported files
7. update renderer to include a short parsing / coverage note when warnings
   exist
8. add focused tests
9. run the real WAF sample acceptance
10. update docs

## Completion Criteria

This round is complete when:

- preprocessing can run without copying the full source tree
- current supported resource and stability fields still extract correctly
- scan coverage metadata is present in evidence output
- skipped/limited large files are visible and explainable
- the generated markdown still feeds trend enhancement without manual edits
- compared with current full-copy mode, the real-sample
  `trend_assessment.json` does not obviously degrade; if any degradation occurs,
  the summary/evidence `coverage_warnings` must clearly explain which skipped or
  limited sources caused it
- focused tests pass
- full test suite passes
- real WAF package demonstrates significant workdir size reduction
