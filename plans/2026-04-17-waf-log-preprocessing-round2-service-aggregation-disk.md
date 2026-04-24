# WAF Log Preprocessing Round2: Service Finding Aggregation + Disk Source Adaptation

## Goal

Improve the content quality of the SafeLine / WAF log preprocessing output after
selective scan is in place.

Round2 should make the generated `状态分析报告.md` more delivery-friendly by:

1. aggregating repeated service error lines into lightweight event-chain style
   findings
2. adding the smallest safe disk-source adaptation available from current WAF
   full-log inputs

This round should not change the platform main flow.

## Scope

### In Scope

- keep the existing offline preprocessing entrypoint
- preserve selective scan behavior and scan coverage metadata
- aggregate same-component / same-time-window service findings
- keep source references and evidence excerpts in the aggregate summary
- add one or more low-ambiguity disk source fallbacks if present in current
  SafeLine / WAF logs
- verify the generated markdown still feeds:
  - `trend_input.json`
  - `trend_assessment.json`

### Out of Scope

- no `/api/tasks` changes
- no xray changes
- no `waf_audits` changes
- no new endpoint
- no LLM judgement
- no complex event-correlation engine
- no broad product framework
- no large-file tail / mmap scan expansion
- no direct Word rendering changes

## Current Problem

The current real WAF sample validates the preprocessing chain, but the report
content still has two clear gaps:

1. service findings are too raw
   - repeated `mgt-es` lines from the same minute are displayed as separate
     findings
   - this is useful evidence, but not a good report narrative
2. disk is still `unknown`
   - CPU / memory / uptime are extracted from `system/top.txt`
   - disk only supports `system/df.txt` and `resources/resource_summary.txt`
   - if current WAF full logs carry another low-ambiguity disk source, v2 should
     map it into the existing disk snapshot field

## Service Aggregation Design

Use a lightweight grouping strategy:

- group by finding category
- group by component
- group by a short time bucket, for example 5 minutes
- group by simple reason family:
  - query execution failure
  - unhealthy
  - generic error
  - generic failed

The aggregate finding should retain:

- first timestamp
- component
- severity, using the highest severity in the group
- source reference, preferably the first source
- count of merged raw lines
- a short summary in Chinese
- representative evidence fragments

Example target wording:

```text
2025-12-08 03:22 ~ 03:23，mgt-es 出现 Elasticsearch 查询执行失败事件链，
合并 10 条相关日志，代表证据：QueryPhaseExecutionException / Failed to execute main query。
```

Keep this intentionally small. Do not build a full incident-correlation engine.

## Disk Source Adaptation Design

Keep disk extraction strict and low ambiguity.

Current priority remains:

1. `system/df.txt`
2. `resources/resource_summary.txt`

Round2 may add only clearly parseable fallback sources found in current WAF
packages, for example:

- a resource summary file with an explicit disk percent
- a storage / filesystem command output file with `Use%`
- a known SafeLine summary file carrying one clear root-disk usage value

Do not infer disk pressure from:

- Docker `BLOCK I/O`
- Elasticsearch errors
- file sizes alone
- vague `disk` mentions in arbitrary logs

If no safe source exists, keep disk `unknown` and make that explicit in the
validation result.

## Testing Plan

Add focused tests for:

1. repeated `mgt-es` / query-failure lines aggregate into one service finding
2. aggregate summary contains merged count and representative evidence
3. unrelated service findings do not collapse incorrectly
4. disk fallback extracts a value only from a low-ambiguity source
5. disk remains `unknown` when no supported disk source exists
6. generated markdown still feeds the existing trend chain

## Real-Sample Acceptance

Use the existing real WAF sample:

```text
minion-command-collect-CT0101202309048DA0-chaitin_safeline-1765356785.tar.gz
```

Record:

- service finding count before / after aggregation
- whether the `mgt-es` repeated query failure becomes one event-chain finding
- whether disk is extracted or remains explicitly `unknown`
- whether trend assessment changes or remains conservative
- whether selective scan workdir remains small and no `source_logs/` copy is
  created

## Completion Criteria

This round is complete when:

- service findings are no longer dominated by repeated same-minute raw lines
- generated markdown reads more like an event-chain summary
- disk extraction is improved if and only if a safe current source exists
- no unsupported disk inference is introduced
- selective scan coverage remains intact
- focused tests pass
- full test suite passes

