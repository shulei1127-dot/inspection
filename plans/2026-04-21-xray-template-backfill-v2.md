# xray 模板回填 v2

## 背景

用户提供了手工调整后的 `/Users/shulei/Downloads/report.docx`，希望后续 xray 日志解析完成后直接按这份版式输出报告。

检查结论：

- 该文档是已渲染成品，当前没有 Carbone 占位符
- 版式可以作为新版 xray 模板基准
- 容器明细表新增了 `CPU使用率` / `内存使用率` 列，但当前 `report_payload.container_rows` 还没有对应字段

## 本轮范围

1. 以用户提供的 `report.docx` 为版式基准，生成新的 `templates/xray_inspection_report.docx`
2. 重新插入 Carbone 占位符
   - 产品主要信息
   - 检查项
   - 容器运行状态详情
   - 节点检查详情
   - 巡检结论与处置建议
3. 扩展最小容器报告字段
   - `container_rows[].cpu_percent`
   - `container_rows[].memory_percent`
4. analyzer 侧从 xray project-compatible v4 的 `summary.containers[]` 提取容器 CPU / 内存使用率
5. 用当前任务 `tsk_20260421_105826_98689b67` 重新生成报告验证

## 非目标

- 不改上传接口
- 不改前端
- 不做趋势图插入
- 不重构 unified-json 契约，只增加向后兼容的可选容器字段
- 不扩展更多 xray 采集项

## 验证

计划执行：

```bash
cd log-analyzer-service && ../.venv/bin/pytest tests/test_api.py -q
.venv/bin/pytest tests/test_report_payload_mapper.py tests/test_report_rendering_service.py tests/test_tasks.py -q
```

并检查新渲染的 DOCX：

- 文档有效
- 模板占位符已被替换
- 产品版本 / 引擎版本 / 漏洞库 / 机器码正常
- 容器表包含 CPU / 内存使用率
