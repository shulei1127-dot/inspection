# 基于状态分析报告的巡检报告趋势增强子链路 v1

## Goal

新增一条独立于现有 `/api/tasks`、x-ray 主链路和 `waf_audits` 的趋势增强子链路。

最小闭环：

1. 读取已清洗状态分析报告 `.md`
2. 生成 `trend_input.json`
3. 生成 `trend_assessment.json`
4. 生成 `trend_summary.md`
5. 生成 1~3 张 PNG 静态图
6. 若提供基础 `docx`，输出 `augmented_report.docx`

## Hard Boundaries

- 不改现有 `/api/tasks`
- 不改现有 x-ray 主链路
- 不改现有 `waf_audits` 审核链路
- 不做截图 OCR
- 不做 Mermaid 直接写入 Word
- 不做 LLM 直接预测数值
- 不做复杂时序模型
- 不重写整份报告，只做附录增强
- `trend_input_builder` 第一阶段只支持已清洗状态分析报告 `.md`
- 第一阶段只使用文本里已有时间点 / 已有事件，不补历史序列

## Scope

### Do

- 新增独立 trend schemas
- 新增 builder / forecaster / chart renderer / summary renderer / report augmenter / orchestration service
- 通过标准库实现 PNG 与 docx 附录增强，减少外部依赖
- 新增离线脚本入口与测试

### Do Not

- 不新增 API endpoint
- 不从原始巡检报告或原始日志直接反推趋势
- 不把 markdown 渲染后再灌进 docx

## Acceptance

- 规则驱动输出保守趋势判断
- 每个指标项输出 `status + confidence + evidence + reason_codes`
- 少于 2 个时间点不生成图
- docx 附录内容直接由 `trend_assessment.json` 生成
- 现有 x-ray / waf_audits 回归保持通过
