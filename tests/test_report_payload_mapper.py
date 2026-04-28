from pathlib import Path
from zipfile import ZipFile

from app.schemas.unified_json import UnifiedJsonV1
from app.services.report_payload_mapper import map_unified_json_to_report_payload


def test_xray_payload_appendix_contains_template_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENV_FILE", "/tmp/nonexistent-xray-payload.env")
    unified_json = UnifiedJsonV1.model_validate(
        {
            "schema_version": "unified-json/v1",
            "task_id": "tsk_xray_payload_001",
            "generated_at": "2026-04-14T14:30:00Z",
            "host_info": {
                "hostname": "host-a",
                "ip": "10.20.20.208",
                "os_name": "Ubuntu 22.04.5 LTS",
                "kernel_version": "5.15.0-119-generic",
                "timezone": "Asia/Shanghai",
            },
            "summary": {
                "overall_status": "warning",
                "service_count": 2,
                "service_running_count": 1,
                "container_count": 20,
                "container_running_count": 19,
                "issue_count": 2,
                "issue_by_severity": {
                    "critical": 0,
                    "high": 0,
                    "medium": 1,
                    "low": 1,
                    "info": 0,
                },
            },
            "services": [
                {
                    "name": "minion",
                    "display_name": "minion service",
                    "status": "running",
                    "enabled": True,
                    "notes": "systemd state: load=loaded active=active sub=running",
                },
                {
                    "name": "prometheus",
                    "display_name": "Monitoring system and time series database",
                    "status": "failed",
                    "notes": "systemd state: load=loaded active=failed sub=failed",
                },
            ],
            "containers": [
                {
                    "name": "xray-nginx",
                    "status": "running",
                    "image": "repo/xray-nginx:latest",
                    "ports": ["0.0.0.0:443->8443/tcp"],
                    "cpu_percent": 0.0,
                    "memory_percent": 21.39,
                    "notes": "docker status: Up 27 hours (healthy)",
                },
                {
                    "name": "xray-prometheus",
                    "status": "stopped",
                    "image": "repo/prometheus:latest",
                    "ports": [],
                    "notes": "docker status: Exited (1) 4 hours ago",
                },
            ],
            "issues": [
                {
                    "id": "host-last-boot-missing",
                    "severity": "low",
                    "category": "host",
                    "title": "Host last boot time is missing",
                    "description": "Uptime was parsed successfully but last_boot_at is missing.",
                    "suggestion": "Collect last boot time in system_info when uptime is available.",
                },
                {
                    "id": "service-prometheus-failed",
                    "severity": "medium",
                    "category": "service",
                    "title": "Service prometheus is in failed state",
                    "description": "systemd state: load=loaded active=failed sub=failed",
                    "suggestion": "Inspect `systemctl status prometheus` and recover the prometheus service.",
                },
            ],
            "warnings": [],
            "metadata": {
                "product_type": "xray",
                "xray_product_version": "10-25.11.001_r15",
                "xray_engine_version": "6.18.8_r12",
                "xray_machine_id": "3bc0c6e9e964477f90dd8175e5e5f181",
                "xray_mgmt_health_result": "正常",
                "xray_mgmt_health_note": "检查通过 8 项",
                "xray_engine_health_result": "告警",
                "xray_engine_health_note": "失败项：REDIS PORT STATUS",
                "xray_mgmt_cpu": "8 cores / Intel Xeon / 2.19GHz",
                "xray_mgmt_memory": "总量 15.6GB，已用 4.4GB (28.32%)，可用 10.7GB",
                "xray_mgmt_disk": "/，79.3GB / 96.4GB，/dev/dm-0 (ext4)",
                "xray_minion_log_result": "正常",
                "xray_minion_log_note": "MINION GRPC 检查通过。",
                "xray_mgmt_node_ip": "169.254.1.1",
                "xray_engine_node_ip": "169.253.0.2",
            },
        }
    )

    payload = map_unified_json_to_report_payload(unified_json, report_lang="zh-CN")

    assert payload.report.title == "洞鉴巡检报告"
    assert payload.summary.overall_status_label == "告警"
    assert payload.service_rows[0].status_label == "运行中"
    assert payload.service_rows[0].enabled == "是"
    assert payload.container_rows[1].status_label == "已停止"
    assert payload.container_rows[0].cpu_percent == "0%"
    assert payload.container_rows[0].memory_percent == "21.39%"
    assert payload.appendix["xray_inspection_date_cn"] == "2026年04月14日"
    assert payload.appendix["xray_cover_summary_1"] == "主机：host-a    IP：10.20.20.208"
    assert payload.appendix["xray_executive_status"] == "整体状态为告警，存在需要优先处理的运行风险"
    assert payload.appendix["xray_primary_problem"] == "引擎节点健康检查告警"
    assert payload.appendix["xray_key_runtime_overview"] == "服务 1/2 运行，容器 19/20 运行"
    assert "引擎节点健康检查告警" in str(payload.appendix["xray_key_alerts"])
    assert payload.appendix["xray_service_status_result"] == "告警"
    assert "失败服务：prometheus" in str(payload.appendix["xray_service_status_note"])
    assert payload.appendix["xray_minion_log_result"] == "正常"
    assert payload.appendix["xray_product_version"] == "10-25.11.001_r15"
    assert payload.appendix["xray_engine_health_result"] == "告警"
    assert payload.appendix["xray_mgmt_cpu"] == "8 cores / Intel Xeon / 2.19GHz"
    assert payload.appendix["xray_engine_cpu"] == "8 cores / Intel Xeon / 2.19GHz"
    assert payload.appendix["xray_engine_memory"] == "总量 15.6GB，已用 4.4GB (28.32%)，可用 10.7GB"
    assert payload.appendix["xray_engine_disk"] == "/，79.3GB / 96.4GB，/dev/dm-0 (ext4)"
    assert payload.appendix["xray_deployment_mode"] == "single_node"
    assert payload.appendix["xray_mgmt_node_ip"] == "169.254.1.1"
    assert payload.appendix["xray_node_info"] == (
        "管理节点 IP：169.254.1.1；引擎节点 IP：169.253.0.2"
    )
    assert payload.appendix["xray_time_sync_result"] == "需人工验证"
    assert payload.appendix["xray_scan_task_result"] == "需人工验证"
    assert payload.appendix["xray_report_generation_result"] == "需人工验证"
    assert payload.appendix["xray_primary_recommendation"] == (
        "优先核查 ./minion engine health 返回的失败项，并恢复对应引擎节点组件。"
    )
    assert payload.appendix["xray_issue_1_problem"] == "引擎节点健康检查告警"
    assert payload.appendix["xray_issue_1_evidence"] == "失败项：REDIS PORT STATUS"
    assert payload.appendix["xray_llm_inspection_summary"] == payload.appendix["xray_result_conclusion"]
    assert payload.appendix["xray_llm_exception_summary"] == payload.appendix["xray_key_alerts"]
    assert payload.appendix["xray_issue_2_problem"] == "服务 prometheus 运行失败"
    assert "服务 Monitoring system and time series database 当前状态为 失败" in str(
        payload.appendix["xray_issue_2_evidence"]
    )
    assert payload.appendix["xray_issue_3_problem"] == "Host last boot time is missing"




def test_xray_observation_priority_prefers_high_resource_alerts_over_runtime_warnings() -> None:
    unified_json = UnifiedJsonV1.model_validate(
        {
            "schema_version": "unified-json/v1",
            "task_id": "tsk_xray_payload_002",
            "generated_at": "2026-04-15T02:00:00Z",
            "host_info": {
                "hostname": "host-b",
            },
            "summary": {
                "overall_status": "warning",
                "service_count": 1,
                "service_running_count": 1,
                "container_count": 2,
                "container_running_count": 1,
                "issue_count": 1,
                "issue_by_severity": {
                    "critical": 0,
                    "high": 0,
                    "medium": 1,
                    "low": 0,
                    "info": 0,
                },
            },
            "services": [
                {
                    "name": "minion",
                    "display_name": "minion",
                    "status": "running",
                    "enabled": True,
                }
            ],
            "containers": [
                {
                    "name": "xray-server",
                    "status": "running",
                },
                {
                    "name": "xray-redis",
                    "status": "stopped",
                    "notes": "docker status: Exited (1) 2 minutes ago",
                },
            ],
            "issues": [
                {
                    "id": "container-xray-redis-stopped",
                    "severity": "medium",
                    "category": "container",
                    "related_object_name": "xray-redis",
                    "title": "Container xray-redis is stopped",
                    "description": "docker ps shows exited container",
                    "suggestion": "恢复 redis 容器并检查退出原因。",
                }
            ],
            "warnings": [],
            "metadata": {
                "product_type": "xray",
                "xray_mgmt_disk": "总量 100GB，已用 92GB (92%)",
                "xray_mgmt_health_result": "正常",
                "xray_engine_health_result": "正常",
            },
        }
    )

    payload = map_unified_json_to_report_payload(unified_json, report_lang="zh-CN")

    assert payload.appendix["xray_issue_1_problem"] == "管理节点磁盘使用率偏高"
    assert "92.00%" in str(payload.appendix["xray_issue_1_evidence"]) or "92" in str(
        payload.appendix["xray_issue_1_evidence"]
    )
    assert payload.appendix["xray_issue_2_problem"] == "容器 xray-redis 已停止"
    assert "容器 xray-redis 当前状态为 已停止" in str(payload.appendix["xray_issue_2_evidence"])
    assert payload.appendix["xray_issue_3_problem"] == "-"


def test_xray_resource_alert_thresholds_cover_cpu_memory_and_disk() -> None:
    unified_json = UnifiedJsonV1.model_validate(
        {
            "schema_version": "unified-json/v1",
            "task_id": "tsk_xray_payload_thresholds",
            "generated_at": "2026-04-24T09:22:57Z",
            "host_info": {
                "hostname": "host-thresholds",
            },
            "summary": {
                "overall_status": "warning",
                "service_count": 0,
                "service_running_count": 0,
                "container_count": 0,
                "container_running_count": 0,
                "issue_count": 0,
                "issue_by_severity": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "info": 0,
                },
            },
            "services": [],
            "containers": [],
            "issues": [],
            "warnings": [],
            "metadata": {
                "product_type": "xray",
                "xray_mgmt_health_result": "正常",
                "xray_engine_health_result": "正常",
                "xray_mgmt_cpu": "8 cores / Intel Xeon / 当前使用率 80.0%",
                "xray_mgmt_memory": "总量 15987M，已用 13600M (85.0%)",
                "xray_mgmt_disk": "/，89G / 97G，使用率 98%",
            },
        }
    )

    payload = map_unified_json_to_report_payload(unified_json, report_lang="zh-CN")

    assert payload.appendix["xray_primary_problem"] == "管理节点磁盘使用率偏高"
    assert "管理节点磁盘使用率偏高（98.00%）" in str(payload.appendix["xray_key_alerts"])
    assert payload.appendix["xray_issue_1_problem"] == "管理节点磁盘使用率偏高"
    assert payload.appendix["xray_issue_2_problem"] == "管理节点内存使用率偏高"
    assert payload.appendix["xray_issue_3_problem"] == "管理节点 CPU 使用率偏高"


def test_xray_critical_disk_pressure_surfaces_ahead_of_runtime_critical() -> None:
    unified_json = UnifiedJsonV1.model_validate(
        {
            "schema_version": "unified-json/v1",
            "task_id": "tsk_xray_payload_disk_critical",
            "generated_at": "2026-04-24T09:22:57Z",
            "host_info": {
                "hostname": "host-critical",
            },
            "summary": {
                "overall_status": "warning",
                "service_count": 0,
                "service_running_count": 0,
                "container_count": 1,
                "container_running_count": 0,
                "issue_count": 1,
                "issue_by_severity": {
                    "critical": 0,
                    "high": 0,
                    "medium": 1,
                    "low": 0,
                    "info": 0,
                },
            },
            "services": [],
            "containers": [
                {
                    "name": "xray-redis",
                    "status": "failed",
                }
            ],
            "issues": [
                {
                    "id": "container-xray-redis-restarting",
                    "severity": "medium",
                    "category": "container",
                    "related_object_name": "xray-redis",
                    "title": "Container xray-redis is restarting",
                    "description": "docker ps shows restarting container",
                    "suggestion": "检查 redis 容器重启原因。",
                }
            ],
            "warnings": [],
            "metadata": {
                "product_type": "xray",
                "xray_mgmt_health_result": "告警",
                "xray_mgmt_health_note": "失败项：HEALTH COMMAND ERROR",
                "xray_engine_health_result": "告警",
                "xray_engine_health_note": "失败项：REDIS PORT STATUS",
                "xray_mgmt_disk": "/，89G / 97G，使用率 98%",
            },
        }
    )

    payload = map_unified_json_to_report_payload(unified_json, report_lang="zh-CN")

    assert payload.appendix["xray_issue_1_problem"] == "管理节点健康检查告警"
    assert payload.appendix["xray_issue_2_problem"] == "引擎节点健康检查告警"
    assert payload.appendix["xray_issue_3_problem"] == "管理节点磁盘使用率偏高"


def test_xray_payload_prefers_collected_at_for_inspection_date() -> None:
    unified_json = UnifiedJsonV1.model_validate(
        {
            "schema_version": "unified-json/v1",
            "task_id": "tsk_xray_payload_date",
            "generated_at": "2026-04-22T02:00:00Z",
            "host_info": {
                "hostname": "host-date",
            },
            "summary": {
                "overall_status": "healthy",
                "service_count": 0,
                "service_running_count": 0,
                "container_count": 0,
                "container_running_count": 0,
                "issue_count": 0,
                "issue_by_severity": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "info": 0,
                },
            },
            "services": [],
            "containers": [],
            "issues": [],
            "warnings": [],
            "metadata": {
                "product_type": "xray",
                "xray_collected_at": "2026-04-21T10:52:36Z",
            },
        }
    )

    payload = map_unified_json_to_report_payload(unified_json, report_lang="zh-CN")

    assert payload.appendix["xray_inspection_date"] == "2026年04月21日"
    assert payload.appendix["xray_inspection_date_iso"] == "2026-04-21"
    assert payload.appendix["xray_inspection_date_cn"] == "2026年04月21日"


def test_xray_template_exists_and_contains_expected_markers() -> None:
    template_path = Path(__file__).resolve().parents[1] / "templates" / "xray_inspection_report.docx"

    assert template_path.exists()
    assert template_path.suffix.lower() == ".docx"

    with ZipFile(template_path) as archive:
        assert archive.testzip() is None
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "{d.appendix.xray_executive_status}" not in document_xml
    assert "{d.appendix.xray_customer_name}" not in document_xml
    assert "{d.appendix.xray_inspection_date_cn}" in document_xml
    assert "{d.appendix.xray_cover_summary_1}" not in document_xml
    assert "{d.appendix.xray_cover_summary_2}" not in document_xml
    assert "{d.appendix.xray_runtime_status_result}" in document_xml
    assert "{d.appendix.xray_product_version}" in document_xml
    assert "{d.appendix.xray_time_sync_result}" not in document_xml
    assert "人工巡检项" not in document_xml
    assert "二、检查项" in document_xml
    assert "节点负载状态" in document_xml
    assert "CPU使用率" in document_xml
    assert "内存使用率" in document_xml
    assert "{d.container_rows[i].name}" in document_xml
    assert "{d.container_rows[i].cpu_percent}" in document_xml
    assert "{d.container_rows[i].memory_percent}" in document_xml
    assert "{d.container_rows[i+1].name}" in document_xml
    assert "{d.appendix.xray_key_alerts}" not in document_xml
    assert "{d.appendix.xray_llm_inspection_summary}" in document_xml
    assert "异常概览：" not in document_xml
    assert "重点告警：" not in document_xml
    assert "关键运行概况：" not in document_xml
    assert "（按风险优先级排序）" in document_xml
    assert "{d.appendix.xray_display_issue_1_problem_line}" in document_xml
    assert "{d.appendix.xray_display_issue_1_evidence_line}" in document_xml
    assert "{d.appendix.xray_display_issue_1_action_line}" in document_xml
    assert "{d.appendix.xray_display_issue_2_problem_line}" in document_xml
    assert "{d.appendix.xray_display_issue_2_evidence_line}" in document_xml
    assert "{d.appendix.xray_display_issue_2_action_line}" in document_xml
    assert "{d.appendix.xray_display_issue_3_problem_line}" in document_xml
    assert "{d.appendix.xray_display_issue_3_evidence_line}" in document_xml
    assert "{d.appendix.xray_display_issue_3_action_line}" in document_xml
