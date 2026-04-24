## Goal

Optimize the x-ray report template and mapping layer for a first report-quality
pass using only data that is already present in the current `unified.json` and
`report_payload.json` flow.

This round focuses on making the generated x-ray DOCX feel more like a formal
inspection report without expanding parser scope, changing product naming, or
trying to solve missing-field presentation globally.

## Scope

This round will only address these four goals:

1. Split "manual inspection items" from "log-derived automatic items"
2. Strengthen exception summary and risk ordering
3. Upgrade issue output into a "problem - evidence - recommendation" structure
4. Improve the homepage/cover summary for management-style reading

## Expected Files To Modify

- `templates/xray_inspection_report.docx`
- `app/services/report_payload_mapper.py`
- `tests/test_report_payload_mapper.py`
- `tests/test_report_rendering_service.py` or another focused render-level test if needed
- `docs/project_status.md`

Potentially touched only if the implementation needs them:

- `scripts/build_xray_template_v1.py`
- `tests/test_report_template_selector.py`

## Structure Adjustments

### 1. Health Check / Inspection Structure

- Reorganize the x-ray report health-check or inspection section into two clearly
  separated groups:
  - log-derived automatic checks
  - manual verification items
- Keep currently log-derived service, container, health, and resource findings in
  the automatic group
- Move items that cannot be concluded from current logs into a manual-verification
  group so the report no longer reads like "many items are unfinished"

### 2. Cover / Executive Summary

- Strengthen the first page with a concise management-facing summary
- Make the overall state answer three questions immediately:
  - current system state
  - highest-priority issue
  - key runtime overview
- Surface the most important current anomaly before generic counts

### 3. Exception Summary / Risk Ordering

- Add a stronger x-ray-specific abnormal summary section or improve the existing
  conclusion block
- Sort the current issues by priority so the highest-impact item appears first
- Ensure resource/runtime concerns such as failed health checks, failed services,
  non-running containers, or restarting containers are elevated in wording and
  ordering

### 4. Issue Presentation

- Upgrade current issue rendering into a three-part structure:
  - problem description
  - supporting evidence
  - recommendation
- Evidence must be derived only from existing payload fields such as:
  - issue description
  - service/container status notes
  - summary counters
  - xray appendix metadata already produced today

## Implementation Notes

- Keep all naming as `洞鉴` / `x-ray` in the current repository style
- Do not expand parser output or add new analyzer-side extraction
- Do not introduce global contract churn if the x-ray appendix can carry the
  required wording cleanly
- Prefer mapping-layer composition and template restructuring over backend flow
  refactors
- Keep `unknown` and non-xray report behavior untouched

## Risks

1. The current x-ray template may constrain how much structural separation can be
   achieved without larger DOCX surgery.
2. If too much logic is pushed into the template, readability may improve only
   partially; if too much logic is pushed into mapping, payload wording may become
   harder to maintain.
3. Because parser scope is frozen in this round, some management-summary wording
   must stay conservative and cannot imply observations that current logs do not
   actually prove.
4. Rendered DOCX quality can regress subtly even when JSON tests pass, so at
   least one render-level verification is needed.

## Acceptance

1. The generated x-ray DOCX clearly separates:
   - log-derived automatic items
   - manual verification items
2. The first page no longer relies only on counts such as "问题 1 项" and instead
   highlights the most important current issue and the key runtime state.
3. Each rendered issue entry is presented as:
   - problem
   - evidence
   - recommendation
4. Existing x-ray generation still runs end-to-end:
   - upload archive
   - generate `unified.json`
   - generate `report_payload.json`
   - render x-ray DOCX
5. Focused tests cover the new x-ray mapping behavior and at least one render-side
   assertion for the updated report wording or structure.
