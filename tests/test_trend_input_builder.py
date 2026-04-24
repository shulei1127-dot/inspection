from pathlib import Path

import pytest

from app.services.trend_input_builder import (
    TrendInputBuildError,
    build_trend_input_from_markdown,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trend_reports"


def test_trend_input_builder_extracts_samples_from_cleaned_status_analysis_markdown() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "multi_point_status_analysis.md",
        run_id="trd_builder_001",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert trend_input.contract_version == "trend-input/v1"
    assert trend_input.source.type == "cleaned-status-analysis-md"
    assert len(trend_input.metrics.cpu.samples) == 4
    assert len(trend_input.metrics.memory.samples) == 4
    assert len(trend_input.metrics.disk.samples) == 4
    assert len(trend_input.stability.uptime_samples) == 4
    assert len(trend_input.stability.restart_events) == 1
    assert trend_input.stability.restart_events[0].count == 2
    assert trend_input.stability.event_counts.restart_count == 2
    assert trend_input.stability.event_counts.panic_count == 0
    assert len(trend_input.stability.fault_chains) == 1
    assert trend_input.parse_summary.time_points_detected == 5
    assert trend_input.parse_summary.data_quality == "sufficient"
    assert trend_input.parse_summary.warnings == []


def test_trend_input_builder_keeps_single_snapshot_partial_and_adds_no_chart_warnings() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "single_snapshot_status_analysis.md",
        run_id="trd_builder_002",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert len(trend_input.metrics.cpu.samples) == 1
    assert len(trend_input.metrics.memory.samples) == 1
    assert len(trend_input.metrics.disk.samples) == 1
    assert trend_input.parse_summary.data_quality == "partial"
    assert any("CPU 历史点少于 2 个" in warning for warning in trend_input.parse_summary.warnings)
    assert any("内存历史点少于 2 个" in warning for warning in trend_input.parse_summary.warnings)
    assert any("磁盘历史点少于 2 个" in warning for warning in trend_input.parse_summary.warnings)


def test_trend_input_builder_extracts_real_world_snapshot_and_timeline_without_overcounting_risk_text() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "real_world_current_snapshot_status_analysis.md",
        run_id="trd_builder_004",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert [sample.value for sample in trend_input.metrics.cpu.samples] == [22.7]
    assert [sample.value for sample in trend_input.metrics.memory.samples] == [84.6]
    assert len(trend_input.stability.uptime_samples) == 1
    assert trend_input.stability.uptime_samples[0].uptime_seconds == 782040
    assert trend_input.stability.event_counts.restart_count >= 6
    assert trend_input.stability.event_counts.panic_count >= 5
    assert trend_input.stability.event_counts.unclean_shutdown_count >= 5
    assert trend_input.stability.fault_chains
    assert all("概率高" not in event.source_excerpt for event in trend_input.stability.restart_events)
    assert all("风险" not in event.source_excerpt for event in trend_input.stability.restart_events)


def test_trend_input_builder_tolerates_missing_data_and_keeps_partial_output() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "data_missing_status_analysis.md",
        run_id="trd_builder_005",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert trend_input.metrics.cpu.samples == []
    assert trend_input.metrics.memory.samples == []
    assert len(trend_input.stability.restart_events) == 1
    assert trend_input.stability.event_counts.restart_count == 1
    assert trend_input.parse_summary.data_quality == "partial"


def test_trend_input_builder_ignores_predictive_noise_without_existing_event() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "noisy_status_analysis.md",
        run_id="trd_builder_006",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert [sample.value for sample in trend_input.metrics.cpu.samples] == [80.0]
    assert [sample.value for sample in trend_input.metrics.memory.samples] == [90.6]
    assert trend_input.stability.restart_events == []
    assert trend_input.stability.event_counts.restart_count == 0


def test_trend_input_builder_captures_low_risk_stability_fixture_without_false_events() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "low_risk_stability_status_analysis.md",
        run_id="trd_builder_007",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert len(trend_input.metrics.cpu.samples) == 3
    assert len(trend_input.stability.uptime_samples) == 3
    assert trend_input.stability.restart_events == []
    assert trend_input.stability.event_counts.model_dump() == {
        "restart_count": 0,
        "panic_count": 0,
        "abnormal_exit_count": 0,
        "unclean_shutdown_count": 0,
    }
    assert trend_input.stability.fault_chains == []


def test_trend_input_builder_captures_disk_judgeable_fixture() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "disk_judgeable_status_analysis.md",
        run_id="trd_builder_008",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert [sample.value for sample in trend_input.metrics.disk.samples] == [76.0, 80.0, 83.0]
    assert len(trend_input.stability.uptime_samples) == 3


def test_trend_input_builder_adapts_waf_status_report_shape() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "waf_status_report_shape.md",
        run_id="trd_builder_009",
        generated_at="2026-04-17T00:00:00Z",
    )

    assert [sample.value for sample in trend_input.metrics.cpu.samples] == [22.7]
    assert [sample.value for sample in trend_input.metrics.memory.samples] == [84.6]
    assert [sample.value for sample in trend_input.metrics.disk.samples] == [11.0]
    assert len(trend_input.stability.uptime_samples) == 1
    assert trend_input.stability.uptime_samples[0].uptime_seconds == 782040
    assert trend_input.stability.event_counts.restart_count >= 1
    assert trend_input.stability.event_counts.panic_count >= 1
    assert trend_input.stability.event_counts.unclean_shutdown_count >= 1
    assert all(
        event.subject not in {"1.", "5.", "-"}
        for event in trend_input.stability.restart_events
    )


def test_trend_input_builder_does_not_mix_swap_with_memory_or_untimed_restart_explanations() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "waf_vmware_status_report_shape.md",
        run_id="trd_builder_010",
        generated_at="2026-04-17T00:00:00Z",
    )

    assert [sample.value for sample in trend_input.metrics.memory.samples] == [54.3]
    assert [sample.value for sample in trend_input.metrics.disk.samples] == [65.6]
    assert len(trend_input.stability.uptime_samples) == 1
    assert trend_input.stability.event_counts.restart_count == 0
    assert trend_input.stability.fault_chains == []


def test_trend_input_builder_collapses_generated_resource_history_snapshot_duplicates(tmp_path: Path) -> None:
    source_path = tmp_path / "generated_status_analysis.md"
    source_path.write_text(
        "\n".join(
            [
                "# SafeLine WAF 状态分析报告",
                "",
                "> **采集时间**: 2026-04-16 04:54:04 UTC",
                "",
                "## 1. 系统资源状态",
                "",
                "### 1.1 CPU",
                "| 指标 | 采集快照值 | 备注 |",
                "|------|-----------|------|",
                "| CPU 当前值 | 7.6% | Round1 CPU current snapshot from top summary. |",
                "",
                "### 1.2 内存",
                "| 指标 | 采集快照值 | 备注 |",
                "|------|-----------|------|",
                "| 已用 | 54.2% | Round1 memory current snapshot from top Mem summary fallback. |",
                "",
                "### 1.5 资源历史样本",
                "| 时间 | CPU | 内存 | 磁盘 | 样本数 | 来源 |",
                "|------|-----|------|------|--------|------|",
                "| 2026-04-16 00:00:00 | 7.6% | 54.2% | - | 1 | resources/resource_history.csv |",
            ]
        ),
        encoding="utf-8",
    )

    trend_input = build_trend_input_from_markdown(
        source_path,
        run_id="trd_builder_011",
        generated_at="2026-04-18T00:00:00Z",
    )

    assert len(trend_input.metrics.cpu.samples) == 1
    assert len(trend_input.metrics.memory.samples) == 1
    assert trend_input.metrics.cpu.samples[0].source_excerpt.endswith("resources/resource_history.csv")
    assert trend_input.parse_summary.data_quality == "partial"
    assert any("CPU 历史点少于 2 个" in warning for warning in trend_input.parse_summary.warnings)
    assert any("内存历史点少于 2 个" in warning for warning in trend_input.parse_summary.warnings)


def test_trend_input_builder_rejects_unstructured_markdown(tmp_path: Path) -> None:
    source_path = tmp_path / "empty.md"
    source_path.write_text("# 状态分析报告\n\n没有可结构化的时间点。\n", encoding="utf-8")

    with pytest.raises(TrendInputBuildError):
        build_trend_input_from_markdown(
            source_path,
            run_id="trd_builder_003",
            generated_at="2026-04-16T00:00:00Z",
        )
