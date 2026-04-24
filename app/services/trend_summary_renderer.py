from __future__ import annotations

from pathlib import Path

from app.schemas.trend_assessment import (
    TrendAssessmentV1,
    TrendFaultChain,
    TrendMetricAssessment,
    TrendStabilityEventCounts,
)


STATUS_LABELS = {
    "stable": "稳定",
    "pressure_high": "压力较高",
    "deteriorating": "呈恶化趋势",
    "unknown": "信息不足",
}

CONFIDENCE_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}

DATA_QUALITY_LABELS = {
    "sufficient": "较完整",
    "partial": "部分可用",
    "insufficient": "明显不足",
}


def render_trend_summary_markdown(
    assessment: TrendAssessmentV1,
    *,
    chart_filenames: list[str] | None = None,
    mermaid_source: str | None = None,
) -> str:
    chart_filenames = chart_filenames or []
    overall = assessment.overall

    sections = [
        "# 趋势增强摘要",
        "",
        "## 数据来源",
        f"- 输入产物：`{assessment.input_path}`",
        f"- 数据质量：`{DATA_QUALITY_LABELS[overall.data_quality]}`",
        "",
        "## 总体结论",
        (
            f"总体状态：**{STATUS_LABELS[overall.summary_status]}**。"
            f"本阶段仅使用状态分析报告中已经存在的时间点与事件，不补造历史序列。"
        ),
        *[f"- {caution}" for caution in overall.cautions],
        "",
        "## CPU 趋势",
        _render_metric_section(assessment.metrics.cpu),
        "",
        "## 内存趋势",
        _render_metric_section(assessment.metrics.memory),
        "",
        "## 磁盘趋势",
        _render_metric_section(assessment.metrics.disk),
        "",
        "## 稳定性 / 重启风险",
        _render_metric_section(assessment.metrics.stability),
        "",
        "## 图表说明",
    ]

    if chart_filenames:
        sections.extend(f"- 已生成：`{filename}`" for filename in chart_filenames)
    else:
        sections.append("- 未生成图表：当前可用历史点少于 2 个，第一阶段按保守策略仅输出文字说明。")

    if mermaid_source:
        sections.extend(
            [
                "",
                "## 状态趋势图",
                "这是一张状态说明图 / 风险方向图，用于表达历史证据、当前重点风险项和后续观察方向；它不是精确数值预测图。",
                "",
                "```mermaid",
                mermaid_source.strip(),
                "```",
                "",
                "图中的未来观察节点来自规则驱动的保守趋势判断，不代表未来资源数值外推。",
            ]
        )

    sections.extend(
        [
            "",
            "## 适用限制与保守声明",
            "- 本结果为规则驱动的弱预测，不用于数值外推。",
            "- LLM 不是本阶段预测引擎，判断结果仅来自结构化规则。",
            "- 当时间点不足、口径不清或证据冲突时，优先输出信息不足（`unknown`）。",
        ]
    )
    return "\n".join(sections).strip() + "\n"


def persist_trend_summary(markdown: str, target_path: Path) -> None:
    target_path.write_text(markdown, encoding="utf-8")


def _render_metric_section(metric: TrendMetricAssessment) -> str:
    parts = [
        f"状态：**{STATUS_LABELS[metric.status]}**",
        f"置信度：**{CONFIDENCE_LABELS[metric.confidence]}**",
    ]
    if metric.current_value is not None:
        parts.append(f"当前值：`{metric.current_value:.1f}%`")
    if metric.baseline_value is not None and metric.delta is not None:
        parts.append(f"基线值：`{metric.baseline_value:.1f}%`，变化：`{metric.delta:+.1f}` 个百分点")
    if metric.evidence:
        parts.append(f"证据：{_join_statements(metric.evidence)}")
    if metric.event_counts is not None:
        parts.append(f"事件拆分：{_render_event_counts(metric.event_counts)}")
    if metric.fault_chains:
        parts.append(f"故障链：{_render_fault_chains(metric.fault_chains)}")
    if metric.reason_codes:
        parts.append("规则编码：`" + "`, `".join(metric.reason_codes) + "`")
    return "。".join(parts) + "。"


def _join_statements(statements: list[str]) -> str:
    cleaned = []
    for statement in statements:
        normalized = statement.strip().rstrip("。；;，,")
        if normalized:
            cleaned.append(normalized)
    return "；".join(cleaned)


def _render_event_counts(event_counts: TrendStabilityEventCounts) -> str:
    return (
        f"restart={event_counts.restart_count}，"
        f"panic={event_counts.panic_count}，"
        f"abnormal_exit={event_counts.abnormal_exit_count}，"
        f"unclean_shutdown={event_counts.unclean_shutdown_count}"
    )


def _render_fault_chains(fault_chains: list[TrendFaultChain]) -> str:
    return "；".join(chain.summary for chain in fault_chains[:3])
