from __future__ import annotations

from app.schemas.status_analysis import (
    StatusAnalysisMetricSnapshot,
    StatusAnalysisResourceTimePoint,
    StatusAnalysisSummaryV1,
)

EVENT_LABELS = {
    "restart": "重启",
    "panic": "panic",
    "abnormal_exit": "异常退出",
    "unclean_shutdown": "非正常关闭/恢复",
}


def render_status_analysis_markdown(summary: StatusAnalysisSummaryV1) -> str:
    lines: list[str] = [
        "# SafeLine WAF 状态分析报告",
        "",
        f"> **采集时间**: {summary.metadata.collect_time_raw or summary.metadata.reference_time}",
        (
            f"> **分析范围**: {summary.metadata.window_start[:10]} ~ "
            f"{summary.metadata.window_end[:10]}（最近 {summary.metadata.window_days} 天）"
        ),
    ]
    if summary.metadata.host_hostname:
        lines.append(f"> **主机名**: {summary.metadata.host_hostname}")
    if summary.metadata.product_version:
        lines.append(f"> **产品版本**: {summary.metadata.product_version}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 1. 系统资源状态",
            "",
            "### 1.1 CPU",
        ]
    )
    lines.extend(_render_percent_snapshot_table(summary.cpu_snapshot, label="CPU 当前值"))
    lines.extend(
        [
            "",
            "### 1.2 内存",
        ]
    )
    lines.extend(_render_percent_snapshot_table(summary.memory_snapshot, label="已用"))
    lines.extend(
        [
            "",
            "### 1.3 磁盘",
        ]
    )
    lines.extend(_render_metric_table(summary.disk_snapshot, label="使用率"))
    lines.extend(
        [
            "",
            "### 1.4 Uptime / 运行时长",
        ]
    )
    lines.extend(_render_uptime_table(summary.uptime_snapshot))
    lines.extend(
        [
            "",
            "### 1.5 资源历史样本",
        ]
    )
    lines.extend(_render_resource_history_table(summary.resource_time_series))

    lines.extend(
        [
            "",
            "## 2. 关键风险发现",
            "",
            "### 2.1 Panic / Abnormal Exit",
        ]
    )
    lines.extend(_render_stability_slice(summary, event_types={"panic", "abnormal_exit"}, empty_text="30 天内无 panic / abnormal exit 记录。"))
    lines.extend(
        [
            "",
            "### 2.2 非计划重启 / Unclean Shutdown",
        ]
    )
    lines.extend(_render_stability_slice(summary, event_types={"restart", "unclean_shutdown"}, empty_text="30 天内无非计划重启。"))
    lines.extend(
        [
            "",
            "### 2.3 服务异常",
        ]
    )
    lines.extend(_render_findings_table(summary.service_findings, empty_text="30 天内未识别到明确服务异常。"))
    lines.extend(
        [
            "",
            "### 2.4 关键容器异常",
        ]
    )
    lines.extend(_render_findings_table(summary.container_findings, empty_text="30 天内未识别到关键容器异常。"))

    lines.extend(
        [
            "",
            "## 3. 系统重启时间线与稳定性分析",
            "",
            "### 3.1 重启时间线",
            "",
            "```text",
        ]
    )
    if summary.recent_stability_events:
        for event in summary.recent_stability_events:
            lines.append(
                f"{event.timestamp[:19].replace('T', ' ')}  {event.component or 'system'} "
                f"{EVENT_LABELS.get(event.event_type, event.event_type)}  {event.summary}"
            )
    else:
        lines.append("最近 30 天内未识别到带时间锚点的稳定性事件。")
    lines.extend(["```", "", "### 3.2 稳定性评估", "", "| 指标 | 值 |", "|------|------|"])
    lines.append(f"| restart_count_30d | {summary.stability_counts_30d.restart_count_30d} |")
    lines.append(f"| panic_count_30d | {summary.stability_counts_30d.panic_count_30d} |")
    lines.append(f"| abnormal_exit_count_30d | {summary.stability_counts_30d.abnormal_exit_count_30d} |")
    lines.append(f"| unclean_shutdown_count_30d | {summary.stability_counts_30d.unclean_shutdown_count_30d} |")

    lines.extend(
        [
            "",
            "## 4. 状态摘要与风险线索",
            "",
            f"- 扫描覆盖度：{summary.coverage_level}",
            f"- CPU 当前快照：{_snapshot_value(summary.cpu_snapshot)}",
            f"- 内存当前快照：{_snapshot_value(summary.memory_snapshot)}",
            f"- 磁盘当前快照：{_snapshot_value(summary.disk_snapshot)}",
            f"- 资源历史样本数：{len(summary.resource_time_series)}",
            (
                "- 稳定性 30 天事件拆分："
                f"restart={summary.stability_counts_30d.restart_count_30d}，"
                f"panic={summary.stability_counts_30d.panic_count_30d}，"
                f"abnormal_exit={summary.stability_counts_30d.abnormal_exit_count_30d}，"
                f"unclean_shutdown={summary.stability_counts_30d.unclean_shutdown_count_30d}"
            ),
        ]
    )

    if summary.historical_associations:
        lines.extend(["", "### 历史关联", ""])
        for event in summary.historical_associations[:5]:
            time_text = event.timestamp[:19].replace("T", " ") if event.timestamp else "未标注时间"
            lines.append(f"- {time_text} {event.component or 'system'} {event.event_type}: {event.summary}")

    if summary.scan_limitations or summary.major_skipped_sources or summary.coverage_warnings:
        lines.extend(["", "### 扫描覆盖说明", ""])
        for limitation in summary.scan_limitations:
            lines.append(f"- 限制：{limitation}")
        if summary.major_skipped_sources:
            lines.append(f"- 主要跳过来源：{', '.join(summary.major_skipped_sources[:5])}")
        for warning in summary.coverage_warnings:
            lines.append(f"- 覆盖告警：{warning}")

    if summary.warnings:
        lines.extend(["", "### 解析说明", ""])
        for warning in summary.warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def persist_status_analysis_markdown(markdown_text: str, target_path) -> None:
    target_path.write_text(markdown_text, encoding="utf-8")


def _render_percent_snapshot_table(snapshot: StatusAnalysisMetricSnapshot | None, *, label: str) -> list[str]:
    return _render_metric_table(snapshot, label=label)


def _render_metric_table(snapshot: StatusAnalysisMetricSnapshot | None, *, label: str) -> list[str]:
    lines = ["| 指标 | 采集快照值 | 备注 |", "|------|-----------|------|"]
    if snapshot is None or snapshot.current_value is None:
        lines.append(f"| {label} | - | 未采集到稳定快照 |")
        return lines

    value = _snapshot_value(snapshot)
    lines.append(f"| {label} | {value} | {snapshot.note or '-'} |")
    return lines


def _render_stability_slice(
    summary: StatusAnalysisSummaryV1,
    *,
    event_types: set[str],
    empty_text: str,
) -> list[str]:
    lines: list[str] = []
    matching = [event for event in summary.recent_stability_events if event.event_type in event_types]
    if not matching:
        lines.append(empty_text)
        return lines
    lines.extend(["| 时间 | 组件 | 类型 | 详情 |", "|------|------|------|------|"])
    for event in matching:
        lines.append(
            f"| {event.timestamp[:19].replace('T', ' ')} | {event.component or '-'} | {EVENT_LABELS.get(event.event_type, event.event_type)} | {event.summary} |"
        )
    return lines


def _render_findings_table(findings, *, empty_text: str) -> list[str]:
    if not findings:
        return [empty_text]
    lines = ["| 时间 | 组件 | 级别 | 详情 |", "|------|------|------|------|"]
    for finding in findings:
        lines.append(
            f"| {(finding.timestamp or '-')[:19].replace('T', ' ')} | {finding.component or '-'} | {finding.severity} | {finding.summary} |"
        )
    return lines


def _snapshot_value(snapshot: StatusAnalysisMetricSnapshot | None) -> str:
    if snapshot is None or snapshot.current_value is None:
        return "-"
    if snapshot.unit == "seconds":
        return _format_uptime_seconds(int(snapshot.current_value))
    return f"{snapshot.current_value:.1f}%"


def _render_uptime_table(snapshot: StatusAnalysisMetricSnapshot | None) -> list[str]:
    lines = ["| 指标 | 值 |", "|------|------|"]
    if snapshot is None or snapshot.current_value is None:
        lines.append("| 当前 uptime | - |")
        return lines
    lines.append(f"| 当前 uptime | {_snapshot_value(snapshot)} |")
    return lines


def _render_resource_history_table(points: list[StatusAnalysisResourceTimePoint]) -> list[str]:
    if not points:
        return ["未识别到低歧义资源历史样本。"]

    lines = ["| 时间 | CPU | 内存 | 磁盘 | 样本数 | 来源 |", "|------|-----|------|------|--------|------|"]
    for point in points[:200]:
        lines.append(
            "| "
            f"{point.timestamp[:19].replace('T', ' ')} | "
            f"{_format_optional_percent(point.cpu_percent)} | "
            f"{_format_optional_percent(point.memory_percent)} | "
            f"{_format_optional_percent(point.disk_percent)} | "
            f"{point.sample_count} | "
            f"{point.source_ref} |"
        )
    return lines


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def _format_uptime_seconds(value: int) -> str:
    days, rem = divmod(value, 24 * 3600)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes and not days:
        parts.append(f"{minutes} 分钟")
    return " ".join(parts) if parts else "0 分钟"
