# WAF audit appendix DOCX v1

## Goal

After a WAF audit task finishes, generate a new Word document from the uploaded manual inspection report by appending a "日志核验意见 / 审核附录" section. The v1 output should not rewrite the original report body. It only appends audit conclusions and review details at the end.

## Scope

- Reuse the existing DOCX augmentation utilities where practical.
- Add WAF audit appendix rendering from `AuditResultV1`.
- Generate `outputs/{task_id}/audit_augmented_report.docx` for successful WAF audit tasks.
- Return the generated DOCX path in WAF audit create/detail responses.
- Add `GET /api/waf-audits/{task_id}/augmented-report` for downloading the generated Word report.
- Add a download link on `/waf-audits/ui`.
- Add focused tests for endpoint generation, download, and frontend link visibility.
- Update `README.md` and `docs/project_status.md`.

## Appendix Content

The v1 appendix should include:

- 总体审核结论
- 核验统计
- 已证实 / 部分证实项
- 冲突 / 需修订项
- 证据不足项
- 仍需人工判断项
- 建议修订项

## Non-goals

- Do not rewrite original Word report sections.
- Do not automatically replace report claims in the original body.
- Do not introduce LLM-based rewriting.
- Do not change the `/waf` preprocessing flow.
- Do not remove the existing Markdown audit opinion.

## Verification

- `pytest tests/test_report_augmenter.py tests/test_waf_audit_endpoints.py tests/test_waf_audit_frontend.py`
- Verify the generated DOCX contains the audit appendix text.
