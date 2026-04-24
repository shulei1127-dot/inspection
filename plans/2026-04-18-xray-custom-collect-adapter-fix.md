# xray 自定义采集包适配修复

## 背景

用户通过 `/xray` 上传 `xray_log_collect_*` 日志包后，生成的 Word 报告内容完全不对且大量英文。排查发现：

- `workdir/tsk_20260418_155725_40476f14/unified.json` 中 `metadata.product_type=unknown`
- analyzer 走了 `linux-default-parser`
- 平台因此使用默认报告模板与默认英文 fallback 文案
- 实际上传包结构是自定义 `xray_log_collect_*` 脚本输出，不属于当前 `xray-collector/v1` 或 `minion-report/v1` 识别规则

本轮目标是让这类脚本输出被 analyzer 识别为 xray 输入，并复用现有 xray 报告链。

## 范围

本轮只做：

1. analyzer 侧识别 `xray_log_collect_*` 自定义采集包结构
2. 映射已有文件到 canonical 输入：
   - `uname.txt`
   - `date.txt`
   - `uptime.txt`
   - `network.txt`
   - `docker_ps.txt`
   - `minion_collect.txt`
3. 补最小 xray metadata：
   - `machine_id.txt`
   - `vuln_db_version.txt`
   - `xray_tree.txt` 中的产品版本线索
4. 保持平台主流程、模板和前端不变
5. 补 analyzer 测试覆盖

排查中额外发现两处小修正也纳入本轮：

- xray 场景下 `report_payload` 的标题和状态标签应使用中文，避免中文模板内夹杂 `Inspection Report` / `Running` / `Warning`
- `POST /api/tasks/{task_id}/render-report` 的响应应返回实际选中的模板路径，避免内容已用 xray 模板但响应仍显示默认模板

## 非目标

- 不改 Word 模板
- 不改 `/api/tasks` 上传主流程
- 不改 `/xray` 前端
- 不扩复杂诊断规则
- 不解析全部容器日志
- 不引入新产品类型

## 验证

计划执行：

```bash
cd log-analyzer-service
../.venv/bin/pytest -q tests/test_api.py
cd ..
.venv/bin/pytest -q tests/test_report_payload_mapper.py tests/test_tasks.py
.venv/bin/pytest -q
```
