from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import shutil
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.schemas.status_analysis import StatusAnalysisEvidenceV1, StatusAnalysisSummaryV1
from app.services.resource_history_builder import materialize_resource_history_csv
from app.services.status_analysis_builder import build_status_analysis_from_directory
from app.services.status_analysis_renderer import (
    persist_status_analysis_markdown,
    render_status_analysis_markdown,
)


@dataclass(frozen=True)
class LogPreprocessingArtifacts:
    run_id: str
    source_directory_path: str
    resource_history_csv_path: str
    status_analysis_evidence_path: str
    status_analysis_summary_path: str
    status_analysis_md_path: str


def run_log_preprocessing(
    analysis_root: Path,
    *,
    run_id: str | None = None,
    reference_time: datetime | None = None,
    copy_source: bool | None = None,
    large_file_bytes: int | None = None,
    max_excerpt_lines: int | None = None,
) -> LogPreprocessingArtifacts:
    settings = get_settings()
    should_copy_source = settings.log_preprocessing_copy_source if copy_source is None else copy_source
    run_id = run_id or _generate_run_id()
    generated_at = _utc_now_iso()
    workdir = settings.workdir_dir / run_id
    output_dir = settings.outputs_dir / run_id
    workdir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_dir = analysis_root.resolve()
    if should_copy_source:
        source_dir = workdir / "source_logs"
        shutil.copytree(analysis_root.resolve(), source_dir)
        _write_collection_time_hint(analysis_root.resolve(), source_dir)

    resource_history_csv_path = workdir / "resources" / "resource_history.csv"
    materialize_resource_history_csv(
        source_dir,
        resource_history_csv_path,
        reference_time=reference_time,
    )

    evidence, summary = build_status_analysis_from_directory(
        source_dir,
        run_id=run_id,
        generated_at=generated_at,
        reference_time=reference_time,
        generated_resource_history_path=resource_history_csv_path,
        copied_source=should_copy_source,
        large_file_bytes=large_file_bytes or settings.log_preprocessing_large_file_bytes,
        max_excerpt_lines=max_excerpt_lines or settings.log_preprocessing_max_excerpt_lines,
    )

    evidence_path = workdir / "status_analysis_evidence.json"
    summary_path = workdir / "status_analysis_summary.json"
    markdown_path = workdir / "status_analysis.md"

    _persist_model(evidence, evidence_path)
    _persist_model(summary, summary_path)
    persist_status_analysis_markdown(render_status_analysis_markdown(summary), markdown_path)

    return LogPreprocessingArtifacts(
        run_id=run_id,
        source_directory_path=source_dir.as_posix(),
        resource_history_csv_path=resource_history_csv_path.as_posix(),
        status_analysis_evidence_path=evidence_path.as_posix(),
        status_analysis_summary_path=summary_path.as_posix(),
        status_analysis_md_path=markdown_path.as_posix(),
    )


def _persist_model(model: StatusAnalysisEvidenceV1 | StatusAnalysisSummaryV1, target_path: Path) -> None:
    target_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _generate_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"prep_{timestamp}_{suffix}"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_collection_time_hint(original_source_dir: Path, stored_source_dir: Path) -> None:
    metadata_dir = stored_source_dir / "metadata"
    collection_info_path = metadata_dir / "collection_info.txt"
    if collection_info_path.exists():
        return

    if match := re.search(r"-(\d{10})(?:\D*)$", original_source_dir.name):
        collected_at = datetime.fromtimestamp(int(match.group(1)), UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        metadata_dir.mkdir(parents=True, exist_ok=True)
        collection_info_path.write_text(
            f"collected_at: {collected_at}\nsource_name: {original_source_dir.name}\n",
            encoding="utf-8",
        )
