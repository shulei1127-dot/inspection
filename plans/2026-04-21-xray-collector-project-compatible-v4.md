# xray collector project-compatible v4

## 背景

用户提供了新的 `x-ray_collect_v4.sh`，目标是让客户服务器执行后生成一个日志压缩包，并能直接交给当前项目的 xray 链路生成 Word 文档。

当前项目里 xray 链路已经支持多种输入形态，但 analyzer 仍更偏好以下稳定输入：

- `system/system_info`
- `system/systemctl_status`
- `containers/docker_ps`
- `system-logs/`
- `resource-snapshots/`
- `health-checks/`
- `container-logs/`
- `minion-logs/`

用户的新脚本增加了更报告友好的目录：

- `node-info/`
- `health-check/`
- `resource-usage/`
- `container-status/`
- `anomaly-detection/`
- `minion-collect/`

本轮目标是优化脚本，不改平台主流程、不改 analyzer，只让采集包同时满足“当前项目可解析”和“报告后续扩展更友好”。

## 本轮范围

1. 新增项目兼容版 xray 采集脚本
   - 默认安装目录 `/data/x-ray`
   - 支持 `XRAY_HOME` 覆盖
   - 支持 `ALLOW_FULL_SCAN=true/false`
   - 常见路径优先，最后才全盘兜底

2. 输出双轨目录
   - 兼容当前 analyzer 的 canonical / legacy 目录
   - 保留用户 v4 中面向报告展示的新目录

3. 增加机器可读摘要
   - `summary/xray_collection_summary.json`
   - 便于后续 analyzer 稳定接入新报告字段

4. 保留容器运行状态证据
   - 当前状态
   - restart count
   - health
   - exit code
   - OOM
   - Docker daemon errors

5. 保留 `minion collect`
   - 支持 `INCLUDE_MINION_COLLECT=true/false`
   - 优先尝试 `./minion collect -f`
   - 失败时兜底读取默认 `minion_report.gz`

## 非目标

- 不改 `/api/tasks`
- 不改 analyzer parser
- 不改 xray Word 模板
- 不依赖外网
- 不主动安装 sysstat / jq / Python package
- 不伪造 CPU / 内存 / 磁盘历史趋势点

## 验证

计划执行：

```bash
bash -n scripts/xray_collect_report_bundle_v4_project.sh
```

并人工确认脚本输出包含：

- `system/system_info`
- `containers/docker_ps`
- `health-checks/minion-mgmt-health.txt`
- `resource-snapshots/docker-ps-a.txt`
- `node-info/versions.txt`
- `summary/xray_collection_summary.json`
- `container-history/container-state-history.txt`
- `minion-collect/minion-collect.tar.gz` 或错误说明
