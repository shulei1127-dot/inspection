from __future__ import annotations

from dataclasses import dataclass

from app.schemas.audit_result import AuditResultV1, ClaimReviewResult
from app.schemas.log_evidence import LogEvidenceV1, LogFinding, ResourceSignal, RuntimeComponentEvidence


@dataclass(frozen=True)
class ContainerAuditRow:
    container_name: str
    status_label: str
    cpu_usage: str
    memory_usage: str
    risk_summary: str
    suggestion: str


def render_audit_opinion_markdown(
    audit_result: AuditResultV1,
    log_evidence: LogEvidenceV1 | None = None,
) -> str:
    lines = [
        "# 雷池 WAF 巡检报告审核意见单",
        "",
        "本意见单以人工巡检报告为主对象，日志作为资源状态与容器运行情况的辅助核验证据。",
    ]
    for title, rows in build_audit_opinion_sections(audit_result, log_evidence=log_evidence):
        lines.extend(["", f"## {title}"])
        lines.extend(rows)
    lines.append("")
    return "\n".join(lines)


def build_audit_opinion_sections(
    audit_result: AuditResultV1,
    *,
    log_evidence: LogEvidenceV1 | None = None,
) -> list[tuple[str, list[str]]]:
    return [
        ("总体审核结论", [audit_result.summary.overall_conclusion]),
        ("资源使用率核验", _render_resource_section(audit_result)),
        ("容器运行状况核验", _render_container_section(log_evidence)),
        ("仍需人工判断", _render_manual_section(audit_result)),
        ("建议修订", _render_revisions(audit_result)),
    ]


def _render_resource_section(audit_result: AuditResultV1) -> list[str]:
    metric_order = {"cpu": 0, "memory": 1, "disk": 2}
    rows = [
        result
        for result in audit_result.claim_results
        if result.claim_type == "resource_usage_assessment"
    ]
    if not rows:
        return ["- 未从报告中抽取到 CPU / 内存 / 磁盘使用率核验项。"]

    ordered = sorted(
        rows,
        key=lambda item: (
            metric_order.get(item.claim_metric or "", 9),
            _section_sort_key(item),
        ),
    )
    return [
        _render_resource_line(result)
        for result in ordered
    ]


def _render_resource_line(result: ClaimReviewResult) -> str:
    label = _metric_label(result.claim_metric)
    text = f"- {label}：[{result.status}] {result.reason}"
    if result.suggested_revision:
        text += f" 处置建议：{result.suggested_revision}"
    return text


def _render_container_section(log_evidence: LogEvidenceV1 | None) -> list[str]:
    rows = build_container_audit_rows(log_evidence)
    if rows is None:
        return ["- 当前未附带日志证据对象，无法输出容器运行核验摘要。"]
    if not rows:
        return ["- 当前日志中未提取到稳定的容器运行状态证据。"]

    lines = [
        (
            f"- 容器 `{row.container_name}`：状态={row.status_label}，"
            f"CPU={row.cpu_usage}，内存={row.memory_usage}。"
            f" 日志依据：{row.risk_summary}"
            + (f" 处置建议：{row.suggestion}" if row.suggestion else "")
        )
        for row in rows
    ]
    lines.append("- 说明：当前容器结论主要基于 `docker_stats.txt` 等资源快照，不等同于完整健康检查。")
    return lines


def build_container_audit_rows(log_evidence: LogEvidenceV1 | None) -> list[ContainerAuditRow] | None:
    if log_evidence is None:
        return None

    components = _container_components(log_evidence)
    if not components:
        return []

    findings_by_subject = _group_findings_by_subject(log_evidence.log_findings)
    cpu_signals = _group_resource_signals(log_evidence.resource_signals, metric="cpu")
    memory_signals = _group_resource_signals(log_evidence.resource_signals, metric="memory")

    rows: list[ContainerAuditRow] = []
    for component in components:
        name = component.component_name
        normalized_name = name.lower()
        cpu_signal = cpu_signals.get(normalized_name)
        memory_signal = memory_signals.get(normalized_name)
        component_findings = findings_by_subject.get(normalized_name, [])
        abnormal = (
            component.status in {"failed", "restarting", "stopped"}
            or component.health == "unhealthy"
            or bool(component_findings)
            or _resource_signal_is_abnormal(cpu_signal)
            or _resource_signal_is_abnormal(memory_signal)
        )
        risk_summary = "当前日志快照未见明确异常。"
        suggestion = ""
        if abnormal:
            risk_summary = _container_risk_text(component_findings, cpu_signal, memory_signal)
            suggestion = _container_suggestion(component_findings, cpu_signal, memory_signal) or ""
        rows.append(
            ContainerAuditRow(
                container_name=name,
                status_label=_status_label(component.status),
                cpu_usage=_resource_value(cpu_signal),
                memory_usage=_resource_value(memory_signal),
                risk_summary=risk_summary,
                suggestion=suggestion,
            )
        )
    return rows


def _render_manual_section(audit_result: AuditResultV1) -> list[str]:
    rows = [
        result
        for result in audit_result.claim_results
        if result.status == "无法由日志判断"
    ]
    if not rows:
        return ["- 无"]
    ordered = sorted(rows, key=_section_sort_key)
    return [
        f"- `{result.claim_type}`：{result.reason}"
        for result in ordered
    ]


def _render_revisions(audit_result: AuditResultV1) -> list[str]:
    revisions = [
        result.suggested_revision
        for result in audit_result.claim_results
        if result.suggested_revision
    ]
    deduped = list(dict.fromkeys(revisions))
    if not deduped:
        return ["- 无"]
    return [f"- {revision}" for revision in deduped]


def _container_components(log_evidence: LogEvidenceV1) -> list[RuntimeComponentEvidence]:
    generic_subjects = {"service", "container", "system", "host", "preprocessing_coverage"}
    seen: set[str] = set()
    components: list[RuntimeComponentEvidence] = []
    for component in log_evidence.runtime_components:
        name = component.component_name.strip()
        lowered = name.lower()
        if not name or lowered in generic_subjects:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        components.append(component)
    return sorted(components, key=lambda item: item.component_name.lower())


def _group_findings_by_subject(findings: list[LogFinding]) -> dict[str, list[LogFinding]]:
    grouped: dict[str, list[LogFinding]] = {}
    for finding in findings:
        key = finding.subject.strip().lower()
        grouped.setdefault(key, []).append(finding)
    return grouped


def _group_resource_signals(
    signals: list[ResourceSignal],
    *,
    metric: str,
) -> dict[str, ResourceSignal]:
    grouped: dict[str, ResourceSignal] = {}
    for signal in signals:
        if signal.scope != "container" or signal.metric != metric:
            continue
        key = signal.subject.strip().lower()
        grouped[key] = signal
    return grouped


def _resource_signal_is_abnormal(signal: ResourceSignal | None) -> bool:
    return signal is not None and signal.level in {"high", "critical"}


def _resource_value(signal: ResourceSignal | None) -> str:
    if signal is None or signal.observed_value is None:
        return "未知"
    suffix = "%" if (signal.unit or "").lower() in {"percent", "%"} else signal.unit or ""
    return f"{signal.observed_value:.1f}{suffix}"


def _status_label(status: str) -> str:
    mapping = {
        "running": "运行中",
        "restarting": "重启中",
        "failed": "失败",
        "stopped": "已停止",
        "unknown": "未知",
    }
    return mapping.get(status, status)


def _container_risk_text(
    findings: list[LogFinding],
    cpu_signal: ResourceSignal | None,
    memory_signal: ResourceSignal | None,
) -> str:
    segments: list[str] = []
    if _resource_signal_is_abnormal(cpu_signal):
        segments.append(f"CPU 使用率偏高，当前约为 {_resource_value(cpu_signal)}")
    if _resource_signal_is_abnormal(memory_signal):
        segments.append(f"内存使用率偏高，当前约为 {_resource_value(memory_signal)}")

    finding_types = {finding.finding_type for finding in findings}
    if "restart" in finding_types:
        segments.append("存在重启异常迹象")
    elif "oom" in finding_types:
        segments.append("存在内存溢出风险")
    elif "health_fail" in finding_types:
        segments.append("存在健康检查异常")
    elif "dependency_fail" in finding_types:
        segments.append("存在依赖连接异常")
    elif "port_bind_fail" in finding_types:
        segments.append("存在端口绑定异常")
    elif findings:
        segments.append("存在异常运行迹象")

    return "；".join(segments) if segments else "当前日志未见明确异常。"


def _container_suggestion(
    findings: list[LogFinding],
    cpu_signal: ResourceSignal | None,
    memory_signal: ResourceSignal | None,
) -> str | None:
    finding_types = {finding.finding_type for finding in findings}
    if "oom" in finding_types:
        return "建议优先排查容器内存上限、宿主机内存压力及 OOM 记录。"
    if "restart" in finding_types:
        return "建议回看重启前后容器日志、依赖连接和最近发布变更。"
    if "dependency_fail" in finding_types or "port_bind_fail" in finding_types:
        return "建议检查容器依赖服务连通性、端口绑定和启动参数。"
    if _resource_signal_is_abnormal(cpu_signal) or _resource_signal_is_abnormal(memory_signal):
        return "建议结合近期业务流量与资源限制配置，确认是否存在持续高负载。"
    if findings:
        return "建议结合对应容器日志进一步核查异常原因。"
    return None


def _metric_label(metric: str | None) -> str:
    mapping = {
        "cpu": "CPU使用率",
        "memory": "内存使用率",
        "disk": "磁盘使用率",
    }
    return mapping.get(metric or "", metric or "资源指标")


def _section_sort_key(result: ClaimReviewResult) -> tuple[int, str, str]:
    priority_order = {"high": 0, "medium": 1, "manual_only": 2}
    return (
        priority_order.get(result.claim_priority, 9),
        result.claim_type,
        result.claim_id,
    )
