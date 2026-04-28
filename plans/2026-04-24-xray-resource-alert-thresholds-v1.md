## Goal

Fix xray report payload resource alert handling so CPU, memory, and disk threshold breaches reliably surface as xray alerts in the generated report.

## Scope

- review the current xray resource observation logic in `app/services/report_payload_mapper.py`
- align alert thresholds with the latest business rule:
  - CPU >= 80%
  - memory >= 85%
  - disk >= 85%
- make high resource pressure visible in xray issue ordering so it is less likely to disappear behind lower-value observations
- add focused payload-mapper tests
- update `docs/project_status.md`

## Non-goals

- no parser changes
- no template structure refactor
- no frontend changes
- no analyzer API changes

## Verification

- run `pytest tests/test_report_payload_mapper.py`
- confirm the target xray task data shape would now surface disk pressure as an xray alert
