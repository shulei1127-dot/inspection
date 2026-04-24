from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import shutil
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.schemas.trend_assessment import TrendAssessmentV1, TrendInputV1
from app.services.mermaid_renderer import build_mermaid_renderer
from app.services.report_augmenter import augment_report_with_trend_appendix
from app.services.trend_chart_renderer import render_trend_charts
from app.services.trend_forecaster import build_trend_assessment
from app.services.trend_input_builder import build_trend_input_from_markdown, persist_trend_input
from app.services.trend_mermaid_renderer import persist_trend_mermaid, render_trend_mermaid
from app.services.trend_summary_renderer import (
    persist_trend_summary,
    render_trend_summary_markdown,
)


@dataclass(frozen=True)
class TrendEnhancementArtifacts:
    run_id: str
    source_report_md_path: str
    source_report_docx_path: str | None
    trend_input_path: str
    trend_assessment_path: str
    trend_summary_path: str
    trend_state_graph_path: str
    output_trend_state_graph_path: str
    trend_state_graph_image_path: str | None
    chart_paths: list[str]
    augmented_report_path: str | None = None


def run_trend_enhancement(
    report_md_path: Path,
    *,
    base_report_docx_path: Path | None = None,
) -> TrendEnhancementArtifacts:
    settings = get_settings()
    run_id = _generate_run_id()
    generated_at = _utc_now_iso()
    workdir = settings.workdir_dir / run_id
    output_dir = settings.outputs_dir / run_id
    workdir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    stored_md_path = workdir / "source_report.md"
    shutil.copyfile(report_md_path, stored_md_path)

    stored_docx_path: Path | None = None
    if base_report_docx_path is not None:
        stored_docx_path = workdir / "source_report.docx"
        shutil.copyfile(base_report_docx_path, stored_docx_path)

    trend_input = build_trend_input_from_markdown(
        stored_md_path,
        run_id=run_id,
        generated_at=generated_at,
    )
    trend_input_path = workdir / "trend_input.json"
    persist_trend_input(trend_input, trend_input_path)

    trend_assessment = build_trend_assessment(
        trend_input,
        input_path=trend_input_path.as_posix(),
        generated_at=_utc_now_iso(),
    )
    trend_assessment_path = workdir / "trend_assessment.json"
    _persist_model(trend_assessment, trend_assessment_path)

    chart_artifacts = render_trend_charts(trend_input, output_dir)
    trend_mermaid = render_trend_mermaid(trend_assessment)
    trend_state_graph_path = workdir / "trend_state_graph.mmd"
    output_trend_state_graph_path = output_dir / "trend_state_graph.mmd"
    persist_trend_mermaid(trend_mermaid, trend_state_graph_path)
    persist_trend_mermaid(trend_mermaid, output_trend_state_graph_path)
    mermaid_renderer = build_mermaid_renderer(
        mode=settings.mermaid_renderer_mode,
        cli_path=settings.mermaid_cli_path,
        cli_timeout_seconds=settings.mermaid_cli_timeout_seconds,
        remote_base_url=settings.mermaid_renderer_base_url,
        remote_timeout_seconds=settings.mermaid_renderer_timeout_seconds,
    )
    mermaid_render_result = mermaid_renderer.render(
        output_trend_state_graph_path,
        output_dir / "trend_state_graph.png",
    )
    trend_state_graph_image_path = mermaid_render_result.output_path if mermaid_render_result.success else None
    trend_summary = render_trend_summary_markdown(
        trend_assessment,
        chart_filenames=[artifact.path.name for artifact in chart_artifacts],
        mermaid_source=trend_mermaid,
    )
    trend_summary_path = workdir / "trend_summary.md"
    persist_trend_summary(trend_summary, trend_summary_path)

    augmented_report_path: Path | None = None
    if stored_docx_path is not None:
        augmented_report_path = output_dir / "augmented_report.docx"
        appendix_chart_paths = [artifact.path for artifact in chart_artifacts]
        if trend_state_graph_image_path is not None:
            appendix_chart_paths.append(trend_state_graph_image_path)
        augment_report_with_trend_appendix(
            stored_docx_path,
            assessment=trend_assessment,
            chart_paths=appendix_chart_paths,
            output_path=augmented_report_path,
        )

    return TrendEnhancementArtifacts(
        run_id=run_id,
        source_report_md_path=stored_md_path.as_posix(),
        source_report_docx_path=stored_docx_path.as_posix() if stored_docx_path else None,
        trend_input_path=trend_input_path.as_posix(),
        trend_assessment_path=trend_assessment_path.as_posix(),
        trend_summary_path=trend_summary_path.as_posix(),
        trend_state_graph_path=trend_state_graph_path.as_posix(),
        output_trend_state_graph_path=output_trend_state_graph_path.as_posix(),
        trend_state_graph_image_path=trend_state_graph_image_path.as_posix() if trend_state_graph_image_path else None,
        chart_paths=[artifact.path.as_posix() for artifact in chart_artifacts],
        augmented_report_path=augmented_report_path.as_posix() if augmented_report_path else None,
    )


def _persist_model(model: TrendInputV1 | TrendAssessmentV1, target_path: Path) -> None:
    target_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _generate_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"trd_{timestamp}_{suffix}"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
