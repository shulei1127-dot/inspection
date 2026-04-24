# xray 单机版资源字段回填

## 背景

xray 当前优先考虑单机版部署：管理节点和引擎节点部署在同一台服务器上。只有分布式部署时，才需要额外采集各个引擎节点的 CPU / 内存 / 磁盘。

当前报告模板里同时展示管理节点和引擎节点资源，但日志包只提供一台机器的资源快照，导致引擎节点 CPU / 内存 / 磁盘显示为 `-`。

## 本轮范围

1. 平台 report payload 层增加 xray 单机版默认语义
2. 单机版下：
   - `xray_engine_cpu` 默认复用 `xray_mgmt_cpu`
   - `xray_engine_memory` 默认复用 `xray_mgmt_memory`
   - `xray_engine_disk` 默认复用 `xray_mgmt_disk`
3. 保留未来分布式扩展口：
   - 如果 metadata 明确提供 `xray_engine_*`，优先使用独立引擎节点字段
4. 更新最小测试和文档

## 非目标

- 不实现分布式部署采集
- 不新增多个引擎节点表格
- 不改上传接口
- 不改 analyzer 主流程

## 验证

```bash
.venv/bin/pytest tests/test_report_payload_mapper.py tests/test_report_rendering_service.py -q
```

并用当前 xray 任务重新生成报告，确认引擎节点 CPU / 内存 / 磁盘不再显示为 `-`。
