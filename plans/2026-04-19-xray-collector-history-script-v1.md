# xray collector history script v1

## 背景

当前 xray 上传主链已经能完成：

- 日志包上传
- analyzer 解析
- `unified.json`
- `report_payload.json`
- `report.docx`

同时，xray trend integration round1 已经把趋势增强骨架接到了报告渲染链中，但真实图表仍依赖日志包内存在 canonical `resource_history.csv` 或等价的多时间点历史资源数据。

用户提供的当前 `xray-collector.sh` 与对应日志包主要包含：

- 当前资源快照
- 最近部分系统日志
- 容器状态 / inspect / 日志尾部
- `minion` health / version

但还缺少：

- 面向趋势链的稳定历史资源点
- canonical `resources/resource_history.csv`
- 明确的历史采集覆盖说明

## 本轮范围

1. 新增一版自包含 xray 采集脚本
   - 保留当前快照采集
   - 保留 xray / minion 关键日志采集
   - 增加 built-in `./minion collect`
   - 增加 machine id / 漏洞库版本采集

2. 为趋势链补最小历史资源采集
   - 优先从 sysstat / `sar` 历史中提取最近 30 天资源点
   - 统一落成 `resources/resource_history.csv`
   - 12 小时一个 bucket
   - 不伪造不存在的历史

3. 在日志包内补采集说明
   - 明确历史数据来源
   - 明确无历史时的降级原因

4. 最小文档同步
   - `docs/xray_collector_input_spec_v1.md`
   - `docs/project_status.md`

## 非目标

- 不改 `/api/tasks`
- 不改 analyzer 主流程
- 不改 xray parser 规则
- 不引入新的后台服务
- 不伪造未来趋势点

## 验证

计划执行：

```bash
bash -n scripts/xray_collect_report_bundle_v2.sh
```

并人工确认：

- 采集脚本输出包含 `resources/resource_history.csv`
- 无 `sar` 历史时仍会输出 header 和说明文件
- 历史来源说明与当前 xray trend 集成路径一致
