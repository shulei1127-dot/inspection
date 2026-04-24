# WAF 审计最小前端页 v1

## 背景

`/console` 已经接入 xray 与 WAF 趋势增强两个真实前端入口，剩余 `WAF 报告审计` 仍然跳转到 Swagger。当前后端已经有完整的 WAF 审计 API：

- `POST /api/waf-audits`
- `GET /api/waf-audits`
- `GET /api/waf-audits/{task_id}`
- `GET /api/waf-audits/{task_id}/claims`
- `GET /api/waf-audits/{task_id}/audit-result`
- `GET /api/waf-audits/{task_id}/audit-opinion`

本轮目标是补一个最小可操作页面，让 `/console` 中 WAF 审计模块也成为真入口。

## 范围

本轮只做：

1. 新增 `GET /waf-audits/ui` 前端页面
2. 页面上传人工巡检报告 DOCX 和 WAF 日志包
3. 调用 `POST /api/waf-audits`
4. 展示 `task_id`、`status`、`claim_count`、`confirmed_count`、`conflict_count`
5. 提供下载 / 查看入口：
   - `GET /api/waf-audits/{task_id}`
   - `GET /api/waf-audits/{task_id}/claims`
   - `GET /api/waf-audits/{task_id}/audit-result`
   - `GET /api/waf-audits/{task_id}/audit-opinion`
6. 更新 `/console` 中 WAF 审计模块入口，不再标注页面待接入
7. 更新首页、README、project_status
8. 补最小页面测试

## 非目标

- 不改 WAF 审计业务逻辑
- 不改 claims / evidence / audit_result 契约
- 不做审计结果可视化表格
- 不做审计任务历史页
- 不做 DOCX 审计意见导出
- 不引入 React / Vue / Vite
- 不新增数据库表

## 页面行为

1. 用户选择人工巡检报告 DOCX
2. 用户选择 WAF 日志包
3. 用户可保留默认 `report_lang=zh-CN`
4. 页面调用 `POST /api/waf-audits`
5. 页面展示摘要计数和产物路径
6. 页面开放 JSON 结果和 Markdown 审计意见下载入口

## 验证

计划执行：

```bash
.venv/bin/pytest -q tests/test_waf_audit_frontend.py tests/test_frontend_console.py tests/test_home.py
.venv/bin/pytest -q
```

