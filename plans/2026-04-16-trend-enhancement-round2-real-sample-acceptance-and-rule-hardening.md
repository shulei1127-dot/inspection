# trend enhancement round2：真实样本验收 + 规则补强 + 回归夹具沉淀

## Goal

在不扩新方向的前提下，把现有独立 trend enhancement 子链路从“能跑”推进到：

- 在真实状态分析 markdown 样本下更稳
- 趋势判断更保守、更可信
- docx 末尾附录更自然
- 夹具与测试可持续支撑后续迭代

## Hard Boundaries

- 不改 `/api/tasks`
- 不改现有 xray 主链路
- 不改现有 `waf_audits`
- 不新增 endpoint
- 不做截图 OCR
- 不引入 LLM 做趋势判定
- 不做复杂时序模型
- 不重写整份报告
- 只继续强化现有独立 trend subchain

## Scope

### 1. 真实样本验收

- 用现有真实状态分析 `.md` 跑完整 trend subchain
- 可选带一个真实 `docx` 跑附录增强
- 复盘：
  - 哪些字段抽取准确
  - 哪些字段漏抽 / 误抽
  - 哪些趋势判断合理
  - 哪些判断偏保守 / 偏激进
  - 哪些规则最值得补强

### 2. 规则补强

- 只补命中率与可信度，不扩功能面
- 优先收敛：
  - markdown 更多表格 / 列表 / 混合格式解析
  - CPU / 内存 / 磁盘样本抽取鲁棒性
  - 稳定性 / 重启事件识别口径
  - `confidence` 判定规则
  - `unknown / stable / pressure_high / deteriorating` 边界

### 3. 回归夹具沉淀

- 沉淀真实样本改写版 fixtures，至少覆盖：
  - 多时间点样本
  - 单快照样本
  - 数据缺失样本
  - 文本噪声样本
- 为 builder / forecaster / augmenter 增补回归测试

## Expected Files

- `plans/2026-04-16-trend-enhancement-round2-real-sample-acceptance-and-rule-hardening.md`
- `app/services/trend_input_builder.py`
- `app/services/trend_forecaster.py`
- `app/services/report_augmenter.py`
- `tests/fixtures/trend_reports/*`
- `tests/test_trend_input_builder.py`
- `tests/test_trend_forecaster.py`
- `tests/test_report_augmenter.py`
- `tests/test_trend_enhancement_service.py`
- `README.md`
- `docs/project_status.md`

## Validation

- 先跑真实样本验收并记录复盘结论
- 再跑趋势链路定向测试
- 最后跑全仓 `pytest`

## Acceptance

- 真实样本下 `trend_input.json` 更贴近原文事实
- 规则补强后不因“看起来聪明”而硬猜趋势
- 数据不足时优先 `unknown`
- 单快照不生成趋势图
- `augmented_report.docx` 附录自然且不破坏原文
- 新增回归夹具能稳定锁住本轮真实样本命中率
