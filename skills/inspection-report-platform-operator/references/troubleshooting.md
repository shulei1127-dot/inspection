# Troubleshooting

## Analyzer looks stale

Symptom:

- xray logs clearly contain versions / health / resource files
- `report_payload.json` still shows many `-` placeholders

Check:

1. Confirm `ANALYZER_MODE=remote`
2. Confirm `ANALYZER_BASE_URL` points at the expected local analyzer
3. Restart the analyzer if an older process is still bound to the port

Useful checks:

- `curl http://127.0.0.1:8090/health`
- inspect `workdir/{task_id}/unified.json`

## Carbone render failed

Symptom:

- task status becomes `render_failed`
- error mentions `carbone_status_failed` or `render_request_failed`

Check:

1. Verify `CARBONE_BASE_URL`
2. Verify `curl ${CARBONE_BASE_URL}/status`
3. Make sure the configured port is not occupied by the wrong process

Useful check:

- `scripts/verify_local_stack.sh`

## Task is `completed` not `rendered`

Meaning:

- parsing and payload generation succeeded
- DOCX rendering did not happen or was disabled

Check:

1. `REPORT_RENDERING_ENABLED=true`
2. Carbone is healthy
3. the task can be retried through `POST /api/tasks/{task_id}/render-report`

## DOCX has many empty fields

Usually one of these is true:

1. the collector script did not gather the needed inputs
2. analyzer recognized the bundle as a weaker collector type
3. analyzer process is stale
4. the template expects fields that the current logs still do not provide

Debug in this order:

1. inspect extracted source files under `workdir/{task_id}/...`
2. inspect `workdir/{task_id}/unified.json`
3. inspect `workdir/{task_id}/report_payload.json`
4. compare with an older known-good task if available

## LLM did not take effect

Check:

1. the matching `*_ENABLED=true` flag is set in `.env`
2. required base URL / key / model vars are present
3. the platform was restarted after changing `.env`

Remember:

- no LLM config should still leave the base report flow usable
- LLM is an enhancement layer, not a prerequisite for report generation
