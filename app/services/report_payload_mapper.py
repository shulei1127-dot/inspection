import re
from dataclasses import dataclass
from pathlib import Path

from app.schemas.report_payload import (
    ContainerRow,
    IssueRow,
    ReportHost,
    ReportMeta,
    ReportPayloadV1,
    ReportSummary,
    ServiceRow,
)
from app.schemas.unified_json import (
    UnifiedJsonContainer,
    UnifiedJsonIssue,
    UnifiedJsonService,
    UnifiedJsonV1,
)


OVERALL_STATUS_LABELS = {
    "healthy": "Healthy",
    "warning": "Warning",
    "critical": "Critical",
    "unknown": "Unknown",
}

XRAY_OVERALL_STATUS_LABELS = {
    "healthy": "健康",
    "warning": "告警",
    "critical": "严重",
    "unknown": "未知",
}

RUNTIME_STATUS_LABELS = {
    "running": "Running",
    "stopped": "Stopped",
    "failed": "Failed",
    "unknown": "Unknown",
}

XRAY_RUNTIME_STATUS_LABELS = {
    "running": "运行中",
    "stopped": "已停止",
    "failed": "失败",
    "unknown": "未知",
}

ISSUE_SEVERITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Info",
}

ISSUE_SEVERITY_PRIORITY = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}

XRAY_PRIORITY_RULES = {
    "health_alert": 400,
    "resource_critical": 350,
    "runtime_critical": 300,
    "runtime_warning": 200,
    "resource_risk": 100,
    "resource_alert": 250,
    "other": 0,
}

XRAY_RESOURCE_ALERT_THRESHOLDS = {
    "cpu": 80.0,
    "memory": 85.0,
    "disk": 85.0,
}


@dataclass(frozen=True)
class XrayObservation:
    title: str
    evidence: str
    recommendation: str
    priority: int
    summary: str


@dataclass(frozen=True)
class XrayIssueContext:
    issue_rows: list[IssueRow]
    observations: list[XrayObservation]


def map_unified_json_to_report_payload(
    unified_json: UnifiedJsonV1,
    *,
    report_lang: str = "zh-CN",
) -> ReportPayloadV1:
    is_xray = _is_xray_product(unified_json)
    host_os = _join_parts(
        [
            unified_json.host_info.os_name,
            unified_json.host_info.os_version,
        ]
    )
    xray_context = _build_xray_issue_context(unified_json)
    issue_rows = (
        xray_context.issue_rows
        if xray_context is not None
        else _build_default_issue_rows(unified_json)
    )
    highlights = _build_highlights(unified_json, xray_context=xray_context)
    recommendations = _build_recommendations(
        unified_json,
        issue_rows=issue_rows,
        xray_context=xray_context,
    )
    appendix = _build_appendix(
        unified_json,
        recommendations=recommendations,
        issue_rows=issue_rows,
        xray_context=xray_context,
    )

    return ReportPayloadV1(
        payload_version="report-payload/v1",
        report=ReportMeta(
            title="洞鉴巡检报告" if is_xray else "Inspection Report",
            generated_at=unified_json.generated_at,
            task_id=unified_json.task_id,
            report_lang=report_lang,
        ),
        host=ReportHost(
            hostname=unified_json.host_info.hostname,
            ip=unified_json.host_info.ip,
            os=host_os,
            kernel_version=unified_json.host_info.kernel_version,
            timezone=unified_json.host_info.timezone,
        ),
        summary=ReportSummary(
            overall_status=unified_json.summary.overall_status,
            overall_status_label=(
                XRAY_OVERALL_STATUS_LABELS[unified_json.summary.overall_status]
                if is_xray
                else OVERALL_STATUS_LABELS[unified_json.summary.overall_status]
            ),
            service_count=unified_json.summary.service_count,
            service_running_count=unified_json.summary.service_running_count,
            container_count=unified_json.summary.container_count,
            container_running_count=unified_json.summary.container_running_count,
            issue_count=unified_json.summary.issue_count,
        ),
        service_rows=[
            ServiceRow(
                name=service.display_name or service.name,
                status=service.status,
                status_label=(
                    XRAY_RUNTIME_STATUS_LABELS[service.status]
                    if is_xray
                    else RUNTIME_STATUS_LABELS[service.status]
                ),
                enabled=_format_bool(service.enabled, zh=is_xray),
                version=service.version or "-",
                ports=", ".join(str(port) for port in service.listen_ports) or "-",
                notes=service.notes or "-",
            )
            for service in unified_json.services
        ],
        container_rows=[
            ContainerRow(
                name=container.name,
                image=container.image or "-",
                status=container.status,
                status_label=(
                    XRAY_RUNTIME_STATUS_LABELS[container.status]
                    if is_xray
                    else RUNTIME_STATUS_LABELS[container.status]
                ),
                cpu_percent=_format_optional_percent(container.cpu_percent),
                memory_percent=_format_optional_percent(container.memory_percent),
                ports=", ".join(container.ports) or "-",
                notes=container.notes or "-",
            )
            for container in unified_json.containers
        ],
        issue_rows=issue_rows,
        highlights=highlights,
        recommendations=recommendations,
        appendix=appendix,
    )


def persist_report_payload(report_payload: ReportPayloadV1, target_path: Path) -> None:
    target_path.write_text(
        report_payload.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _format_bool(value: bool | None, *, zh: bool = False) -> str:
    if value is None:
        return "-"
    if zh:
        return "是" if value else "否"
    return "Yes" if value else "No"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:.2f}".rstrip("0").rstrip(".") + "%"


def _join_parts(parts: list[str | None]) -> str | None:
    values = [part for part in parts if part]
    if not values:
        return None
    return " ".join(values)


def _build_highlights(
    unified_json: UnifiedJsonV1,
    *,
    xray_context: XrayIssueContext | None,
) -> list[str]:
    if xray_context is not None:
        highlights = [
            _build_xray_executive_status(unified_json, xray_context),
            _build_xray_runtime_overview(unified_json),
        ]
        if xray_context.observations:
            highlights.append(f"最高优先级问题：{xray_context.observations[0].title}")
        return highlights

    return [
        f"Upload task {unified_json.task_id} completed and unified JSON was generated.",
    ]


def _build_recommendations(
    unified_json: UnifiedJsonV1,
    *,
    issue_rows: list[IssueRow],
    xray_context: XrayIssueContext | None,
) -> list[str]:
    if xray_context is not None and xray_context.observations:
        deduped = list(
            dict.fromkeys(
                observation.recommendation
                for observation in xray_context.observations
                if observation.recommendation and observation.recommendation != "-"
            )
        )
        if deduped:
            return deduped

    if _is_xray_product(unified_json):
        deduped_recommendations = list(
            dict.fromkeys(
                issue_row.suggestion.strip()
                for issue_row in issue_rows
                if issue_row.suggestion and issue_row.suggestion.strip() != "-"
            )
        )
        if deduped_recommendations:
            return deduped_recommendations

    parser_name = unified_json.parser.name if unified_json.parser else "unknown-parser"
    return [
        f"Review results produced by {parser_name} and continue expanding parser coverage for additional log types.",
    ]


def _build_appendix(
    unified_json: UnifiedJsonV1,
    *,
    recommendations: list[str],
    issue_rows: list[IssueRow],
    xray_context: XrayIssueContext | None,
) -> dict[str, str | int | float | bool | None]:
    parser_name = unified_json.parser.name if unified_json.parser else None
    parser_version = unified_json.parser.version if unified_json.parser else None

    appendix: dict[str, str | int | float | bool | None] = {
        "parser_name": parser_name,
        "parser_version": parser_version,
    }

    if "extracted_file_count" in unified_json.metadata:
        appendix["extracted_file_count"] = unified_json.metadata["extracted_file_count"]

    if xray_context is not None:
        appendix.update(
            _build_xray_appendix(
                unified_json,
                recommendations=recommendations,
                issue_rows=issue_rows,
                xray_context=xray_context,
            )
        )

    return appendix


def _build_xray_appendix(
    unified_json: UnifiedJsonV1,
    *,
    recommendations: list[str],
    issue_rows: list[IssueRow],
    xray_context: XrayIssueContext,
) -> dict[str, str | int | float | bool | None]:
    metadata = unified_json.metadata
    service_issues = [issue for issue in unified_json.issues if issue.category == "service"]
    container_issues = [issue for issue in unified_json.issues if issue.category == "container"]
    minion_service = next((service for service in unified_json.services if service.name == "minion"), None)
    failed_services = [service.name for service in unified_json.services if service.status == "failed"]
    non_running_containers = [
        container.name
        for container in unified_json.containers
        if container.status != "running"
    ]
    primary_observation = xray_context.observations[0] if xray_context.observations else None
    top_observations = list(xray_context.observations[:3])

    service_status_result = "正常" if not service_issues and unified_json.summary.service_count else (
        "告警" if service_issues else "-"
    )
    container_status_result = "正常" if not container_issues and unified_json.summary.container_count else (
        "告警" if container_issues else "-"
    )

    service_status_note = (
        f"运行 {unified_json.summary.service_running_count} / {unified_json.summary.service_count}"
        if unified_json.summary.service_count
        else "-"
    )
    if failed_services:
        service_status_note += f"，失败服务：{', '.join(failed_services)}"

    container_status_note = (
        f"运行 {unified_json.summary.container_running_count} / {unified_json.summary.container_count}"
        if unified_json.summary.container_count
        else "-"
    )
    if non_running_containers:
        container_status_note += f"，非运行容器：{', '.join(non_running_containers[:5])}"

    minion_log_result = (
        _metadata_text(metadata, "xray_minion_log_result")
        or ("正常" if minion_service and minion_service.status == "running" else "-")
    )
    minion_log_note = (
        _metadata_text(metadata, "xray_minion_log_note")
        or (f"minion 服务状态：{minion_service.status}" if minion_service else "-")
    )

    runtime_status_result = (
        "告警"
        if any(
            value == "告警"
            for value in [minion_log_result, container_status_result, service_status_result]
        )
        else ("正常" if unified_json.summary.service_count or unified_json.summary.container_count else "-")
    )
    runtime_status_note = _build_xray_runtime_status_note(
        minion_log_note=minion_log_note,
        container_status_note=container_status_note,
        service_status_note=service_status_note,
    )
    executive_status = _build_xray_executive_status(unified_json, xray_context)
    runtime_overview = _build_xray_runtime_overview(unified_json)
    key_alerts = _build_xray_key_alerts(xray_context)
    primary_problem = primary_observation.title if primary_observation else "当前未识别到高优先级异常"
    overall_overview = (
        f"{executive_status}。最高优先级问题为：{primary_problem}。"
        f"关键运行概况：{runtime_overview}。"
    )
    result_conclusion = (
        f"{executive_status}；当前首要处理项为“{primary_problem}”。"
        f"重点关注：{key_alerts}"
    )
    xray_deployment_mode = _metadata_text(metadata, "xray_deployment_mode")
    if xray_deployment_mode == "-":
        xray_deployment_mode = "single_node"
    is_single_node_deployment = xray_deployment_mode == "single_node"
    mgmt_cpu = _metadata_text(metadata, "xray_mgmt_cpu")
    mgmt_memory = _metadata_text(metadata, "xray_mgmt_memory")
    mgmt_disk = _metadata_text(metadata, "xray_mgmt_disk")

    return {
        "xray_customer_name": "-",
        "xray_project_name": "-",
        "xray_cover_summary_1": (
            f"主机：{unified_json.host_info.hostname}    "
            f"IP：{unified_json.host_info.ip or '-'}"
        ),
        "xray_cover_summary_2": (
            f"{executive_status}；最高风险：{primary_problem}；"
            f"{runtime_overview}"
        ),
        "xray_inspected_host_count": 1,
        "xray_executive_status": executive_status,
        "xray_overall_overview": overall_overview,
        "xray_node_info": _build_xray_node_info(unified_json),
        "xray_product_version": _metadata_text(metadata, "xray_product_version"),
        "xray_engine_version": _metadata_text(metadata, "xray_engine_version"),
        "xray_vuln_db_version": _metadata_text(metadata, "xray_vuln_db_version"),
        "xray_machine_id": _metadata_text(metadata, "xray_machine_id"),
        "xray_license_validity": _metadata_text(metadata, "xray_license_validity"),
        "xray_mgmt_health_result": _metadata_text(metadata, "xray_mgmt_health_result"),
        "xray_mgmt_health_note": _metadata_text(metadata, "xray_mgmt_health_note"),
        "xray_engine_health_result": _metadata_text(metadata, "xray_engine_health_result"),
        "xray_engine_health_note": _metadata_text(metadata, "xray_engine_health_note"),
        "xray_time_sync_result": "需人工验证",
        "xray_time_sync_note": "当前日志未提供跨节点时间同步的直接证据，需现场核验。",
        "xray_scan_task_result": "需人工验证",
        "xray_scan_task_note": "需在产品任务链路中手工创建测试任务后确认。",
        "xray_report_generation_result": "需人工验证",
        "xray_report_generation_note": "需在产品界面或导出链路中手工验证报表生成结果。",
        "xray_minion_log_result": minion_log_result,
        "xray_minion_log_note": minion_log_note,
        "xray_runtime_status_result": runtime_status_result,
        "xray_runtime_status_note": runtime_status_note,
        "xray_container_status_result": container_status_result,
        "xray_container_status_note": container_status_note,
        "xray_service_status_result": service_status_result,
        "xray_service_status_note": service_status_note,
        "xray_mgmt_node_ip": (
            _metadata_text(metadata, "xray_mgmt_node_ip") or unified_json.host_info.ip or "-"
        ),
        "xray_engine_node_ip": (
            _metadata_text(metadata, "xray_engine_node_ip") or unified_json.host_info.ip or "-"
        ),
        "xray_mgmt_node_health": _metadata_text(metadata, "xray_mgmt_node_health"),
        "xray_mgmt_cpu": mgmt_cpu,
        "xray_mgmt_memory": mgmt_memory,
        "xray_mgmt_disk": mgmt_disk,
        "xray_engine_node_health": _metadata_text(metadata, "xray_engine_node_health"),
        "xray_engine_cpu": _xray_engine_resource_value(
            metadata,
            "xray_engine_cpu",
            mgmt_cpu,
            single_node=is_single_node_deployment,
        ),
        "xray_engine_memory": _xray_engine_resource_value(
            metadata,
            "xray_engine_memory",
            mgmt_memory,
            single_node=is_single_node_deployment,
        ),
        "xray_engine_service_status": service_status_result,
        "xray_engine_disk": _xray_engine_resource_value(
            metadata,
            "xray_engine_disk",
            mgmt_disk,
            single_node=is_single_node_deployment,
        ),
        "xray_deployment_mode": xray_deployment_mode,
        "xray_result_conclusion": result_conclusion,
        "xray_llm_inspection_summary": result_conclusion,
        "xray_llm_exception_summary": key_alerts,
        "xray_llm_disposal_advice": "；".join(recommendations[:3]) if recommendations else "-",
        "xray_primary_problem": primary_problem,
        "xray_key_alerts": key_alerts,
        "xray_key_runtime_overview": runtime_overview,
        "xray_primary_note": primary_observation.evidence if primary_observation else "-",
        "xray_primary_recommendation": (
            primary_observation.recommendation
            if primary_observation is not None
            else (recommendations[0] if recommendations else "-")
        ),
        "xray_issue_1_problem": _observation_value(top_observations, 0, "title"),
        "xray_issue_1_evidence": _observation_value(top_observations, 0, "evidence"),
        "xray_issue_1_recommendation": _observation_value(top_observations, 0, "recommendation"),
        "xray_issue_2_problem": _observation_value(top_observations, 1, "title"),
        "xray_issue_2_evidence": _observation_value(top_observations, 1, "evidence"),
        "xray_issue_2_recommendation": _observation_value(top_observations, 1, "recommendation"),
        "xray_issue_3_problem": _observation_value(top_observations, 2, "title"),
        "xray_issue_3_evidence": _observation_value(top_observations, 2, "evidence"),
        "xray_issue_3_recommendation": _observation_value(top_observations, 2, "recommendation"),
        "xray_inspector_name": "-",
        "xray_inspection_date": _format_chinese_date(_xray_report_date(unified_json)),
        "xray_inspection_date_iso": _xray_report_date(unified_json),
        "xray_inspection_date_cn": _format_chinese_date(_xray_report_date(unified_json)),
    }


def _build_default_issue_rows(unified_json: UnifiedJsonV1) -> list[IssueRow]:
    return [
        IssueRow(
            id=issue.id,
            severity=issue.severity,
            severity_label=ISSUE_SEVERITY_LABELS[issue.severity],
            category=issue.category,
            title=issue.title,
            description=issue.description or "-",
            suggestion=issue.suggestion or "-",
        )
        for issue in unified_json.issues
    ]


def _build_xray_issue_context(unified_json: UnifiedJsonV1) -> XrayIssueContext | None:
    if not _is_xray_product(unified_json):
        return None

    issue_rows = sorted(
        [_build_xray_issue_row(issue, unified_json) for issue in unified_json.issues],
        key=lambda row: (_build_xray_issue_priority(row), ISSUE_SEVERITY_PRIORITY[row.severity]),
        reverse=True,
    )
    observations = sorted(
        _build_xray_observations(unified_json, issue_rows=issue_rows),
        key=lambda observation: (observation.priority, observation.title),
        reverse=True,
    )
    return XrayIssueContext(issue_rows=issue_rows, observations=observations)


def _build_xray_issue_row(
    issue: UnifiedJsonIssue,
    unified_json: UnifiedJsonV1,
) -> IssueRow:
    return IssueRow(
        id=issue.id,
        severity=issue.severity,
        severity_label=ISSUE_SEVERITY_LABELS[issue.severity],
        category=issue.category,
        title=_build_xray_issue_title(issue, unified_json),
        description=_build_xray_issue_evidence(issue, unified_json),
        suggestion=_build_xray_issue_suggestion(issue, unified_json),
    )


def _build_xray_issue_title(
    issue: UnifiedJsonIssue,
    unified_json: UnifiedJsonV1,
) -> str:
    if issue.category == "container":
        container = _find_container(unified_json, issue.related_object_name)
        name = issue.related_object_name or (container.name if container else _extract_issue_object_name(issue))
        if name:
            source_text = f"{issue.id} {issue.title}".lower()
            if "restarting" in source_text:
                return f"容器 {name} 正在反复重启"
            if "stopped" in source_text or "exited" in source_text:
                return f"容器 {name} 已停止"
            if container is not None and container.status == "failed":
                return f"容器 {name} 状态异常"
            return f"容器 {name} 需要关注"

    if issue.category == "service":
        service = _find_service(unified_json, issue.related_object_name)
        name = issue.related_object_name or (service.name if service else _extract_issue_object_name(issue))
        if name:
            if (service is not None and service.status == "failed") or "failed" in issue.title.lower():
                return f"服务 {name} 运行失败"
            return f"服务 {name} 状态异常"

    return issue.title


def _build_xray_issue_suggestion(
    issue: UnifiedJsonIssue,
    unified_json: UnifiedJsonV1,
) -> str:
    if issue.category == "container":
        container = _find_container(unified_json, issue.related_object_name)
        name = issue.related_object_name or (container.name if container else _extract_issue_object_name(issue) or "相关容器")
        return f"检查 {name} 容器日志、重启策略和依赖组件状态，确认异常退出或反复重启原因。"

    if issue.category == "service":
        service = _find_service(unified_json, issue.related_object_name)
        name = issue.related_object_name or (service.name if service else _extract_issue_object_name(issue) or "相关服务")
        return f"检查 {name} 的 systemd 状态、最近日志和依赖组件，恢复服务到正常运行状态。"

    if issue.category == "host":
        return "补充采集主机基础信息，并结合现场状态确认该项是否影响巡检结论。"

    return issue.suggestion or "-"


def _build_xray_issue_evidence(
    issue: UnifiedJsonIssue,
    unified_json: UnifiedJsonV1,
) -> str:
    if issue.category == "container":
        container = _find_container(unified_json, issue.related_object_name) or _guess_container(
            unified_json,
            issue,
        )
        if container is not None:
            parts = [
                f"容器 {container.name} 当前状态为 {XRAY_RUNTIME_STATUS_LABELS[container.status]}",
            ]
            if container.notes:
                parts.append(f"运行证据：{container.notes}")
            if container.image:
                parts.append(f"镜像：{container.image}")
            if container.ports:
                parts.append(f"端口：{', '.join(container.ports)}")
            return "；".join(parts) + "。"

    if issue.category == "service":
        service = _find_service(unified_json, issue.related_object_name) or _guess_service(
            unified_json,
            issue,
        )
        if service is not None:
            parts = [
                f"服务 {service.display_name or service.name} 当前状态为 {XRAY_RUNTIME_STATUS_LABELS[service.status]}",
            ]
            if service.notes:
                parts.append(f"运行证据：{service.notes}")
            if service.enabled is not None:
                parts.append(f"开机启动：{'是' if service.enabled else '否'}")
            return "；".join(parts) + "。"

    if issue.category == "host":
        parts = [issue.description or "主机信息存在需关注项。"]
        if unified_json.host_info.hostname:
            parts.append(f"主机：{unified_json.host_info.hostname}")
        if unified_json.host_info.kernel_version:
            parts.append(f"内核：{unified_json.host_info.kernel_version}")
        if unified_json.host_info.timezone:
            parts.append(f"时区：{unified_json.host_info.timezone}")
        return "；".join(part.strip("。") for part in parts if part) + "。"

    return issue.description or "-"


def _extract_issue_object_name(issue: UnifiedJsonIssue) -> str | None:
    patterns = [
        r"\b(?:Container|Service)\s+([A-Za-z0-9_.:@-]+)",
        r"\b(container|service)-([A-Za-z0-9_.:@-]+?)-(?:failed|stopped|restarting|inactive|unhealthy)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, f"{issue.id} {issue.title}", flags=re.IGNORECASE)
        if not match:
            continue
        return match.group(match.lastindex or 1)
    return None


def _build_xray_observations(
    unified_json: UnifiedJsonV1,
    *,
    issue_rows: list[IssueRow],
) -> list[XrayObservation]:
    metadata = unified_json.metadata
    observations = [
        XrayObservation(
            title=issue_row.title,
            evidence=issue_row.description,
            recommendation=issue_row.suggestion,
            priority=_build_xray_issue_priority(issue_row),
            summary=issue_row.title,
        )
        for issue_row in issue_rows
    ]

    for observation in [
        _build_xray_health_observation(
            "管理节点健康检查告警",
            _metadata_text(metadata, "xray_mgmt_health_result"),
            _metadata_text(metadata, "xray_mgmt_health_note"),
            "优先核查 ./minion mgmt health 返回的失败项，并恢复对应管理节点组件。",
        ),
        _build_xray_health_observation(
            "引擎节点健康检查告警",
            _metadata_text(metadata, "xray_engine_health_result"),
            _metadata_text(metadata, "xray_engine_health_note"),
            "优先核查 ./minion engine health 返回的失败项，并恢复对应引擎节点组件。",
        ),
        _build_xray_resource_observation(
            "管理节点 CPU 使用率偏高",
            _metadata_text(metadata, "xray_mgmt_cpu"),
            metric="cpu",
        ),
        _build_xray_resource_observation(
            "引擎节点 CPU 使用率偏高",
            _metadata_text(metadata, "xray_engine_cpu"),
            metric="cpu",
        ),
        _build_xray_resource_observation(
            "管理节点内存使用率偏高",
            _metadata_text(metadata, "xray_mgmt_memory"),
            metric="memory",
        ),
        _build_xray_resource_observation(
            "引擎节点内存使用率偏高",
            _metadata_text(metadata, "xray_engine_memory"),
            metric="memory",
        ),
        _build_xray_resource_observation(
            "管理节点磁盘使用率偏高",
            _metadata_text(metadata, "xray_mgmt_disk"),
            metric="disk",
        ),
        _build_xray_resource_observation(
            "引擎节点磁盘使用率偏高",
            _metadata_text(metadata, "xray_engine_disk"),
            metric="disk",
        ),
    ]:
        if observation is not None:
            observations.append(observation)

    deduped: list[XrayObservation] = []
    seen_titles: set[str] = set()
    for observation in observations:
        if observation.title in seen_titles:
            continue
        deduped.append(observation)
        seen_titles.add(observation.title)
    return deduped


def _build_xray_health_observation(
    title: str,
    result: str,
    note: str,
    recommendation: str,
) -> XrayObservation | None:
    if result != "告警":
        return None

    evidence = note if note != "-" else "健康检查返回告警结果。"
    return XrayObservation(
        title=title,
        evidence=evidence,
        recommendation=recommendation,
        priority=XRAY_PRIORITY_RULES["health_alert"],
        summary=f"{title}（{evidence}）",
    )


def _build_xray_resource_observation(
    title: str,
    raw_value: str,
    *,
    metric: str,
) -> XrayObservation | None:
    if raw_value == "-":
        return None

    usage = _extract_percent(raw_value)
    threshold = XRAY_RESOURCE_ALERT_THRESHOLDS.get(metric)
    if usage is None or threshold is None or usage < threshold:
        return None

    return XrayObservation(
        title=title,
        evidence=f"日志摘要显示：{raw_value}",
        recommendation="结合节点资源趋势和业务负载，尽快评估清理、扩容或限流措施。",
        priority=_build_xray_resource_priority(metric=metric, usage=usage),
        summary=f"{title}（{usage:.2f}%）",
    )


def _build_xray_resource_priority(*, metric: str, usage: float) -> int:
    if metric == "disk" and usage >= 95:
        return XRAY_PRIORITY_RULES["resource_critical"]
    if metric in {"cpu", "memory"} and usage >= 95:
        return XRAY_PRIORITY_RULES["resource_critical"]
    return XRAY_PRIORITY_RULES["resource_alert"]


def _build_xray_issue_priority(issue_row: IssueRow) -> int:
    text = " ".join(
        [
            issue_row.id,
            issue_row.title,
            issue_row.description,
            issue_row.suggestion,
        ]
    ).lower()

    if any(keyword in text for keyword in ("restarting", "unhealthy", "failed health")):
        return XRAY_PRIORITY_RULES["runtime_critical"]
    if any(keyword in text for keyword in ("non-running", "failed", "inactive", "stopped", "exited")):
        return XRAY_PRIORITY_RULES["runtime_warning"]
    if any(keyword in text for keyword in ("disk", "memory")):
        return XRAY_PRIORITY_RULES["resource_risk"]
    return XRAY_PRIORITY_RULES["other"]


def _build_xray_executive_status(
    unified_json: UnifiedJsonV1,
    xray_context: XrayIssueContext,
) -> str:
    if xray_context.observations:
        return "整体状态为告警，存在需要优先处理的运行风险"
    if unified_json.summary.service_count or unified_json.summary.container_count:
        return "整体状态基本稳定，日志自动检查未发现高优先级异常"
    return "当前日志数据有限，整体状态需结合人工巡检进一步确认"


def _build_xray_runtime_overview(unified_json: UnifiedJsonV1) -> str:
    return (
        f"服务 {unified_json.summary.service_running_count}/{unified_json.summary.service_count} 运行，"
        f"容器 {unified_json.summary.container_running_count}/{unified_json.summary.container_count} 运行"
    )


def _build_xray_key_alerts(xray_context: XrayIssueContext) -> str:
    if not xray_context.observations:
        return "当前未识别到需要前置关注的关键告警项"

    return "；".join(observation.summary for observation in xray_context.observations[:3])


def _build_xray_runtime_status_note(
    *,
    minion_log_note: str,
    container_status_note: str,
    service_status_note: str,
) -> str:
    return "；".join(
        note
        for note in [minion_log_note, container_status_note, service_status_note]
        if note and note != "-"
    ) or "-"


def _find_container(
    unified_json: UnifiedJsonV1,
    related_object_name: str | None,
) -> UnifiedJsonContainer | None:
    if not related_object_name:
        return None
    return next(
        (container for container in unified_json.containers if container.name == related_object_name),
        None,
    )


def _find_service(
    unified_json: UnifiedJsonV1,
    related_object_name: str | None,
) -> UnifiedJsonService | None:
    if not related_object_name:
        return None
    return next(
        (service for service in unified_json.services if service.name == related_object_name),
        None,
    )


def _guess_container(
    unified_json: UnifiedJsonV1,
    issue: UnifiedJsonIssue,
) -> UnifiedJsonContainer | None:
    haystack = " ".join(
        [
            issue.id,
            issue.title,
            issue.description or "",
        ]
    ).lower()
    return next(
        (container for container in unified_json.containers if container.name.lower() in haystack),
        None,
    )


def _guess_service(
    unified_json: UnifiedJsonV1,
    issue: UnifiedJsonIssue,
) -> UnifiedJsonService | None:
    haystack = " ".join(
        [
            issue.id,
            issue.title,
            issue.description or "",
        ]
    ).lower()
    return next(
        (
            service
            for service in unified_json.services
            if service.name.lower() in haystack
            or (
                service.display_name is not None
                and service.display_name.lower() in haystack
            )
        ),
        None,
    )


def _extract_percent(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)%", value)
    if not match:
        return None
    return float(match.group(1))


def _issue_row_value(issue_rows: list[IssueRow], index: int, field_name: str) -> str:
    if index >= len(issue_rows):
        return "-"
    return str(getattr(issue_rows[index], field_name) or "-")


def _observation_value(
    observations: list[XrayObservation],
    index: int,
    field_name: str,
) -> str:
    if index >= len(observations):
        return "-"
    return str(getattr(observations[index], field_name) or "-")


def _build_xray_node_info(unified_json: UnifiedJsonV1) -> str:
    mgmt_ip = _metadata_text(unified_json.metadata, "xray_mgmt_node_ip")
    engine_ip = _metadata_text(unified_json.metadata, "xray_engine_node_ip")
    if mgmt_ip != "-" or engine_ip != "-":
        return f"管理节点 IP：{mgmt_ip}；引擎节点 IP：{engine_ip}"
    if unified_json.host_info.hostname or unified_json.host_info.ip:
        return (
            f"主机：{unified_json.host_info.hostname or '-'}；"
            f"IP：{unified_json.host_info.ip or '-'}"
        )
    return "-"


def _is_xray_product(unified_json: UnifiedJsonV1) -> bool:
    return str(unified_json.metadata.get("product_type")).strip().lower() == "xray"


def _metadata_text(
    metadata: dict[str, str | int | float | bool | None],
    key: str,
) -> str:
    value = metadata.get(key)
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value).strip()
    return text or "-"


def _xray_engine_resource_value(
    metadata: dict[str, str | int | float | bool | None],
    key: str,
    mgmt_value: str,
    *,
    single_node: bool,
) -> str:
    explicit_value = _metadata_text(metadata, key)
    if explicit_value != "-":
        return explicit_value
    if single_node and mgmt_value != "-":
        return mgmt_value
    return "-"


def _format_chinese_date(date_value: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_value.strip())
    if not match:
        return date_value
    return f"{match.group(1)}年{match.group(2)}月{match.group(3)}日"


def _xray_report_date(unified_json: UnifiedJsonV1) -> str:
    collected_at = unified_json.metadata.get("xray_collected_at")
    if collected_at is not None:
        match = re.search(r"(^|\D)(\d{4}-\d{2}-\d{2})(?=\D|$)", str(collected_at))
        if match:
            return match.group(2)
    return unified_json.generated_at.split("T", 1)[0]
