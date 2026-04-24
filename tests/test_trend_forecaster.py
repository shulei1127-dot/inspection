from pathlib import Path

from app.services.trend_forecaster import build_trend_assessment
from app.services.trend_input_builder import build_trend_input_from_markdown


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trend_reports"


def test_trend_forecaster_outputs_conservative_statuses_and_confidence() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "multi_point_status_analysis.md",
        run_id="trd_forecaster_001",
        generated_at="2026-04-16T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_001/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    assert assessment.metrics.cpu.status == "deteriorating"
    assert assessment.metrics.cpu.confidence == "high"
    assert assessment.metrics.memory.status == "stable"
    assert assessment.metrics.disk.status == "stable"
    assert assessment.metrics.stability.status == "pressure_high"
    assert assessment.metrics.stability.confidence == "high"
    assert assessment.metrics.stability.event_counts is not None
    assert assessment.metrics.stability.event_counts.restart_count == 2
    assert len(assessment.metrics.stability.fault_chains) == 1
    assert assessment.overall.summary_status == "pressure_high"


def test_trend_forecaster_keeps_single_low_snapshot_unknown_instead_of_stable() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "single_snapshot_status_analysis.md",
        run_id="trd_forecaster_002",
        generated_at="2026-04-16T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_002/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    assert assessment.metrics.cpu.status == "unknown"
    assert assessment.metrics.memory.status == "unknown"
    assert assessment.metrics.disk.status == "unknown"
    assert assessment.metrics.cpu.confidence == "low"


def test_trend_forecaster_real_world_snapshot_marks_memory_and_stability_pressure_high() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "real_world_current_snapshot_status_analysis.md",
        run_id="trd_forecaster_003",
        generated_at="2026-04-16T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_003/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    assert assessment.metrics.cpu.status == "unknown"
    assert assessment.metrics.memory.status == "pressure_high"
    assert assessment.metrics.memory.confidence == "medium"
    assert assessment.metrics.stability.status == "pressure_high"
    assert assessment.metrics.stability.confidence == "high"
    assert assessment.metrics.stability.event_counts is not None
    assert assessment.metrics.stability.event_counts.panic_count >= 5
    assert assessment.metrics.stability.event_counts.unclean_shutdown_count >= 5


def test_trend_forecaster_noisy_single_snapshot_can_still_mark_high_pressure() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "noisy_status_analysis.md",
        run_id="trd_forecaster_004",
        generated_at="2026-04-16T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_004/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    assert assessment.metrics.cpu.status == "pressure_high"
    assert assessment.metrics.memory.status == "pressure_high"


def test_trend_forecaster_low_risk_fixture_marks_stability_stable() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "low_risk_stability_status_analysis.md",
        run_id="trd_forecaster_005",
        generated_at="2026-04-16T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_005/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    assert assessment.metrics.cpu.status == "stable"
    assert assessment.metrics.memory.status == "stable"
    assert assessment.metrics.disk.status == "stable"
    assert assessment.metrics.stability.status == "stable"
    assert assessment.overall.summary_status == "stable"


def test_trend_forecaster_disk_fixture_can_mark_deteriorating() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "disk_judgeable_status_analysis.md",
        run_id="trd_forecaster_006",
        generated_at="2026-04-16T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_006/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    assert assessment.metrics.disk.status == "deteriorating"
    assert assessment.metrics.disk.confidence == "medium"


def test_trend_forecaster_waf_shape_extracts_snapshot_resource_signals() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "waf_status_report_shape.md",
        run_id="trd_forecaster_007",
        generated_at="2026-04-17T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_007/trend_input.json",
        generated_at="2026-04-17T00:01:00Z",
    )

    assert assessment.metrics.cpu.status == "unknown"
    assert assessment.metrics.memory.status == "pressure_high"
    assert assessment.metrics.disk.status == "unknown"
    assert assessment.metrics.stability.status == "pressure_high"
    assert assessment.overall.summary_status == "pressure_high"


def test_trend_forecaster_vmware_shape_keeps_memory_conservative_after_swap_is_ignored() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "waf_vmware_status_report_shape.md",
        run_id="trd_forecaster_008",
        generated_at="2026-04-17T00:00:00Z",
    )

    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_forecaster_008/trend_input.json",
        generated_at="2026-04-17T00:01:00Z",
    )

    assert assessment.metrics.memory.status == "unknown"
    assert assessment.metrics.disk.status == "unknown"
    assert assessment.metrics.stability.status == "unknown"
