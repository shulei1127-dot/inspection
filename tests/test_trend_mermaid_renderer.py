from pathlib import Path

from app.services.trend_forecaster import build_trend_assessment
from app.services.trend_input_builder import build_trend_input_from_markdown
from app.services.trend_mermaid_renderer import render_trend_mermaid


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trend_reports"


def test_trend_mermaid_renderer_focuses_highest_risk_metric() -> None:
    mermaid = _render_fixture("disk_judgeable_status_analysis.md")

    assert mermaid.startswith("flowchart LR")
    assert "重点项<br/>磁盘：呈恶化趋势" in mermaid
    assert "未来观察<br/>磁盘存在恶化风险" in mermaid


def test_trend_mermaid_renderer_handles_pressure_high_status() -> None:
    mermaid = _render_fixture("real_world_current_snapshot_status_analysis.md")

    assert "重点项<br/>稳定性：压力较高" in mermaid
    assert "压力可能持续" in mermaid
    assert "关注高压指标并复核容量/进程" in mermaid


def test_trend_mermaid_renderer_handles_stable_status() -> None:
    mermaid = _render_fixture("low_risk_stability_status_analysis.md")

    assert "重点项<br/>整体：稳定" in mermaid
    assert "短期保持稳定观察" in mermaid
    assert "保持常规巡检与12小时采样" in mermaid


def test_trend_mermaid_renderer_handles_unknown_status() -> None:
    mermaid = _render_fixture("single_snapshot_status_analysis.md")

    assert "重点项<br/>整体：信息不足" in mermaid
    assert "证据不足，需补充采样" in mermaid
    assert "补充连续样本后再强化判断" in mermaid


def _render_fixture(filename: str) -> str:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / filename,
        run_id="trd_mermaid_test",
        generated_at="2026-04-17T00:00:00Z",
    )
    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_mermaid_test/trend_input.json",
        generated_at="2026-04-17T00:01:00Z",
    )
    return render_trend_mermaid(assessment)
