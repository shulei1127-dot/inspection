# xray v4 collector report field fix

## 背景

用户通过前端上传 `xray-collector.20260421184735.tar.gz` 后生成 Word，发现：

- 产品 / 引擎 / 漏洞库 / 机器码没有填入报告
- 第一页/报告中的时间展示不符合预期

初步排查：

- 日志包内已经包含 `summary/xray_collection_summary.json`、`node-info/versions.txt`、`xray-logs/machineid.txt` 等字段
- analyzer 当前将该包识别为 `xray-collector/v1`
- 当前 `xray-collector/v1` 解析路径未读取 v4_project 新增的机器可读摘要和版本文件
- 报告日期当前直接来自 `unified_json.generated_at` 的 ISO 日期字符串

## 本轮范围

1. analyzer 侧补最小 v4_project 字段读取
   - `summary/xray_collection_summary.json`
   - `node-info/versions.txt`
   - `node-info/machine-id.txt`
   - `xray-logs/machineid.txt`
   - `xray-logs/vuln-db-version.txt`
   - `health-check/mgmt-health.txt`
   - `health-check/engine-health.txt`
   - `resource-usage/resource-summary.txt`

2. report payload 侧修日期
   - 优先使用日志采集时间 `xray_collected_at`
   - 没有采集时间再回退到 `generated_at`
   - 报告展示日期统一成中文年月日

3. 补最小测试
   - v4_project 样例能提取版本号、漏洞库、机器码、采集时间
   - xray report payload 日期使用采集时间并生成中文日期

## 非目标

- 不改前端
- 不改 `/api/tasks`
- 不做完整 container-history 报告增强
- 不改 Word 模板结构
- 不做 xray 容器趋势图

## 验证

计划执行：

```bash
cd log-analyzer-service && ../.venv/bin/pytest tests/test_api.py -q
.venv/bin/pytest tests/test_report_payload_mapper.py tests/test_tasks.py -q
```
