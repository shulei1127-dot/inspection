from __future__ import annotations

from datetime import datetime

from app.schemas.trend_assessment import (
    TrendAssessmentMetrics,
    TrendAssessmentOverall,
    TrendAssessmentV1,
    TrendConfidence,
    TrendInputV1,
    TrendMetricAssessment,
    TrendMetricSample,
)


SINGLE_SNAPSHOT_WARNING_TOKENS = ("告警", "紧张", "严重", "高", "风险")


def build_trend_assessment(
    trend_input: TrendInputV1,
    *,
    input_path: str,
    generated_at: str,
) -> TrendAssessmentV1:
    cpu = _assess_resource_metric(
        trend_input.metrics.cpu.samples,
        metric_name="cpu",
        attention_threshold=70.0,
        pressure_threshold=85.0,
        stable_threshold=75.0,
        stable_variation=10.0,
        deteriorating_delta=10.0,
    )
    memory = _assess_resource_metric(
        trend_input.metrics.memory.samples,
        metric_name="memory",
        attention_threshold=70.0,
        pressure_threshold=85.0,
        stable_threshold=75.0,
        stable_variation=10.0,
        deteriorating_delta=8.0,
    )
    disk = _assess_resource_metric(
        trend_input.metrics.disk.samples,
        metric_name="disk",
        attention_threshold=75.0,
        pressure_threshold=85.0,
        stable_threshold=75.0,
        stable_variation=5.0,
        deteriorating_delta=5.0,
        severe_threshold=90.0,
    )
    stability = _assess_stability(
        uptime_sample_count=len(trend_input.stability.uptime_samples),
        restart_events=trend_input.stability.restart_events,
        event_counts=trend_input.stability.event_counts,
        fault_chains=trend_input.stability.fault_chains,
        resource_statuses=[cpu.status, memory.status, disk.status],
    )

    overall = _build_overall_assessment(
        data_quality=trend_input.parse_summary.data_quality,
        metrics=[cpu, memory, disk, stability],
        warnings=trend_input.parse_summary.warnings,
    )

    return TrendAssessmentV1(
        run_id=trend_input.run_id,
        generated_at=generated_at,
        input_path=input_path,
        overall=overall,
        metrics=TrendAssessmentMetrics(
            cpu=cpu,
            memory=memory,
            disk=disk,
            stability=stability,
        ),
        warnings=list(trend_input.parse_summary.warnings),
    )


def _assess_resource_metric(
    samples: list[TrendMetricSample],
    *,
    metric_name: str,
    attention_threshold: float,
    pressure_threshold: float,
    stable_threshold: float,
    stable_variation: float,
    deteriorating_delta: float,
    severe_threshold: float | None = None,
) -> TrendMetricAssessment:
    ordered = sorted(samples, key=lambda sample: _parse_timestamp(sample.timestamp))
    sample_count = len(ordered)
    if sample_count == 0:
        return TrendMetricAssessment(
            status="unknown",
            confidence="low",
            evidence=["未检测到可用于规则判断的历史样本。"],
            reason_codes=["no_samples"],
        )

    latest = ordered[-1]
    current_value = latest.value
    upper_pressure = severe_threshold or pressure_threshold

    if sample_count == 1:
        if current_value >= pressure_threshold:
            return TrendMetricAssessment(
                status="pressure_high",
                confidence="medium",
                current_value=current_value,
                evidence=[f"仅检测到 1 个样本，但当前值已达到 {pressure_threshold:.0f}% 阈值。"],
                reason_codes=[f"{metric_name}_single_high_snapshot"],
            )
        if current_value >= attention_threshold and _contains_warning_signal(latest.source_excerpt):
            return TrendMetricAssessment(
                status="pressure_high",
                confidence="medium",
                current_value=current_value,
                evidence=[
                    "仅检测到 1 个样本。",
                    "当前快照已进入关注区间，且原文给出明确告警/紧张信号。",
                ],
                reason_codes=[f"{metric_name}_single_warning_snapshot"],
            )
        return TrendMetricAssessment(
            status="unknown",
            confidence="low",
            current_value=current_value,
            evidence=["仅检测到 1 个样本，按保守策略不输出趋势图和稳定结论。"],
            reason_codes=["insufficient_points"],
        )

    baseline = ordered[0]
    delta = round(current_value - baseline.value, 2)
    values = [sample.value for sample in ordered]
    variation = max(values) - min(values)
    upward_steps = sum(1 for previous, current in zip(values, values[1:]) if current > previous)
    high_zone_count = sum(1 for value in values if value >= attention_threshold)
    pressure_zone_count = sum(1 for value in values if value >= pressure_threshold)

    if current_value >= upper_pressure or pressure_zone_count >= 2:
        return TrendMetricAssessment(
            status="pressure_high",
            confidence=_confidence_from_sample_count(sample_count),
            current_value=current_value,
            baseline_value=baseline.value,
            delta=delta,
            evidence=[
                f"最新值达到 {current_value:.1f}% 。",
                f"样本中共有 {pressure_zone_count} 个时间点达到高压阈值。",
            ],
            reason_codes=[f"{metric_name}_pressure_threshold"],
        )

    if (
        current_value >= attention_threshold
        and delta >= deteriorating_delta
        and upward_steps >= max(1, sample_count - 2)
        and high_zone_count >= 2
    ):
        return TrendMetricAssessment(
            status="deteriorating",
            confidence=_confidence_from_sample_count(sample_count),
            current_value=current_value,
            baseline_value=baseline.value,
            delta=delta,
            evidence=[
                f"最近 {sample_count} 个时间点整体上升。",
                f"最新值已进入重点关注区间，较基线增加 {delta:.1f} 个百分点。",
            ],
            reason_codes=[f"{metric_name}_upward_slope", f"{metric_name}_attention_zone"],
        )

    if current_value < stable_threshold and variation < stable_variation:
        return TrendMetricAssessment(
            status="stable",
            confidence=_confidence_from_sample_count(sample_count),
            current_value=current_value,
            baseline_value=baseline.value,
            delta=delta,
            evidence=[f"最近 {sample_count} 个样本波动为 {variation:.1f} 个百分点，未进入高压区间。"],
            reason_codes=[f"{metric_name}_low_variation"],
        )

    return TrendMetricAssessment(
        status="unknown",
        confidence=_confidence_from_sample_count(sample_count),
        current_value=current_value,
        baseline_value=baseline.value,
        delta=delta,
        evidence=["存在部分历史点，但不足以保守地判定为稳定、恶化或高压。"],
        reason_codes=[f"{metric_name}_mixed_signals"],
    )


def _assess_stability(
    *,
    uptime_sample_count: int,
    restart_events,
    event_counts,
    fault_chains,
    resource_statuses: list[str],
) -> TrendMetricAssessment:
    if restart_events:
        total_event_count = (
            event_counts.restart_count
            + event_counts.panic_count
            + event_counts.abnormal_exit_count
            + event_counts.unclean_shutdown_count
        )
        chain_count = len(fault_chains)

        if (
            event_counts.panic_count > 0
            or event_counts.abnormal_exit_count > 0
            or event_counts.unclean_shutdown_count > 0
            or event_counts.restart_count >= 2
            or chain_count >= 2
        ):
            return TrendMetricAssessment(
                status="pressure_high",
                confidence="high" if (total_event_count >= 2 or chain_count >= 2) else "medium",
                evidence=[
                    (
                        "检测到稳定性事件拆分结果："
                        f"重启 {event_counts.restart_count}，"
                        f"panic {event_counts.panic_count}，"
                        f"异常退出 {event_counts.abnormal_exit_count}，"
                        f"非正常关闭 {event_counts.unclean_shutdown_count}。"
                    ),
                    f"已聚合出 {chain_count} 条故障链，稳定性风险由原文已记录事件直接触发。",
                ],
                reason_codes=["stability_fault_chain_detected"],
                event_counts=event_counts,
                fault_chains=fault_chains,
            )

        if any(status in {"deteriorating", "pressure_high"} for status in resource_statuses):
            return TrendMetricAssessment(
                status="deteriorating",
                confidence="medium",
                evidence=[
                    (
                        "检测到轻量稳定性事件："
                        f"重启 {event_counts.restart_count}，"
                        f"panic {event_counts.panic_count}，"
                        f"异常退出 {event_counts.abnormal_exit_count}，"
                        f"非正常关闭 {event_counts.unclean_shutdown_count}。"
                    ),
                    "资源指标同步出现恶化或高压信号，按保守策略视为潜在恶化。",
                ],
                reason_codes=["restart_events_with_resource_pressure"],
                event_counts=event_counts,
                fault_chains=fault_chains,
            )

        return TrendMetricAssessment(
            status="pressure_high",
            confidence="medium",
            evidence=[
                (
                    "检测到轻量稳定性事件："
                    f"重启 {event_counts.restart_count}，"
                    f"panic {event_counts.panic_count}，"
                    f"异常退出 {event_counts.abnormal_exit_count}，"
                    f"非正常关闭 {event_counts.unclean_shutdown_count}。"
                )
            ],
            reason_codes=["restart_events_detected"],
            event_counts=event_counts,
            fault_chains=fault_chains,
        )

    if uptime_sample_count >= 2:
        return TrendMetricAssessment(
            status="stable",
            confidence="medium",
            evidence=["检测到连续 uptime 采样，且未发现明确重启事件。"],
            reason_codes=["uptime_without_restarts"],
            event_counts=event_counts,
            fault_chains=fault_chains,
        )

    return TrendMetricAssessment(
        status="unknown",
        confidence="low",
        evidence=["未检测到足够的 uptime 或重启事件证据。"],
        reason_codes=["insufficient_stability_evidence"],
        event_counts=event_counts,
        fault_chains=fault_chains,
    )


def _build_overall_assessment(
    *,
    data_quality: str,
    metrics: list[TrendMetricAssessment],
    warnings: list[str],
) -> TrendAssessmentOverall:
    statuses = [metric.status for metric in metrics]
    if "pressure_high" in statuses:
        summary_status = "pressure_high"
    elif "deteriorating" in statuses:
        summary_status = "deteriorating"
    elif "stable" in statuses:
        summary_status = "stable"
    else:
        summary_status = "unknown"

    cautions = list(warnings)
    unknown_count = sum(1 for status in statuses if status == "unknown")
    if unknown_count:
        cautions.append(f"共有 {unknown_count} 个指标因样本不足或口径不清而保持保守判断。")

    return TrendAssessmentOverall(
        summary_status=summary_status,
        data_quality=data_quality,
        cautions=cautions,
    )


def _confidence_from_sample_count(sample_count: int) -> TrendConfidence:
    if sample_count >= 4:
        return "high"
    if sample_count >= 2:
        return "medium"
    return "low"


def _parse_timestamp(raw_value: str) -> datetime:
    normalized = raw_value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _contains_warning_signal(source_excerpt: str) -> bool:
    return any(token in source_excerpt for token in SINGLE_SNAPSHOT_WARNING_TOKENS)
