# WAF Troubleshooting

## Which mode should I use?

Use:

- preprocessing + audit when logs are available
- document-only review when only the report DOCX is available

If the user wants strong evidence binding, prefer the log-grounded path.

## Wording feels too strong

Check whether the run was:

- log-grounded
- document-only

Document-only outputs should say things like:

- `根据巡检文档内容`
- `需进一步核查`

They must not claim:

- `经日志核验`

## Missing preprocessing result

If `preprocessing_id` is missing:

1. run `/waf` or `POST /api/waf/preprocessing`
2. capture the returned `preprocessing_id`
3. rerun the audit

## LLM did not take effect

Check:

- `WAF_LLM_REVIEW_ENABLED=true`
- base URL / key / model vars are present
- the platform was restarted after `.env` changed

Remember:

- WAF base review flows should still work without LLM
