# Xray Troubleshooting

## New xray report is sparse

Check in this order:

1. extracted task input under `workdir/{task_id}/...`
2. `workdir/{task_id}/unified.json`
3. `workdir/{task_id}/report_payload.json`

If the source files are present but `unified.json` is sparse, the analyzer may be stale or the collector shape may not be recognized as expected.

## Old task looked richer than the new one

This often means:

- the analyzer process is older than the current repository code
- the collector bundle layout changed
- the new bundle missed required files

## Task is `completed`

Meaning:

- analyzer and payload succeeded
- Word rendering did not finish

Check:

- `REPORT_RENDERING_ENABLED=true`
- Carbone health
- `POST /api/tasks/{task_id}/render-report`

## xray LLM sections did not appear

Check:

- `XRAY_LLM_SECTION_ENABLED=true`
- base URL / key / model vars are present
- the platform was restarted after `.env` changed

Remember:

- missing xray LLM text does not mean the base xray report chain failed
