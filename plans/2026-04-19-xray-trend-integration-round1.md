# xray trend integration round1

## 背景

当前项目已经有一条独立可运行的 trend enhancement 子链：

- `trend_input.json`
- `trend_assessment.json`
- `trend_summary.md`
- `trend_state_graph.mmd`
- 可选 `trend_state_graph.png`
- 可选 DOCX 附录增强

但这条链目前主要接在 WAF preprocessing / status-analysis markdown 上，xray 上传主链尚未接入。

当前目标不是立刻把 xray 的真实历史数据规则做满，而是先把 xray 报告链的趋势增强功能位接好，让后续新增真实日志数据时只需补提取规则，不必重构报告主流程。

## 本轮范围

1. 为 xray 新增最小趋势输入构建层
   - 从 `unified.json` 和可选 `resource_history.csv` 构建 `trend_input.json`
   - 当前支持“无历史数据降级”
   - 当前支持“有 canonical resource_history.csv 时直接消费”

2. 为 xray 新增最小趋势增强服务
   - 生成：
     - `workdir/{task_id}/trend/trend_input.json`
     - `workdir/{task_id}/trend/trend_assessment.json`
     - `workdir/{task_id}/trend/trend_summary.md`
     - `workdir/{task_id}/trend/trend_state_graph.mmd`
     - `outputs/{task_id}/trend/*.png`
   - 复用现有：
     - `trend_forecaster`
     - `trend_chart_renderer`
     - `trend_mermaid_renderer`
     - `report_augmenter`

3. 将 xray 趋势增强非阻断地接入现有报告渲染流程
   - 先保持 report render 主链成功优先
   - 趋势增强失败不得导致 xray 报告渲染失败
   - 若没有足够历史点，不伪造趋势图

4. 补最小测试
   - 无资源历史时可稳定产出趋势工件并降级
   - 有 `resource_history.csv` 时可生成历史趋势图
   - 有可用图表时可增强 xray DOCX

5. 更新最小文档
   - README
   - docs/project_status.md

## 非目标

- 不改 analyzer 主契约
- 不改 `/api/tasks` 接口形状
- 不开始写 xray 专用前端趋势页
- 不伪造未来预测图
- 不在本轮做 xray 多时间点日志提取规则全集
- 不把 WAF trend 子链改成通用大框架

## 验证

计划执行：

```bash
.venv/bin/pytest tests/test_xray_trend_service.py tests/test_report_rendering_service.py tests/test_tasks.py -q
.venv/bin/pytest tests -q
cd log-analyzer-service && ../.venv/bin/pytest tests -q
```

并用一个现有 xray 任务验证：

- 无 `resource_history.csv` 时报告仍可正常生成
- 有历史数据 fixture 时可生成趋势图工件
- 若 Mermaid renderer 可用，则生成 `trend_state_graph.png`
