# 平台前端骨架 v1：Stitch 控制台落地 + WAF 页面统一风格

## 背景

Stitch 产出的控制台视觉稿已经收敛到适合当前项目的轻量技术形态：

- 单文件 HTML
- 内联 CSS
- 原生 JavaScript
- 不依赖外部 CDN / 字体 / 图标库 / 远程图片

当前项目已有 `/waf` 最小工作台，能够真实调用 WAF preprocessing 与 trend enhancement API，但视觉风格还没有和控制台统一。本轮直接落地，不继续等待 Stitch 输出 WAF 详情页。

## 范围

本轮只做：

1. 新增 `/console` 统一控制台页面
2. `/console` 使用 Stitch 控制台视觉方向，但改成项目真实入口
3. 保留 `/waf` 真实 API 调用逻辑，并统一为同一套视觉语言
4. 更新首页入口，优先引导到 `/console`
5. 补最小页面测试
6. 更新 README 与 project_status

## 页面入口

- `/console`：平台统一控制台
- `/waf`：WAF 日志清洗与趋势增强工作台

## 控制台模块

`/console` v1 展示：

- xray 巡检报告生成：当前以 API 文档入口承接，标注页面待接入
- WAF 日志清洗与趋势增强：进入 `/waf`
- WAF 报告审计：当前以 API 文档入口承接，标注页面待接入
- API 文档：进入 `/docs`
- 服务健康状态：平台可检查，Analyzer / Carbone / Mermaid Renderer 暂标注待后端聚合
- 最近任务活动：暂为空态，不展示假数据

## WAF 页面

`/waf` v1 保持已有真实链路：

1. 上传 WAF 全量日志包
2. 可选上传基础 DOCX 报告
3. 调 `POST /api/waf/preprocessing`
4. 调 `POST /api/waf/trend-enhancements`
5. 展示 `preprocessing_id` / `trend_id` / `overall_status` / `data_quality`
6. 提供下载：
   - 状态分析 Markdown
   - 趋势摘要 Markdown
   - 增强版 Word 报告

## 非目标

- 不引入 React / Vue / Vite
- 不新增 API
- 不实现 xray 专属前端页面
- 不实现 WAF 审计专属前端页面
- 不实现统一任务列表 API
- 不改 WAF preprocessing / trend enhancement 业务逻辑
- 不改 `/api/tasks` / xray / `waf_audits`

## 验证

计划执行：

```bash
.venv/bin/pytest -q tests/test_frontend_console.py tests/test_waf_frontend.py tests/test_home.py
.venv/bin/pytest -q
```

