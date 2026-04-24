## 任务

WAF 审计回填 Word v1：
- 将“容器运行状况核验”从纯段落说明升级为表格展示

## 目标

在 `audit_augmented_report.docx` 附录中，用表格展示容器运行状态数据，至少包含：
- 容器名称
- 运行状态
- CPU 使用率
- 内存使用率
- 异常支撑
- 建议

## 范围

1. 不改 WAF 主流程
2. 不改 `/api/tasks`、xray、trend 子链
3. 保留 markdown 版审核意见的现有结构
4. 仅增强 Word 附录在“容器运行状况核验”这一节的展示形式

## 实施点

1. 在 `audit_opinion_renderer` 中抽出容器核验行构建逻辑
2. 在 `report_augmenter` 中新增最小 Word 表格生成能力
3. 仅对“容器运行状况核验”插入表格，其余章节继续用段落
4. 补测试验证生成的 docx 中存在容器表头和容器数据
