from pathlib import Path

from app.services.trend_forecaster import build_trend_assessment
from app.services.trend_input_builder import build_trend_input_from_markdown
from app.services.trend_summary_renderer import render_trend_summary_markdown


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trend_reports"


def test_trend_summary_renderer_outputs_fixed_sections_and_no_chart_notice() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "single_snapshot_status_analysis.md",
        run_id="trd_summary_001",
        generated_at="2026-04-16T00:00:00Z",
    )
    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_summary_001/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    markdown = render_trend_summary_markdown(assessment)

    assert "# 趋势增强摘要" in markdown
    assert "## 总体结论" in markdown
    assert "## CPU 趋势" in markdown
    assert "## 稳定性 / 重启风险" in markdown
    assert "少于 2 个" in markdown
    assert "LLM 不是本阶段预测引擎" in markdown


def test_trend_summary_renderer_includes_event_split_and_fault_chain_text() -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "multi_point_status_analysis.md",
        run_id="trd_summary_002",
        generated_at="2026-04-16T00:00:00Z",
    )
    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_summary_002/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )

    markdown = render_trend_summary_markdown(assessment)

    assert "事件拆分" in markdown
    assert "restart=2" in markdown
    assert "故障链" in markdown
    assert "nginx.service" in markdown
