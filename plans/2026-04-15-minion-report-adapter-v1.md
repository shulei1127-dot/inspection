## Goal

Add `minion_report.gz` adapter v1 so the analyzer can recognize the built-in
`./minion collect` output, extract the highest-value fields from `info`,
`health`, `docker`, and `resource` sections, and feed them into the existing
`unified.json -> report_payload.json -> report.docx` chain.

## Scope

- Detect `minion_report.gz` extracted directory structure in the xray adapter
- Reuse the current xray product type and report chain
- Extract minimal stable fields from:
  - `info`
  - `config/mgmt_config.yml`
  - `config/engine_config.yml`
- Materialize canonical inputs where possible:
  - `system/system_info`
  - `containers/docker_ps`
- Preserve richer xray-specific values in `unified_json.metadata`
- Surface metadata into xray report appendix fields
- Add focused analyzer and payload tests
- Validate with the real `/Users/shulei/Downloads/minion_report.gz`

## Non-goals

- No platform main-flow refactor
- No archive upload mode in analyzer
- No second product support
- No broad service inventory expansion from minion report
- No AI analysis or extra diagnosis rules

## Validation

- Analyzer tests for `minion_report.gz` happy path
- Root payload tests for xray appendix field mapping
- Real local integration:
  - start analyzer
  - start platform in remote mode
  - upload `/Users/shulei/Downloads/minion_report.gz`
  - verify `unified.json`, `report_payload.json`, and optional `report.docx`
