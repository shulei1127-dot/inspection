from __future__ import annotations

from pathlib import Path

from app.schemas.trend_assessment import TrendAssessmentV1, TrendMetricAssessment


STATUS_LABELS = {
    "stable": "稳定",
    "pressure_high": "压力较高",
    "deteriorating": "呈恶化趋势",
    "unknown": "信息不足",
}

DATA_QUALITY_LABELS = {
    "sufficient": "较完整",
    "partial": "部分可用",
    "insufficient": "明显不足",
}

METRIC_LABELS = {
    "cpu": "CPU",
    "memory": "内存",
    "disk": "磁盘",
    "stability": "稳定性",
}

RISK_RANK = {
    "deteriorating": 4,
    "pressure_high": 3,
    "unknown": 2,
    "stable": 1,
}


def render_trend_mermaid(assessment: TrendAssessmentV1) -> str:
    focus_key, focus_metric = _select_focus_metric(assessment)
    focus_label = METRIC_LABELS.get(focus_key, "整体")
    focus_status = STATUS_LABELS[focus_metric.status] if focus_metric is not None else STATUS_LABELS[assessment.overall.summary_status]

    historical_label = (
        "历史窗口<br/>"
        f"数据质量：{DATA_QUALITY_LABELS[assessment.overall.data_quality]}"
    )
    focus_node = f"重点项<br/>{focus_label}：{focus_status}"
    current_node = _current_node_text(focus_metric)
    future_node = _future_node_text(focus_key, focus_metric.status if focus_metric is not None else assessment.overall.summary_status)
    action_node = _action_node_text(focus_metric.status if focus_metric is not None else assessment.overall.summary_status)

    return "\n".join(
        [
            "flowchart LR",
            f'  H["{_escape_mermaid_label(historical_label)}"] --> R["{_escape_mermaid_label(focus_node)}"]',
            f'  R --> C["{_escape_mermaid_label(current_node)}"]',
            f'  C --> F["{_escape_mermaid_label(future_node)}"]',
            f'  F --> A["{_escape_mermaid_label(action_node)}"]',
            "",
        ]
    )


def persist_trend_mermaid(mermaid_source: str, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(mermaid_source, encoding="utf-8")


def _select_focus_metric(assessment: TrendAssessmentV1) -> tuple[str, TrendMetricAssessment | None]:
    metrics = {
        "cpu": assessment.metrics.cpu,
        "memory": assessment.metrics.memory,
        "disk": assessment.metrics.disk,
        "stability": assessment.metrics.stability,
    }
    if all(metric.status == "stable" for metric in metrics.values()):
        return "overall", None
    if all(metric.status == "unknown" for metric in metrics.values()):
        return "data_quality", None

    priority_order = {"stability": 0, "memory": 1, "disk": 2, "cpu": 3}
    focus_key, focus_metric = max(
        metrics.items(),
        key=lambda item: (RISK_RANK[item[1].status], -priority_order[item[0]]),
    )
    return focus_key, focus_metric


def _current_node_text(metric: TrendMetricAssessment | None) -> str:
    if metric is None:
        return "当前状态<br/>以总体结论为准"
    parts = ["当前状态"]
    if metric.current_value is not None:
        parts.append(f"当前值：{metric.current_value:.1f}%")
    if metric.baseline_value is not None and metric.delta is not None:
        parts.append(f"基线：{metric.baseline_value:.1f}% / 变化：{metric.delta:+.1f}pp")
    if len(parts) == 1:
        parts.append("无可用数值，按事件/证据判断")
    return "<br/>".join(parts)


def _future_node_text(metric_key: str, status: str) -> str:
    subject = METRIC_LABELS.get(metric_key, "整体状态")
    if status == "stable":
        return f"未来观察<br/>{subject}短期保持稳定观察"
    if status == "pressure_high":
        return f"未来观察<br/>{subject}压力可能持续"
    if status == "deteriorating":
        return f"未来观察<br/>{subject}存在恶化风险"
    return f"未来观察<br/>{subject}证据不足，需补充采样"


def _action_node_text(status: str) -> str:
    if status == "stable":
        return "建议<br/>保持常规巡检与12小时采样"
    if status == "pressure_high":
        return "建议<br/>关注高压指标并复核容量/进程"
    if status == "deteriorating":
        return "建议<br/>优先排查增长来源并制定处置计划"
    return "建议<br/>补充连续样本后再强化判断"


def _escape_mermaid_label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', "'")
        .replace("[", "【")
        .replace("]", "】")
        .replace("\n", " ")
    )
