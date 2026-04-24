# xray 最小前端页 v1

## 背景

`/console` 已经成为轻量平台控制台，但 xray 巡检报告生成仍然标注为“页面待接入”，用户需要跳到 Swagger 手动调用 `/api/tasks`。本轮目标是把 xray 主链路做成一个最小可操作页面，让控制台里的 xray 模块成为真入口。

## 范围

本轮只做：

1. 新增 `GET /xray` 前端页面
2. 页面上传 xray 日志包并调用 `POST /api/tasks`
3. 展示 task_id、status、summary、关键产物路径
4. 如果上传结果已包含 `report_file_path`，提供 Word 下载入口
5. 如果尚未渲染，提供 `POST /api/tasks/{task_id}/render-report` 触发按钮
6. 渲染成功后提供 `GET /api/tasks/{task_id}/report` 下载入口
7. 更新 `/console` 中 xray 模块入口，不再标注 xray 页面待接入
8. 补最小页面测试与文档

## 非目标

- 不改 `/api/tasks` 业务逻辑
- 不改 analyzer / xray parser
- 不改 Carbone 渲染实现
- 不做任务历史列表
- 不做模板配置
- 不引入 React / Vue / Vite
- 不新增数据库表
- 不实现 WAF 审计前端页

## 页面行为

1. 用户选择 xray 日志包
2. 用户可保留默认 `parser_profile=default` 与 `report_lang=zh-CN`
3. 页面调用 `POST /api/tasks`
4. 页面展示：
   - `task_id`
   - `status`
   - `service_count`
   - `container_count`
   - `issue_count`
   - `unified_json_path`
   - `report_payload_path`
5. 页面提供：
   - 任务详情链接：`GET /api/tasks/{task_id}`
   - Word 下载链接：`GET /api/tasks/{task_id}/report`
   - 渲染按钮：`POST /api/tasks/{task_id}/render-report`

## 验证

计划执行：

```bash
.venv/bin/pytest -q tests/test_xray_frontend.py tests/test_frontend_console.py tests/test_home.py
.venv/bin/pytest -q
```

