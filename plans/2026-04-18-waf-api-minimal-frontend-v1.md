# WAF API 最小前端 v1：上传日志包 + 生成趋势增强 + 下载产物

## 背景

当前 WAF preprocessing 与 trend enhancement 已经完成 API 化：

- `POST /api/waf/preprocessing`
- `GET /api/waf/preprocessing/{preprocessing_id}`
- `GET /api/waf/preprocessing/{preprocessing_id}/status-analysis`
- `POST /api/waf/trend-enhancements`
- `GET /api/waf/trend-enhancements/{trend_id}`
- `GET /api/waf/trend-enhancements/{trend_id}/summary`
- `GET /api/waf/trend-enhancements/{trend_id}/augmented-report`

但用户仍需要在 Swagger 或 curl 中手动串联两步流程。本轮目标是补一个最小可用的内置前端页面，把上传 WAF 日志包、生成趋势增强、下载产物串成一条可操作链路。

## 范围

本轮只做：

1. 新增一个轻量内置页面，例如 `GET /waf`
2. 页面调用现有 WAF API，不新增业务 API
3. 支持上传 WAF 日志压缩包
4. 支持可选上传基础 DOCX 报告，用于生成增强报告
5. 展示 preprocessing / trend enhancement 的关键返回结果
6. 提供状态分析 Markdown、趋势摘要 Markdown、可选增强 DOCX 下载入口
7. 更新最小文档与状态说明
8. 补最小页面可达性测试

## 非目标

- 不引入 React/Vue/Vite 等前端工程
- 不新增数据库表
- 不新增 WAF 业务能力
- 不改变 preprocessing / trend enhancement 现有 API 契约
- 不改 `/api/tasks`
- 不改 xray 主链路
- 不改 `waf_audits`
- 不做登录、权限、任务列表、历史管理

## 设计

### 页面路径

- `GET /waf`
- 首页 `/` 增加 `/waf` 入口链接

### 页面流程

1. 用户选择 WAF 全量日志包
2. 用户可选选择基础巡检报告 DOCX
3. 点击生成
4. 页面用 `FormData` 调 `POST /api/waf/preprocessing`
5. 取得 `preprocessing_id`
6. 页面用 `preprocessing_id` 和可选 DOCX 调 `POST /api/waf/trend-enhancements`
7. 取得 `trend_id`
8. 页面展示关键摘要和下载链接

### 下载链接

- `GET /api/waf/preprocessing/{preprocessing_id}/status-analysis`
- `GET /api/waf/trend-enhancements/{trend_id}/summary`
- `GET /api/waf/trend-enhancements/{trend_id}/augmented-report`

增强 DOCX 仅在 `augmented_report_path` 存在时展示。

### 错误处理

页面优先展示 API 的结构化错误：

- `error.code`
- `error.message`
- `error.details`

若返回非 JSON，则展示 HTTP 状态码和文本摘要。

## 测试

新增或更新测试覆盖：

- `GET /waf` 返回 200
- 页面包含 WAF 上传、趋势增强、下载产物相关入口文案
- 页面包含现有 WAF API 路径，确保未偏离当前接口契约
- 首页 `/` 包含 `/waf` 入口

## 验证

计划执行：

```bash
.venv/bin/pytest -q tests/test_waf_frontend.py tests/test_home.py
.venv/bin/pytest -q
```

## 文档更新

- `README.md`：补 `/waf` 页面使用说明
- `docs/project_status.md`：记录本轮新增最小 WAF 前端入口

