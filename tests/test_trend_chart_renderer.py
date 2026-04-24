from pathlib import Path

from app.services.trend_chart_renderer import render_trend_charts
from app.services.trend_input_builder import build_trend_input_from_markdown


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trend_reports"


def test_trend_chart_renderer_generates_png_only_for_multi_point_series(tmp_path: Path) -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "multi_point_status_analysis.md",
        run_id="trd_chart_001",
        generated_at="2026-04-16T00:00:00Z",
    )

    artifacts = render_trend_charts(trend_input, tmp_path)

    assert [artifact.metric_name for artifact in artifacts] == ["cpu", "memory", "disk"]
    for artifact in artifacts:
        content = artifact.path.read_bytes()
        assert content.startswith(b"\x89PNG\r\n\x1a\n")


def test_trend_chart_renderer_skips_single_snapshot_series(tmp_path: Path) -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "single_snapshot_status_analysis.md",
        run_id="trd_chart_002",
        generated_at="2026-04-16T00:00:00Z",
    )

    artifacts = render_trend_charts(trend_input, tmp_path)

    assert artifacts == []
