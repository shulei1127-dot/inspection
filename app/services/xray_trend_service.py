from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
import re

from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.trend_assessment import (
    TrendInputMetrics,
    TrendInputSource,
    TrendInputV1,
    TrendMetricSample,
    TrendMetricSeries,
    TrendParseSummary,
    TrendStabilityInput,
)
from app.schemas.unified_json import UnifiedJsonV1
from app.services.mermaid_renderer import build_mermaid_renderer
from app.services.report_augmenter import ReportAugmentError, augment_report_with_trend_appendix
from app.services.trend_chart_renderer import render_trend_charts
from app.services.trend_forecaster import build_trend_assessment
from app.services.trend_mermaid_renderer import persist_trend_mermaid, render_trend_mermaid
from app.services.trend_summary_renderer import (
    persist_trend_summary,
    render_trend_summary_markdown,
)


RESOURCE_HISTORY_CANDIDATES = (
    Path("resources/resource_history.csv"),
    Path("resource_history.csv"),
    Path("trend/resource_history.csv"),
    Path("resource_history/resource_history.csv"),
)


@dataclass(frozen=True)
class XrayTrendArtifacts:
    task_id: str
    trend_input_path: str
    trend_assessment_path: str
    trend_summary_path: str
    trend_state_graph_path: str
    output_trend_state_graph_path: str
    trend_state_graph_image_path: str | None
    resource_history_path: str | None
    chart_paths: list[str] = field(default_factory=list)
    augmented_report_path: str | None = None
    warnings: list[str] = field(default_factory=list)


def maybe_run_xray_trend_enhancement(
    task_id: str,
    *,
    base_report_docx_path: Path | None = None,
) -> XrayTrendArtifacts | None:
    settings = get_settings()
    if not settings.xray_trend_enhancement_enabled:
        return None

    task_root = settings.workdir_dir / task_id
    unified_json_path = task_root / "unified.json"
    if not unified_json_path.exists():
        return None

    unified_json = _load_unified_json(unified_json_path)
    if unified_json is None or not _is_xray_product(unified_json):
        return None

    return run_xray_trend_enhancement(
        task_id,
        unified_json=unified_json,
        task_root=task_root,
        base_report_docx_path=base_report_docx_path,
    )


def run_xray_trend_enhancement(
    task_id: str,
    *,
    unified_json: UnifiedJsonV1,
    task_root: Path,
    base_report_docx_path: Path | None = None,
) -> XrayTrendArtifacts:
    settings = get_settings()
    trend_workdir = task_root / "trend"
    trend_output_dir = settings.outputs_dir / task_id / "trend"
    trend_workdir.mkdir(parents=True, exist_ok=True)
    trend_output_dir.mkdir(parents=True, exist_ok=True)

    resource_history_path = _find_resource_history_csv(task_root)
    trend_input = build_xray_trend_input(
        task_id=task_id,
        task_root=task_root,
        unified_json=unified_json,
        resource_history_path=resource_history_path,
    )

    trend_input_path = trend_workdir / "trend_input.json"
    trend_input_path.write_text(trend_input.model_dump_json(indent=2), encoding="utf-8")

    trend_assessment = build_trend_assessment(
        trend_input,
        input_path=trend_input_path.as_posix(),
        generated_at=_utc_now_iso(),
    )
    trend_assessment_path = trend_workdir / "trend_assessment.json"
    trend_assessment_path.write_text(
        trend_assessment.model_dump_json(indent=2),
        encoding="utf-8",
    )

    chart_artifacts = render_trend_charts(trend_input, trend_output_dir)
    trend_mermaid = render_trend_mermaid(trend_assessment)
    trend_state_graph_path = trend_workdir / "trend_state_graph.mmd"
    output_trend_state_graph_path = trend_output_dir / "trend_state_graph.mmd"
    persist_trend_mermaid(trend_mermaid, trend_state_graph_path)
    persist_trend_mermaid(trend_mermaid, output_trend_state_graph_path)

    mermaid_renderer = build_mermaid_renderer(
        mode=settings.mermaid_renderer_mode,
        cli_path=settings.mermaid_cli_path,
        cli_timeout_seconds=settings.mermaid_cli_timeout_seconds,
        remote_base_url=settings.mermaid_renderer_base_url,
        remote_timeout_seconds=settings.mermaid_renderer_timeout_seconds,
    )
    mermaid_result = mermaid_renderer.render(
        output_trend_state_graph_path,
        trend_output_dir / "trend_state_graph.png",
    )
    trend_state_graph_image_path = (
        mermaid_result.output_path if mermaid_result.success else None
    )

    trend_summary = render_trend_summary_markdown(
        trend_assessment,
        chart_filenames=[artifact.path.name for artifact in chart_artifacts],
        mermaid_source=trend_mermaid,
    )
    trend_summary_path = trend_workdir / "trend_summary.md"
    persist_trend_summary(trend_summary, trend_summary_path)

    appendix_chart_paths = [artifact.path for artifact in chart_artifacts]
    if trend_state_graph_image_path is not None:
        appendix_chart_paths.append(trend_state_graph_image_path)

    augmented_report_path: Path | None = None
    if base_report_docx_path is not None and appendix_chart_paths:
        temp_output_path = base_report_docx_path.with_name(
            f"{base_report_docx_path.stem}.xray-trend.docx"
        )
        augment_report_with_trend_appendix(
            base_report_docx_path,
            assessment=trend_assessment,
            chart_paths=appendix_chart_paths,
            output_path=temp_output_path,
        )
        temp_output_path.replace(base_report_docx_path)
        augmented_report_path = base_report_docx_path

    return XrayTrendArtifacts(
        task_id=task_id,
        trend_input_path=trend_input_path.as_posix(),
        trend_assessment_path=trend_assessment_path.as_posix(),
        trend_summary_path=trend_summary_path.as_posix(),
        trend_state_graph_path=trend_state_graph_path.as_posix(),
        output_trend_state_graph_path=output_trend_state_graph_path.as_posix(),
        trend_state_graph_image_path=(
            trend_state_graph_image_path.as_posix()
            if trend_state_graph_image_path is not None
            else None
        ),
        resource_history_path=(
            resource_history_path.as_posix()
            if resource_history_path is not None
            else None
        ),
        chart_paths=[artifact.path.as_posix() for artifact in chart_artifacts],
        augmented_report_path=(
            augmented_report_path.as_posix()
            if augmented_report_path is not None
            else None
        ),
        warnings=list(dict.fromkeys(list(trend_input.parse_summary.warnings) + list(trend_assessment.warnings))),
    )


def build_xray_trend_input(
    *,
    task_id: str,
    task_root: Path,
    unified_json: UnifiedJsonV1,
    resource_history_path: Path | None,
) -> TrendInputV1:
    cpu_samples: list[TrendMetricSample] = []
    memory_samples: list[TrendMetricSample] = []
    disk_samples: list[TrendMetricSample] = []
    warnings: list[str] = []

    if resource_history_path is not None:
        history_samples = _load_resource_history_samples(resource_history_path, task_root=task_root)
        cpu_samples.extend(history_samples["cpu"])
        memory_samples.extend(history_samples["memory"])
        disk_samples.extend(history_samples["disk"])
    else:
        warnings.append("未检测到 xray resource_history.csv，当前仅能基于有限快照保守降级。")

    snapshot_timestamp = unified_json.generated_at
    cpu_percent = _extract_percent_from_text(str(unified_json.metadata.get("xray_mgmt_cpu") or ""))
    if cpu_percent is not None:
        cpu_samples.append(
            TrendMetricSample(
                timestamp=snapshot_timestamp,
                value=cpu_percent,
                source_excerpt="unified_json.metadata.xray_mgmt_cpu",
            )
        )
    memory_percent = _extract_percent_from_text(str(unified_json.metadata.get("xray_mgmt_memory") or ""))
    if memory_percent is not None:
        memory_samples.append(
            TrendMetricSample(
                timestamp=snapshot_timestamp,
                value=memory_percent,
                source_excerpt="unified_json.metadata.xray_mgmt_memory",
            )
        )
    disk_percent = _extract_percent_from_text(str(unified_json.metadata.get("xray_mgmt_disk") or ""))
    if disk_percent is not None:
        disk_samples.append(
            TrendMetricSample(
                timestamp=snapshot_timestamp,
                value=disk_percent,
                source_excerpt="unified_json.metadata.xray_mgmt_disk",
            )
        )

    cpu_samples = _dedupe_samples(cpu_samples)
    memory_samples = _dedupe_samples(memory_samples)
    disk_samples = _dedupe_samples(disk_samples)

    if len(cpu_samples) < 2:
        warnings.append("Xray CPU 历史点少于 2 个，当前不会生成 CPU 趋势图。")
    if len(memory_samples) < 2:
        warnings.append("Xray 内存历史点少于 2 个，当前不会生成内存趋势图。")
    if len(disk_samples) < 2:
        warnings.append("Xray 磁盘历史点少于 2 个，当前不会生成磁盘趋势图。")

    time_points_detected = len(
        {
            sample.timestamp
            for sample in [*cpu_samples, *memory_samples, *disk_samples]
        }
    )
    data_quality = _determine_data_quality(
        cpu_samples=cpu_samples,
        memory_samples=memory_samples,
        disk_samples=disk_samples,
    )

    return TrendInputV1(
        run_id=f"{task_id}_trend",
        generated_at=_utc_now_iso(),
        source=TrendInputSource(
            type="xray-task-v1",
            path=(resource_history_path or task_root).as_posix(),
        ),
        parse_summary=TrendParseSummary(
            warnings=warnings,
            time_points_detected=time_points_detected,
            data_quality=data_quality,
        ),
        metrics=TrendInputMetrics(
            cpu=TrendMetricSeries(samples=cpu_samples),
            memory=TrendMetricSeries(samples=memory_samples),
            disk=TrendMetricSeries(samples=disk_samples),
        ),
        stability=TrendStabilityInput(),
    )


def _find_resource_history_csv(task_root: Path) -> Path | None:
    for relative_path in RESOURCE_HISTORY_CANDIDATES:
        candidate = task_root / relative_path
        if candidate.is_file():
            return candidate

    fallback_candidates = sorted(
        path for path in task_root.rglob("resource_history.csv") if path.is_file()
    )
    if fallback_candidates:
        return fallback_candidates[0]
    return None


def _load_resource_history_samples(
    resource_history_path: Path,
    *,
    task_root: Path,
) -> dict[str, list[TrendMetricSample]]:
    samples: dict[str, list[TrendMetricSample]] = {"cpu": [], "memory": [], "disk": []}
    with resource_history_path.open(encoding="utf-8", newline="") as buffer:
        reader = csv.DictReader(buffer)
        for row in reader:
            timestamp = (row.get("timestamp") or "").strip()
            if not timestamp:
                continue
            source_excerpt = resource_history_path.relative_to(task_root).as_posix()
            for metric_name, column_name in [("cpu", "cpu"), ("memory", "memory"), ("disk", "disk")]:
                raw_value = (row.get(column_name) or "").strip()
                if not raw_value:
                    continue
                try:
                    value = float(raw_value)
                except ValueError:
                    continue
                samples[metric_name].append(
                    TrendMetricSample(
                        timestamp=timestamp,
                        value=value,
                        source_excerpt=source_excerpt,
                    )
                )
    return samples


def _dedupe_samples(samples: list[TrendMetricSample]) -> list[TrendMetricSample]:
    deduped: dict[tuple[str, float], TrendMetricSample] = {}
    for sample in samples:
        deduped[(sample.timestamp, sample.value)] = sample
    return sorted(deduped.values(), key=lambda sample: sample.timestamp)


def _determine_data_quality(
    *,
    cpu_samples: list[TrendMetricSample],
    memory_samples: list[TrendMetricSample],
    disk_samples: list[TrendMetricSample],
) -> str:
    multi_point_metrics = sum(
        1
        for samples in [cpu_samples, memory_samples, disk_samples]
        if len(samples) >= 2
    )
    if multi_point_metrics >= 2:
        return "sufficient"
    if any([cpu_samples, memory_samples, disk_samples]):
        return "partial"
    return "insufficient"


def _extract_percent_from_text(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)%", value)
    if not match:
        return None
    return float(match.group(1))


def _is_xray_product(unified_json: UnifiedJsonV1) -> bool:
    return str(unified_json.metadata.get("product_type")).strip().lower() == "xray"


def _load_unified_json(path: Path) -> UnifiedJsonV1 | None:
    try:
        return UnifiedJsonV1.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, ValidationError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
