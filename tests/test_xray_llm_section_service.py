import json

import httpx

from app.schemas.report_payload import ReportPayloadV1
from app.schemas.unified_json import UnifiedJsonV1
from app.services.report_payload_mapper import map_unified_json_to_report_payload
from app.services.xray_llm_section_service import (
    RemoteXrayLlmSectionService,
    maybe_apply_xray_llm_sections,
)


def test_xray_llm_section_service_overrides_summary_and_issue_actions() -> None:
    unified_json = _build_xray_unified_json()
    report_payload = map_unified_json_to_report_payload(unified_json, report_lang="zh-CN")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read().decode("utf-8"))
        assert payload["model"] == "glm-5.1"
        assert payload["messages"][1]["content"].find("输入事实 JSON") != -1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "inspection_summary": "当前 x-ray 系统已识别到健康检查异常与磁盘空间压力，建议优先处理管理侧与引擎侧失败项，并尽快排查高磁盘占用来源。",
                                    "exception_summary": "当前主要异常集中在节点健康检查失败和管理节点磁盘使用率过高两方面，已对系统稳定运行形成直接风险。",
                                    "exception_actions": [
                                        {
                                            "problem": "管理节点健康检查返回异常",
                                            "action": "建议复核 ./minion mgmt health 的失败项，并检查管理节点相关组件与依赖服务状态。",
                                        },
                                        {
                                            "problem": "引擎节点健康检查存在 Redis 端口异常",
                                            "action": "建议核查 ./minion engine health 结果，并重点检查 Redis 相关进程、端口连通性及容器日志。",
                                        },
                                        {
                                            "problem": "管理节点磁盘使用率达到 98%",
                                            "action": "建议尽快排查磁盘占用来源，必要时清理无效数据或评估扩容，避免影响后续运行与日志写入。",
                                        },
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    service = RemoteXrayLlmSectionService(
        base_url="http://llm.local/v1",
        api_key="secret",
        model="glm-5.1",
        timeout_seconds=5,
        temperature=0.2,
        transport=httpx.MockTransport(handler),
    )

    result = maybe_apply_xray_llm_sections(
        report_payload,
        unified_json=unified_json,
        service=service,
    )

    assert result.success is True
    assert report_payload.appendix["xray_llm_status"] == "ok"
    assert report_payload.appendix["xray_result_conclusion"] == report_payload.appendix["xray_llm_inspection_summary"]
    assert report_payload.appendix["xray_issue_1_problem"] == "管理节点健康检查返回异常"
    assert report_payload.appendix["xray_issue_2_problem"] == "引擎节点健康检查存在 Redis 端口异常"
    assert report_payload.appendix["xray_issue_3_problem"] == "管理节点磁盘使用率达到 98%"
    assert report_payload.appendix["xray_display_issue_1_problem_line"] == "问题 1：管理节点健康检查返回异常"
    assert report_payload.appendix["xray_display_issue_1_evidence_line"] == "证据：失败项：HEALTH COMMAND ERROR"
    assert report_payload.appendix["xray_display_issue_3_action_line"].startswith("建议：")
    assert report_payload.appendix["xray_issue_1_evidence"] == "失败项：HEALTH COMMAND ERROR"
    assert report_payload.appendix["xray_mgmt_disk"] == "/，89G / 97G，使用率 98%"


def test_xray_llm_section_service_falls_back_on_invalid_output() -> None:
    unified_json = _build_xray_unified_json()
    report_payload = map_unified_json_to_report_payload(unified_json, report_lang="zh-CN")
    original_summary = report_payload.appendix["xray_result_conclusion"]
    original_problem = report_payload.appendix["xray_issue_1_problem"]

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    service = RemoteXrayLlmSectionService(
        base_url="http://llm.local/v1",
        api_key="secret",
        model="glm-5.1",
        timeout_seconds=5,
        temperature=0.2,
        transport=httpx.MockTransport(handler),
    )

    result = maybe_apply_xray_llm_sections(
        report_payload,
        unified_json=unified_json,
        service=service,
    )

    assert result.success is False
    assert result.status == "invalid_output"
    assert report_payload.appendix["xray_result_conclusion"] == original_summary
    assert report_payload.appendix["xray_issue_1_problem"] == original_problem
    assert report_payload.appendix["xray_llm_status"] == "invalid_output"
    assert report_payload.appendix["xray_display_issue_3_problem_line"] == "问题 3：管理节点磁盘使用率偏高"


def _build_xray_unified_json() -> UnifiedJsonV1:
    return UnifiedJsonV1.model_validate(
        {
            "schema_version": "unified-json/v1",
            "task_id": "tsk_xray_llm_001",
            "generated_at": "2026-04-27T10:00:00Z",
            "host_info": {
                "hostname": "host-a",
                "ip": "10.20.20.208",
            },
            "summary": {
                "overall_status": "warning",
                "service_count": 1,
                "service_running_count": 1,
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
                    "name": "xray-redis",
                    "status": "failed",
                    "notes": "docker status: Restarting (1) 10 seconds ago",
                }
            ],
            "issues": [
                {
                    "id": "container-xray-redis-restarting",
                    "severity": "medium",
                    "category": "container",
                    "related_object_name": "xray-redis",
                    "title": "Container xray-redis is restarting",
                    "description": "docker status: Restarting (1) 10 seconds ago",
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
                "xray_mgmt_cpu": "8 cores / Intel Xeon / 当前使用率 4.4%",
                "xray_mgmt_memory": "总量 15987M，已用 4813M (30.1%)",
                "xray_mgmt_disk": "/，89G / 97G，使用率 98%",
            },
        }
    )
