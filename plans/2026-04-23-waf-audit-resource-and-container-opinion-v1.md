## 任务

WAF 审计日志核验意见格式 v1：
- 资源使用率按 CPU / 内存 / 磁盘分别核验，并尽量比对报告展示值与日志值是否接近
- 容器运行状况单列说明，异常容器给出日志支撑与建议

## 背景

当前 `audit_opinion.md` 和回填 Word 附录主要按 claim 状态分段输出，适合内部调试，但不够贴近用户实际阅读口径。

现阶段用户更关心两类内容：
1. 报告里写的 CPU / 内存 / 磁盘是否与日志证据一致
2. 容器是否运行异常，异常时是否有日志支撑与处置建议

## 本轮范围

1. 保留现有 WAF 审计主链，不改 `/api/tasks`、xray、`waf_audits` 总体流程
2. 增强资源 claim 的数值一致性核验
3. 在基于 preprocessing 的审计链路中补充 `container/docker_stats.txt` 解析
4. 重排 `audit_opinion.md` 与 `audit_augmented_report.docx` 附录结构

## 实施点

### 1. 资源核验增强

- 在 `audit_result` 中补充 `claim_subject`、`claim_metric`、`claim_source_text`
- 对 `resource_usage_assessment`：
  - 继续保留 normal / high / critical 定性核验
  - 若报告原文中能提取百分比，且日志中也有百分比，则增加“数值接近性”判断
  - v1 规则：
    - 差值 `<= 10` 个百分点：视为口径接近
    - 差值 `> 10` 且 `<= 15`：降为部分证实
    - 差值 `> 15`：判为冲突

### 2. preprocessing 容器证据补充

- 在 `_build_log_evidence_from_preprocessing()` 中增加对 `source_directory_path/container/docker_stats.txt` 的解析
- 从中提取：
  - 容器名
  - CPU%
  - 内存使用率%
  - 内存使用量 / 限额
- 写入：
  - `runtime_components`
  - `resource_signals`
  - 必要的高负载 `log_findings`

### 3. 日志核验意见结构改版

- `audit_opinion.md` 输出改为更贴近业务阅读的结构：
  - 总体审核结论
  - 资源使用率核验
  - 容器运行状况核验
  - 仍需人工判断
  - 建议修订
- `audit_augmented_report.docx` 附录与 markdown 使用同一结构

## 验证

至少覆盖：
- 报告写 56%，日志 85% 时资源核验判为冲突
- preprocessing 审计链可从 `docker_stats.txt` 生成容器证据
- `audit_opinion.md` 和回填 Word 都包含“资源使用率核验”“容器运行状况核验”
