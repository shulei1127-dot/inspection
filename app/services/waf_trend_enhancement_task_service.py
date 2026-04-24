from __future__ import annotations

from json import JSONDecodeError
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.trend_assessment import TrendAssessmentV1, TrendInputV1
from app.schemas.waf_trend_enhancements import (
    WafTrendEnhancementCreateData,
    WafTrendEnhancementError,
    WafTrendEnhancementErrorResponse,
    WafTrendEnhancementSummary,
    WafTrendMetricStatuses,
)
from app.services.report_augmenter import ReportAugmentError
from app.services.trend_enhancement_service import TrendEnhancementArtifacts, run_trend_enhancement
from app.services.trend_input_builder import TrendInputBuildError


PREPROCESSING_ID_PATTERN = re.compile(r"^prep_\d{8}_\d{6}_[0-9a-f]{8}$")


class WafTrendEnhancementTaskError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}

    def to_response(self) -> WafTrendEnhancementErrorResponse:
        return WafTrendEnhancementErrorResponse(
            error=WafTrendEnhancementError(
                code=self.code,
                message=self.message,
                details=self.details,
            )
        )


def create_waf_trend_enhancement_from_preprocessing(
    *,
    preprocessing_id: str,
    base_report_docx: UploadFile | None = None,
) -> WafTrendEnhancementCreateData:
    normalized_preprocessing_id = preprocessing_id.strip()
    if not normalized_preprocessing_id:
        raise WafTrendEnhancementTaskError(
            status_code=400,
            code="missing_preprocessing_id",
            message="preprocessing_id is required.",
        )
    if not PREPROCESSING_ID_PATTERN.fullmatch(normalized_preprocessing_id):
        raise WafTrendEnhancementTaskError(
            status_code=400,
            code="invalid_preprocessing_id",
            message="preprocessing_id has an invalid format.",
            details={"preprocessing_id": normalized_preprocessing_id},
        )

    settings = get_settings()
    status_analysis_md_path = settings.workdir_dir / normalized_preprocessing_id / "status_analysis.md"
    if not status_analysis_md_path.exists():
        raise WafTrendEnhancementTaskError(
            status_code=404,
            code="preprocessing_artifact_not_found",
            message="The preprocessing status_analysis.md artifact does not exist.",
            details={
                "preprocessing_id": normalized_preprocessing_id,
                "status_analysis_md_path": status_analysis_md_path.as_posix(),
            },
        )

    stored_base_report_path: Path | None = None
    if base_report_docx is not None and base_report_docx.filename:
        stored_base_report_path = _store_base_report_docx(
            base_report_docx,
            preprocessing_id=normalized_preprocessing_id,
        )

    try:
        artifacts = run_trend_enhancement(
            status_analysis_md_path,
            base_report_docx_path=stored_base_report_path,
        )
        trend_input = _load_trend_input(Path(artifacts.trend_input_path))
        trend_assessment = _load_trend_assessment(Path(artifacts.trend_assessment_path))
    except TrendInputBuildError as exc:
        raise WafTrendEnhancementTaskError(
            status_code=400,
            code="trend_input_build_failed",
            message="Failed to build trend_input.json from the preprocessing markdown.",
            details={"preprocessing_id": normalized_preprocessing_id, "reason": str(exc)},
        ) from exc
    except ReportAugmentError as exc:
        raise WafTrendEnhancementTaskError(
            status_code=400,
            code="report_augment_failed",
            message="Failed to append the trend appendix to the uploaded DOCX report.",
            details={"preprocessing_id": normalized_preprocessing_id, "reason": str(exc)},
        ) from exc
    except OSError as exc:
        raise WafTrendEnhancementTaskError(
            status_code=500,
            code="trend_enhancement_failed",
            message="Failed to generate trend enhancement artifacts.",
            details={"preprocessing_id": normalized_preprocessing_id, "reason": str(exc)},
        ) from exc

    return _build_create_data(
        preprocessing_id=normalized_preprocessing_id,
        source_status_analysis_md_path=status_analysis_md_path,
        artifacts=artifacts,
        trend_input=trend_input,
        trend_assessment=trend_assessment,
    )


def get_waf_trend_enhancement_result(trend_id: str) -> WafTrendEnhancementCreateData:
    normalized_trend_id = _validate_trend_id(trend_id)
    settings = get_settings()
    trend_workdir = settings.workdir_dir / normalized_trend_id
    trend_output_dir = settings.outputs_dir / normalized_trend_id
    trend_input_path = trend_workdir / "trend_input.json"
    trend_assessment_path = trend_workdir / "trend_assessment.json"
    trend_input = _load_trend_input_or_404(trend_input_path, trend_id=normalized_trend_id)
    trend_assessment = _load_trend_assessment_or_404(trend_assessment_path, trend_id=normalized_trend_id)
    preprocessing_id = _extract_preprocessing_id_from_trend_input(trend_input)
    artifacts = TrendEnhancementArtifacts(
        run_id=normalized_trend_id,
        source_report_md_path=(trend_workdir / "source_report.md").as_posix(),
        source_report_docx_path=(
            (trend_workdir / "source_report.docx").as_posix()
            if (trend_workdir / "source_report.docx").exists()
            else None
        ),
        trend_input_path=trend_input_path.as_posix(),
        trend_assessment_path=trend_assessment_path.as_posix(),
        trend_summary_path=(trend_workdir / "trend_summary.md").as_posix(),
        trend_state_graph_path=(trend_workdir / "trend_state_graph.mmd").as_posix(),
        output_trend_state_graph_path=(trend_output_dir / "trend_state_graph.mmd").as_posix(),
        trend_state_graph_image_path=(
            (trend_output_dir / "trend_state_graph.png").as_posix()
            if (trend_output_dir / "trend_state_graph.png").exists()
            else None
        ),
        chart_paths=[path.as_posix() for path in sorted(trend_output_dir.glob("*_trend.png"))],
        augmented_report_path=(
            (trend_output_dir / "augmented_report.docx").as_posix()
            if (trend_output_dir / "augmented_report.docx").exists()
            else None
        ),
    )
    return _build_create_data(
        preprocessing_id=preprocessing_id,
        source_status_analysis_md_path=get_settings().workdir_dir / preprocessing_id / "status_analysis.md",
        artifacts=artifacts,
        trend_input=trend_input,
        trend_assessment=trend_assessment,
    )


def get_waf_trend_summary_path(trend_id: str) -> Path:
    normalized_trend_id = _validate_trend_id(trend_id)
    path = get_settings().workdir_dir / normalized_trend_id / "trend_summary.md"
    if not path.exists():
        raise WafTrendEnhancementTaskError(
            status_code=404,
            code="artifact_not_found",
            message="The requested trend summary markdown does not exist.",
            details={"trend_id": normalized_trend_id, "path": path.as_posix()},
        )
    return path


def get_waf_augmented_report_path(trend_id: str) -> Path:
    normalized_trend_id = _validate_trend_id(trend_id)
    path = get_settings().outputs_dir / normalized_trend_id / "augmented_report.docx"
    if not path.exists():
        raise WafTrendEnhancementTaskError(
            status_code=404,
            code="artifact_not_found",
            message="The requested augmented report does not exist.",
            details={"trend_id": normalized_trend_id, "path": path.as_posix()},
        )
    return path


def _store_base_report_docx(upload: UploadFile, *, preprocessing_id: str) -> Path:
    filename = upload.filename or ""
    if not filename.lower().endswith(".docx"):
        raise WafTrendEnhancementTaskError(
            status_code=400,
            code="invalid_report_file",
            message="The uploaded base report must be a .docx document.",
            details={"filename": filename},
        )

    settings = get_settings()
    target_path = settings.workdir_dir / preprocessing_id / "trend_base_reports" / f"{uuid.uuid4().hex[:8]}.docx"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    upload.file.seek(0)
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    upload.file.seek(0)

    if not zipfile.is_zipfile(target_path):
        raise WafTrendEnhancementTaskError(
            status_code=400,
            code="invalid_report_file",
            message="The uploaded base report is not a valid .docx document.",
            details={"filename": filename},
        )
    return target_path


def _validate_trend_id(trend_id: str) -> str:
    normalized = trend_id.strip()
    if not re.fullmatch(r"^trd_\d{8}_\d{6}_[0-9a-f]{8}$", normalized):
        raise WafTrendEnhancementTaskError(
            status_code=400,
            code="invalid_trend_id",
            message="trend_id has an invalid format.",
            details={"trend_id": trend_id},
        )
    return normalized


def _extract_preprocessing_id_from_trend_input(trend_input: TrendInputV1) -> str:
    source_path = Path(trend_input.source.path)
    for parent in [source_path, *source_path.parents]:
        if PREPROCESSING_ID_PATTERN.fullmatch(parent.name):
            return parent.name
    return "unknown"


def _build_create_data(
    *,
    preprocessing_id: str,
    source_status_analysis_md_path: Path,
    artifacts: TrendEnhancementArtifacts,
    trend_input: TrendInputV1,
    trend_assessment: TrendAssessmentV1,
) -> WafTrendEnhancementCreateData:
    return WafTrendEnhancementCreateData(
        trend_id=artifacts.run_id,
        preprocessing_id=preprocessing_id,
        source_status_analysis_md_path=source_status_analysis_md_path.as_posix(),
        source_report_md_path=artifacts.source_report_md_path,
        source_report_docx_path=artifacts.source_report_docx_path,
        trend_input_path=artifacts.trend_input_path,
        trend_assessment_path=artifacts.trend_assessment_path,
        trend_summary_path=artifacts.trend_summary_path,
        trend_state_graph_path=artifacts.trend_state_graph_path,
        output_trend_state_graph_path=artifacts.output_trend_state_graph_path,
        trend_state_graph_image_path=artifacts.trend_state_graph_image_path,
        chart_paths=artifacts.chart_paths,
        augmented_report_path=artifacts.augmented_report_path,
        summary=WafTrendEnhancementSummary(
            overall_status=trend_assessment.overall.summary_status,
            data_quality=trend_input.parse_summary.data_quality,
            metric_statuses=WafTrendMetricStatuses(
                cpu=trend_assessment.metrics.cpu.status,
                memory=trend_assessment.metrics.memory.status,
                disk=trend_assessment.metrics.disk.status,
                stability=trend_assessment.metrics.stability.status,
            ),
            chart_count=len(artifacts.chart_paths),
            warnings=list(dict.fromkeys(list(trend_input.parse_summary.warnings) + list(trend_assessment.warnings))),
        ),
    )


def _load_trend_input(path: Path) -> TrendInputV1:
    try:
        return TrendInputV1.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, ValidationError, ValueError) as exc:
        raise WafTrendEnhancementTaskError(
            status_code=500,
            code="trend_input_load_failed",
            message="Generated trend_input.json could not be loaded.",
            details={"trend_input_path": path.as_posix()},
        ) from exc


def _load_trend_input_or_404(path: Path, *, trend_id: str) -> TrendInputV1:
    if not path.exists():
        raise WafTrendEnhancementTaskError(
            status_code=404,
            code="artifact_not_found",
            message="The requested trend input artifact does not exist.",
            details={"trend_id": trend_id, "path": path.as_posix()},
        )
    return _load_trend_input(path)


def _load_trend_assessment(path: Path) -> TrendAssessmentV1:
    try:
        return TrendAssessmentV1.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, ValidationError, ValueError) as exc:
        raise WafTrendEnhancementTaskError(
            status_code=500,
            code="trend_assessment_load_failed",
            message="Generated trend_assessment.json could not be loaded.",
            details={"trend_assessment_path": path.as_posix()},
        ) from exc


def _load_trend_assessment_or_404(path: Path, *, trend_id: str) -> TrendAssessmentV1:
    if not path.exists():
        raise WafTrendEnhancementTaskError(
            status_code=404,
            code="artifact_not_found",
            message="The requested trend assessment artifact does not exist.",
            details={"trend_id": trend_id, "path": path.as_posix()},
        )
    return _load_trend_assessment(path)
