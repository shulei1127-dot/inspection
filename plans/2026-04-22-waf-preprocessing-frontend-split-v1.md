# WAF preprocessing frontend split v1

## Goal

Split the current WAF browser page so `/waf` represents only the WAF full-log preprocessing step. Trend enhancement remains available through existing APIs, but the frontend should not automatically run it for now.

## Scope

- Rename `/waf` page copy from "WAF log preprocessing + trend enhancement" to "WAF log preprocessing".
- Remove the optional base DOCX upload from `/waf` because it belongs to later trend/report enhancement flow, not cleaning.
- Change the submit flow to call only `POST /api/waf/preprocessing`.
- Keep result downloads focused on preprocessing artifacts, especially `status-analysis`.
- Update `/console` and homepage wording so the WAF module is not presented as trend enhancement.
- Update focused frontend tests.
- Update `docs/project_status.md`.

## Out Of Scope

- Do not remove or change `POST /api/waf/trend-enhancements`.
- Do not change preprocessing backend behavior.
- Do not change WAF report audit behavior.
- Do not add a new frontend route for trend enhancement in this round.
- Do not add persistence/listing for WAF preprocessing history.

## Verification

- `pytest tests/test_waf_frontend.py tests/test_frontend_console.py`
- Optionally run the WAF preprocessing endpoint test if the page assertions touch API wording.
