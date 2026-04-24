## Goal

Lift `services[]` for `minion_report.gz` from `0` to a minimal but explainable
inventory by reusing low-ambiguity runtime evidence already present in the
bundle.

## Scope

- Extend the analyzer-side xray/minion-report adapter
- Build a minimal service inventory from:
  - `logs/minion.log`
  - `logs/*/supervisord.log`
- Normalize those entries into canonical `system/systemctl_status`
- Keep the platform main flow unchanged
- Revalidate the real `minion_report.gz` remote path

## Rules

- Prefer explicit running evidence over guessed service names
- Keep inventory narrow and product-relevant
- Do not invent enabled/version fields unless the source is explicit
- Preserve existing xray appendices and report compatibility

## Validation

- Analyzer tests for minion-report service inventory
- Full local test suite
- Real upload in remote analyzer mode, compare `service_count` before/after
