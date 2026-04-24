## Goal

Use the user-provided xray inspection DOCX as the xray report template base, keep missing fields blank, and render current log-derived data into that template without changing the main platform flow.

## Scope

1. Add an xray-specific report template file under `templates/`
2. Route `product_type=xray` to that template
3. Expose a minimal set of xray-friendly payload fields via the existing report payload appendix
4. Replace key static sample text in the provided template with Carbone markers
5. Replace body image slots with log-driven text placeholders where practical
6. Keep `unknown` and the old default template path unchanged

## Out of Scope

1. Deep xray parser expansion
2. New collector fields just for template completeness
3. Multi-template asset expansion beyond xray
4. Full redesign of the report payload contract

## Notes

- Prefer blank (`-`) or conservative fallback values when the current logs do not provide a field
- Reuse existing `report_payload.json` structure and `appendix` for xray-specific placeholders
- Preserve current Carbone render chain
