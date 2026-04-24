from __future__ import annotations

from datetime import UTC, datetime
from json import JSONDecodeError
import re
import shutil
import tarfile
import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.schemas.status_analysis import StatusAnalysisSummaryV1
from app.schemas.waf_preprocessing import (
    WafPreprocessingCreateData,
    WafPreprocessingError,
    WafPreprocessingErrorResponse,
    WafPreprocessingSummary,
)
from app.services.log_preprocessing_service import LogPreprocessingArtifacts, run_log_preprocessing
from app.services.status_analysis_builder import StatusAnalysisBuildError


SUPPORTED_WAF_PREPROCESSING_ARCHIVE_MESSAGE = "Only .zip, .tar.gz, .tgz, and .gz WAF log archives are accepted."
PREPROCESSING_ID_PATTERN = re.compile(r"^prep_\d{8}_\d{6}_[0-9a-f]{8}$")


class WafPreprocessingTaskError(Exception):
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

    def to_response(self) -> WafPreprocessingErrorResponse:
        return WafPreprocessingErrorResponse(
            error=WafPreprocessingError(
                code=self.code,
                message=self.message,
                details=self.details,
            )
        )


def create_waf_preprocessing_from_upload(
    upload: UploadFile | None,
    *,
    reference_time: str | None = None,
    copy_source: bool | None = None,
) -> WafPreprocessingCreateData:
    if upload is None or not (upload.filename or ""):
        raise WafPreprocessingTaskError(
            status_code=400,
            code="missing_file",
            message="No WAF log archive file was provided.",
        )

    filename = upload.filename or ""
    archive_suffix = _detect_archive_suffix(filename)
    if archive_suffix is None:
        raise WafPreprocessingTaskError(
            status_code=415,
            code="unsupported_archive_type",
            message=SUPPORTED_WAF_PREPROCESSING_ARCHIVE_MESSAGE,
            details={"filename": filename},
        )

    parsed_reference_time = _parse_reference_time(reference_time)
    settings = get_settings()
    preprocessing_id = _generate_preprocessing_id()
    archive_path = settings.uploads_dir / f"{preprocessing_id}{archive_suffix}"
    extracted_dir = settings.workdir_dir / preprocessing_id / "extracted"

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    try:
        _save_upload(upload, archive_path)
        _validate_archive_file(archive_path, filename, archive_suffix=archive_suffix)
        _extract_archive(archive_path, extracted_dir, filename, archive_suffix=archive_suffix)
        analysis_root = _resolve_analysis_root(extracted_dir)
        artifacts = run_log_preprocessing(
            analysis_root,
            run_id=preprocessing_id,
            reference_time=parsed_reference_time,
            copy_source=copy_source,
        )
        summary = _load_preprocessing_summary(Path(artifacts.status_analysis_summary_path))
    except WafPreprocessingTaskError:
        raise
    except StatusAnalysisBuildError as exc:
        raise WafPreprocessingTaskError(
            status_code=400,
            code="waf_preprocessing_failed",
            message="Failed to build status analysis from uploaded WAF logs.",
            details={"filename": filename, "reason": str(exc), "preprocessing_id": preprocessing_id},
        ) from exc
    except OSError as exc:
        raise WafPreprocessingTaskError(
            status_code=500,
            code="internal_error",
            message="Failed to persist or preprocess the uploaded WAF log archive.",
            details={"filename": filename, "reason": str(exc), "preprocessing_id": preprocessing_id},
        ) from exc

    return _build_create_data(
        preprocessing_id=preprocessing_id,
        filename=filename,
        archive_path=archive_path,
        extracted_dir=extracted_dir,
        artifacts=artifacts,
        summary=summary,
    )


def get_waf_preprocessing_result(preprocessing_id: str) -> WafPreprocessingCreateData:
    normalized_preprocessing_id = _validate_preprocessing_id(preprocessing_id)
    settings = get_settings()
    summary_path = settings.workdir_dir / normalized_preprocessing_id / "status_analysis_summary.json"
    summary = _load_preprocessing_summary_or_404(summary_path, preprocessing_id=normalized_preprocessing_id)
    artifacts = _build_artifacts_from_id(normalized_preprocessing_id, settings.workdir_dir)
    archive_path = _find_preprocessing_archive_path(normalized_preprocessing_id, settings.uploads_dir)
    return _build_create_data(
        preprocessing_id=normalized_preprocessing_id,
        filename=archive_path.name if archive_path is not None else normalized_preprocessing_id,
        archive_path=archive_path or settings.uploads_dir / normalized_preprocessing_id,
        extracted_dir=settings.workdir_dir / normalized_preprocessing_id / "extracted",
        artifacts=artifacts,
        summary=summary,
    )


def get_waf_status_analysis_path(preprocessing_id: str) -> Path:
    normalized_preprocessing_id = _validate_preprocessing_id(preprocessing_id)
    path = get_settings().workdir_dir / normalized_preprocessing_id / "status_analysis.md"
    if not path.exists():
        raise WafPreprocessingTaskError(
            status_code=404,
            code="artifact_not_found",
            message="The requested status analysis markdown does not exist.",
            details={"preprocessing_id": normalized_preprocessing_id, "path": path.as_posix()},
        )
    return path


def _build_create_data(
    *,
    preprocessing_id: str,
    filename: str,
    archive_path: Path,
    extracted_dir: Path,
    artifacts: LogPreprocessingArtifacts,
    summary: StatusAnalysisSummaryV1,
) -> WafPreprocessingCreateData:
    return WafPreprocessingCreateData(
        preprocessing_id=preprocessing_id,
        filename=filename,
        source_archive_path=archive_path.as_posix(),
        extracted_dir_path=extracted_dir.as_posix(),
        source_directory_path=artifacts.source_directory_path,
        resource_history_csv_path=artifacts.resource_history_csv_path,
        status_analysis_evidence_path=artifacts.status_analysis_evidence_path,
        status_analysis_summary_path=artifacts.status_analysis_summary_path,
        status_analysis_md_path=artifacts.status_analysis_md_path,
        summary=WafPreprocessingSummary(
            coverage_level=summary.coverage_level,
            resource_history_point_count=len(summary.resource_time_series),
            stability_event_count=len(summary.recent_stability_events),
            service_finding_count=len(summary.service_findings),
            warnings=list(summary.warnings) + list(summary.coverage_warnings),
        ),
    )


def _validate_preprocessing_id(preprocessing_id: str) -> str:
    normalized = preprocessing_id.strip()
    if not PREPROCESSING_ID_PATTERN.fullmatch(normalized):
        raise WafPreprocessingTaskError(
            status_code=400,
            code="invalid_preprocessing_id",
            message="preprocessing_id has an invalid format.",
            details={"preprocessing_id": preprocessing_id},
        )
    return normalized


def _build_artifacts_from_id(preprocessing_id: str, workdir_dir: Path) -> LogPreprocessingArtifacts:
    workdir = workdir_dir / preprocessing_id
    return LogPreprocessingArtifacts(
        run_id=preprocessing_id,
        source_directory_path=_resolve_existing_source_directory(workdir).as_posix(),
        resource_history_csv_path=(workdir / "resources" / "resource_history.csv").as_posix(),
        status_analysis_evidence_path=(workdir / "status_analysis_evidence.json").as_posix(),
        status_analysis_summary_path=(workdir / "status_analysis_summary.json").as_posix(),
        status_analysis_md_path=(workdir / "status_analysis.md").as_posix(),
    )


def _resolve_existing_source_directory(workdir: Path) -> Path:
    source_logs = workdir / "source_logs"
    if source_logs.exists():
        return source_logs
    extracted = workdir / "extracted"
    if extracted.exists():
        return _resolve_analysis_root(extracted)
    return workdir


def _find_preprocessing_archive_path(preprocessing_id: str, uploads_dir: Path) -> Path | None:
    for suffix in (".tar.gz", ".tgz", ".zip", ".gz"):
        candidate = uploads_dir / f"{preprocessing_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _detect_archive_suffix(filename: str) -> str | None:
    lowered = filename.lower()
    for suffix in (".tar.gz", ".tgz", ".zip", ".gz"):
        if lowered.endswith(suffix):
            return suffix
    return None


def _generate_preprocessing_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"prep_{timestamp}_{suffix}"


def _parse_reference_time(raw_value: str | None) -> datetime | None:
    if raw_value is None or not raw_value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise WafPreprocessingTaskError(
            status_code=400,
            code="invalid_reference_time",
            message="reference_time must be an ISO timestamp.",
            details={"reference_time": raw_value},
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _save_upload(upload: UploadFile, target_path: Path) -> None:
    upload.file.seek(0)
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    upload.file.seek(0)


def _validate_archive_file(
    archive_path: Path,
    filename: str,
    *,
    archive_suffix: str,
) -> None:
    if archive_suffix == ".zip":
        if not zipfile.is_zipfile(archive_path):
            raise WafPreprocessingTaskError(
                status_code=400,
                code="invalid_archive",
                message="The uploaded WAF log archive is not valid.",
                details={"filename": filename},
            )
        return
    if not tarfile.is_tarfile(archive_path):
        raise WafPreprocessingTaskError(
            status_code=400,
            code="invalid_archive",
            message="The uploaded WAF log archive is not valid.",
            details={"filename": filename},
        )


def _extract_archive(
    archive_path: Path,
    target_dir: Path,
    filename: str,
    *,
    archive_suffix: str,
) -> None:
    root = target_dir.resolve()
    try:
        if archive_suffix == ".zip":
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    destination = (target_dir / member.filename).resolve()
                    if destination != root and root not in destination.parents:
                        raise WafPreprocessingTaskError(
                            status_code=400,
                            code="extract_failed",
                            message="Failed to extract the uploaded WAF log archive.",
                            details={"filename": filename, "reason": "unsafe_archive_path"},
                        )
                archive.extractall(target_dir)
            return

        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                destination = (target_dir / member.name).resolve()
                if destination != root and root not in destination.parents:
                    raise WafPreprocessingTaskError(
                        status_code=400,
                        code="extract_failed",
                        message="Failed to extract the uploaded WAF log archive.",
                        details={"filename": filename, "reason": "unsafe_archive_path"},
                    )
            archive.extractall(target_dir, filter="data")
    except WafPreprocessingTaskError:
        raise
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
        raise WafPreprocessingTaskError(
            status_code=400,
            code="extract_failed",
            message="Failed to extract the uploaded WAF log archive.",
            details={"filename": filename, "reason": str(exc)},
        ) from exc


def _resolve_analysis_root(extracted_dir: Path) -> Path:
    children = [path for path in extracted_dir.iterdir() if path.name != "__MACOSX"]
    directories = [path for path in children if path.is_dir()]
    files = [path for path in children if path.is_file()]
    if len(directories) == 1 and not files:
        return directories[0]
    return extracted_dir


def _load_preprocessing_summary(summary_path: Path) -> StatusAnalysisSummaryV1:
    try:
        return StatusAnalysisSummaryV1.model_validate_json(summary_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, ValueError) as exc:
        raise WafPreprocessingTaskError(
            status_code=500,
            code="summary_load_failed",
            message="Generated WAF preprocessing summary could not be loaded.",
            details={"summary_path": summary_path.as_posix()},
        ) from exc


def _load_preprocessing_summary_or_404(
    summary_path: Path,
    *,
    preprocessing_id: str,
) -> StatusAnalysisSummaryV1:
    if not summary_path.exists():
        raise WafPreprocessingTaskError(
            status_code=404,
            code="artifact_not_found",
            message="The requested WAF preprocessing summary does not exist.",
            details={"preprocessing_id": preprocessing_id, "path": summary_path.as_posix()},
        )
    return _load_preprocessing_summary(summary_path)
