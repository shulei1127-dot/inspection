## 任务

LLM 接入方案 v1

## 目标

在不破坏当前项目可解释、可回归主链的前提下，引入 LLM 做“表达增强”和“分析辅助”，而不是替代底层规则解析。

## 当前项目现状

当前主链已经形成：

`日志包 -> 解压/清洗/解析 -> 结构化结果 -> report payload -> Word`

已具备可供 LLM 安全消费的中间产物：

- `unified.json`
- `status_analysis_summary.json`
- `status_analysis_evidence.json`
- `trend_input.json`
- `trend_assessment.json`
- `audit_result.json`
- `report_payload.json`

这意味着 LLM 不需要直接读取全量原始日志，而可以工作在已经清洗好的结构化层之上。

## 接入原则

1. 不让 LLM 直接替代底层日志解析
2. 不让 LLM 直接决定 CPU / 内存 / 磁盘是否异常
3. 不让 LLM 直接充当审计判定引擎
4. LLM 失败时，系统必须能稳定回退到规则版输出
5. 所有 LLM 输出默认标记为“增强内容”而不是“唯一事实来源”

## 最适合的切入点

### 1. 巡检文案增强

输入：
- `report_payload.json`
- `audit_result.json`
- `status_analysis_summary.json`

输出：
- `llm_report_summary.md`
- `llm_disposal_advice.md`

目标：
- 把现有规则输出变成更像客户交付件的语言
- 把重复、松散的异常说明合并成自然段
- 将“日志依据 + 处置建议”表达得更专业

### 2. 趋势结论增强

输入：
- `trend_assessment.json`
- `trend_summary.md`

输出：
- `llm_trend_summary.md`

目标：
- 不改变 `stable / pressure_high / deteriorating / unknown` 这些规则态
- 只增强结论解释、风险描述、管理层可读性

### 3. 审计意见增强

输入：
- `audit_result.json`
- `log_evidence.json`

输出：
- `llm_audit_opinion.md`

目标：
- 将当前 WAF 审计意见改写成更正式的巡检附录措辞
- 做客户版 / 内部版双风格切换

## 不建议当前就做的部分

1. 直接把全量日志喂给 LLM
2. 用 LLM 替代 preprocessing / analyzer / parser
3. 用 LLM 直接判断资源异常或健康状态
4. 用 LLM 直接决定最终审计 verdict

这些地方更需要：
- 稳定性
- 可解释性
- 可回归性
- 对同一输入的确定性

## 建议架构

### 平台侧增加抽象

新增：
- `app/services/llm_enhancer.py`

建议模式：
- `disabled`
- `local_mock`
- `remote_api`

与 Mermaid / analyzer 的模式设计保持一致。

### 最小服务接口建议

如果后续服务化，建议单独做 `report-llm-service`，而不是把 LLM 逻辑直接揉进主平台。

最小接口：

- `GET /health`
- `POST /enhance/report-summary`
- `POST /enhance/audit-opinion`
- `POST /enhance/trend-summary`

### 平台内落盘约定

建议新增可选产物：

- `outputs/{task_id}/llm_report_summary.md`
- `outputs/{task_id}/llm_audit_opinion.md`
- `outputs/{task_id}/llm_trend_summary.md`

如需进 Word：
- 先作为 appendix / optional section 接入
- 不直接覆盖规则主正文

## Prompt / 上下文策略

LLM 输入应只使用结构化、已清洗数据，不直接传原始大日志。

建议输入结构：

1. `system`
   - 明确“禁止虚构事实”
   - 明确“只能基于输入生成”
   - 明确“结论与建议必须区分”

2. `context`
   - 产品类型
   - 报告风格
   - 面向对象（客户 / 内部）

3. `facts`
   - 结构化 JSON 摘要

4. `output_schema`
   - 固定 markdown 或 JSON schema

## 风险与控制

### 风险

1. 幻觉补事实
2. 建议过度泛化
3. 与规则 verdict 冲突
4. 成本和时延不可控

### 控制

1. 仅允许消费结构化结果
2. 输出必须带 schema / section 约束
3. 规则 verdict 优先，LLM 只做解释层
4. 默认可关闭，失败自动回退

## 建议落地顺序

### Phase 1

先做：
- `LlmEnhancer` 抽象
- `disabled / local_mock / remote_api`
- 只接 `audit_result.json -> llm_audit_opinion.md`

原因：
- 输入最稳定
- 价值直观
- 不改主业务 verdict

### Phase 2

再做：
- `trend_assessment.json -> llm_trend_summary.md`

### Phase 3

最后做：
- `report_payload.json -> llm_report_summary.md`
- 可选接入 Word appendix

## 验收标准

1. LLM 关闭时，现有主链零变化
2. LLM 开启时，生成独立增强产物，不覆盖规则主产物
3. 同一份结构化输入，输出格式稳定
4. 输出中不得出现输入中不存在的设备、容器、版本或异常事实
5. 任一 LLM 请求失败，不影响 `/api/tasks`、WAF、xray、trend 主链完成
