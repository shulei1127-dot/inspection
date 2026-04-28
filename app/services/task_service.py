import shutil
import tarfile
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
import json
from json import JSONDecodeError
from pathlib import Path

from fastapi import UploadFile
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.unified_json import UnifiedJsonV1
from app.schemas.tasks import (
    TaskCleanupData,
    TaskCleanupOptions,
    TaskCreateData,
    TaskCreateOptions,
    TaskDeleteData,
    TaskError,
    TaskErrorResponse,
    TaskResultData,
    TaskSummary,
)
from app.schemas.log_analyzer import AnalyzeDirectorySource, AnalyzeRequestV1
from app.services.log_analyzer import LogAnalyzerError, build_log_analyzer
from app.services.parser_stub import persist_unified_json
from app.services.report_payload_mapper import (
    map_unified_json_to_report_payload,
    persist_report_payload,
)
from app.services.report_rendering_service import (
    ReportRenderResult,
    maybe_render_report_from_payload_file,
)
from app.services.report_template_selector import (
    resolve_report_template_path_for_unified_json,
)
from app.services.xray_llm_section_service import maybe_apply_xray_llm_sections
from app.services.task_repository import (
    TaskRecord,
    create_task_record,
    delete_task_record,
    get_task_record,
    list_task_records,
    update_task_record,
)


class TaskUploadError(Exception):
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

    def to_response(self) -> TaskErrorResponse:
        return TaskErrorResponse(
            error=TaskError(
                code=self.code,
                message=self.message,
                details=self.details,
            )
        )


class TaskLookupError(Exception):
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

    def to_response(self) -> TaskErrorResponse:
        return TaskErrorResponse(
            error=TaskError(
                code=self.code,
                message=self.message,
                details=self.details,
            )
        )


SUPPORTED_UPLOAD_ARCHIVE_MESSAGE = (
    "Only .zip, .tar.gz, .tgz, and the native xray minion_report.gz archive are accepted."
)
NATIVE_XRAY_MINION_REPORT_FILENAME = "minion_report.gz"
STORED_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".zip", ".gz")


def create_task_from_upload(upload: UploadFile | None, options: TaskCreateOptions) -> TaskCreateData:
    if upload is None:
        raise TaskUploadError(
            status_code=400,
            code="missing_file",
            message="No upload file was provided.",
        )

    filename = upload.filename or ""
    if not filename:
        raise TaskUploadError(
            status_code=400,
            code="missing_file",
            message="No upload file was provided.",
        )

    archive_suffix = _detect_upload_archive_suffix(filename)
    if archive_suffix is None:
        raise TaskUploadError(
            status_code=415,
            code="unsupported_media_type",
            message=SUPPORTED_UPLOAD_ARCHIVE_MESSAGE,
            details={"filename": filename},
        )

    settings = get_settings()
    task_id = generate_task_id()
    archive_path = settings.uploads_dir / f"{task_id}{archive_suffix}"
    task_workdir = settings.workdir_dir / task_id
    unified_json_path = task_workdir / "unified.json"
    report_payload_path = task_workdir / "report_payload.json"
    report_file_path: str | None = None

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    task_workdir.mkdir(parents=True, exist_ok=True)
    create_task_record(
        task_id=task_id,
        status="analyzing",
        archive_path=archive_path.as_posix(),
        workdir_path=task_workdir.as_posix(),
    )

    try:
        _save_upload(upload, archive_path)
        _validate_archive_file(archive_path, filename, archive_suffix=archive_suffix)
        _extract_archive(archive_path, task_workdir, filename, archive_suffix=archive_suffix)
        analyze_request = AnalyzeRequestV1(
            task_id=task_id,
            source=AnalyzeDirectorySource(path=task_workdir.resolve().as_posix()),
            archive_name=filename,
            archive_size_bytes=archive_path.stat().st_size,
        )
        analyze_response = build_log_analyzer().analyze(analyze_request)
        unified_json = analyze_response.result
        persist_unified_json(unified_json, unified_json_path)
        update_task_record(
            task_id,
            unified_json_path=unified_json_path.as_posix(),
            error_code=None,
            error_message=None,
            error_details=None,
        )
        report_payload = map_unified_json_to_report_payload(
            unified_json,
            report_lang=options.report_lang,
        )
        maybe_apply_xray_llm_sections(
            report_payload,
            unified_json=unified_json,
        )
        persist_report_payload(report_payload, report_payload_path)
        update_task_record(
            task_id,
            status="completed",
            unified_json_path=unified_json_path.as_posix(),
            report_payload_path=report_payload_path.as_posix(),
            report_file_path=None,
            error_code=None,
            error_message=None,
            error_details=None,
        )
        render_result = maybe_render_report_from_payload_file(
            task_id,
            report_payload_path,
            **_build_optional_render_kwargs(
                resolve_report_template_path_for_unified_json(unified_json)
            ),
        )
        result_status = "completed"
        if render_result.success and render_result.output_path is not None:
            report_file_path = render_result.output_path.as_posix()
            result_status = "rendered"
        elif render_result.attempted:
            result_status = "render_failed"
        _record_render_result(task_id, render_result)
    except LogAnalyzerError as exc:
        update_task_record(
            task_id,
            status="analyze_failed",
            error_code=exc.code,
            error_message=exc.message,
            error_details=_serialize_error_details(exc.details),
        )
        raise TaskUploadError(
            status_code=503,
            code=exc.code,
            message=exc.message,
            details={**exc.details, "task_id": task_id},
        ) from exc
    except TaskUploadError as exc:
        _cleanup_failed_task(archive_path, task_workdir)
        update_task_record(
            task_id,
            status="analyze_failed",
            unified_json_path=None,
            report_payload_path=None,
            report_file_path=None,
            error_code=exc.code,
            error_message=exc.message,
            error_details=_serialize_error_details(exc.details),
        )
        exc.details.setdefault("task_id", task_id)
        raise
    except OSError as exc:
        _cleanup_failed_task(archive_path, task_workdir)
        update_task_record(
            task_id,
            status="analyze_failed",
            unified_json_path=None,
            report_payload_path=None,
            report_file_path=None,
            error_code="internal_error",
            error_message="Failed to persist the uploaded task files.",
            error_details=_serialize_error_details(
                {"filename": filename, "reason": str(exc), "task_id": task_id}
            ),
        )
        raise TaskUploadError(
            status_code=500,
            code="internal_error",
            message="Failed to persist the uploaded task files.",
            details={"filename": filename, "reason": str(exc), "task_id": task_id},
        ) from exc

    return TaskCreateData(
        task_id=task_id,
        status=result_status,
        filename=filename,
        parser_profile=options.parser_profile,
        report_lang=options.report_lang,
        stored_zip_path=archive_path.as_posix(),
        workdir_path=task_workdir.as_posix(),
        unified_json_path=unified_json_path.as_posix(),
        report_payload_path=report_payload_path.as_posix(),
        report_file_path=report_file_path,
        summary=TaskSummary(
            service_count=unified_json.summary.service_count,
            container_count=unified_json.summary.container_count,
            issue_count=unified_json.summary.issue_count,
        ),
    )


def generate_task_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"tsk_{timestamp}_{suffix}"


def get_task_result(task_id: str) -> TaskResultData:
    task_record = get_task_record(task_id)
    if task_record is not None:
        return _task_result_from_record(task_record)

    artifact_paths = _resolve_task_paths(task_id)
    _ensure_task_exists(task_id, artifact_paths=artifact_paths)
    summary = _load_task_summary(artifact_paths["unified_json_path"])
    status = _derive_task_status(
        unified_json_path=artifact_paths["unified_json_path"],
        report_payload_path=artifact_paths["report_payload_path"],
        report_file_path=artifact_paths["report_file_path"],
    )

    return TaskResultData(
        task_id=task_id,
        status=status,
        created_at=_derive_task_created_at(task_id, artifact_paths=artifact_paths),
        unified_json_path=(
            artifact_paths["unified_json_path"].as_posix()
            if artifact_paths["unified_json_path"].exists()
            else None
        ),
        report_payload_path=(
            artifact_paths["report_payload_path"].as_posix()
            if artifact_paths["report_payload_path"].exists()
            else None
        ),
        report_file_path=(
            artifact_paths["report_file_path"].as_posix()
            if artifact_paths["report_file_path"].exists()
            else None
        ),
        summary=summary,
        error=None,
    )


def list_task_results() -> list[TaskResultData]:
    task_records = list_task_records()
    task_results = [_task_result_from_record(task_record) for task_record in task_records]

    settings = get_settings()
    task_ids = _discover_task_ids(
        uploads_dir=settings.uploads_dir,
        workdir_dir=settings.workdir_dir,
        outputs_dir=settings.outputs_dir,
    )
    database_task_ids = {task_record.task_id for task_record in task_records}

    task_results.extend(
        get_task_result(task_id)
        for task_id in task_ids
        if task_id not in database_task_ids
    )
    task_results.sort(
        key=lambda result: _task_sort_key(result),
        reverse=True,
    )
    return task_results


def get_task_report_path(task_id: str) -> Path:
    task_record = get_task_record(task_id)
    report_file_path = _resolve_task_paths(task_id, task_record=task_record)["report_file_path"]
    if not report_file_path.exists():
        raise TaskLookupError(
            status_code=404,
            code="report_not_found",
            message="Rendered report file does not exist.",
            details={"task_id": task_id},
        )
    return report_file_path


def delete_task(task_id: str) -> TaskDeleteData:
    task_record = get_task_record(task_id)
    artifact_paths = _resolve_task_paths(task_id, task_record=task_record)

    if task_record is None:
        _ensure_task_exists(task_id, artifact_paths=artifact_paths)

    deleted_paths: list[str] = []

    stored_zip_path = artifact_paths["stored_zip_path"]
    if stored_zip_path.exists():
        stored_zip_path.unlink()
        deleted_paths.append(stored_zip_path.as_posix())

    task_workdir = artifact_paths["task_workdir"]
    if task_workdir.exists():
        shutil.rmtree(task_workdir)
        deleted_paths.append(task_workdir.as_posix())

    outputs_dir = artifact_paths["outputs_task_dir"]
    if outputs_dir.exists():
        shutil.rmtree(outputs_dir)
        deleted_paths.append(outputs_dir.as_posix())

    delete_task_record(task_id)

    return TaskDeleteData(
        task_id=task_id,
        deleted=True,
        deleted_paths=deleted_paths,
    )


def cleanup_tasks(options: TaskCleanupOptions) -> TaskCleanupData:
    task_results = list_task_results()
    safe_task_results = [
        task_result
        for task_result in task_results
        if task_result.status in {"rendered", "completed", "render_failed", "analyze_failed", "failed"}
    ]

    kept_task_ids: set[str] = set()
    if options.keep_latest is not None:
        kept_task_ids = {
            task_result.task_id
            for task_result in safe_task_results[: options.keep_latest]
        }

    deleted_task_ids: list[str] = []

    for task_result in task_results:
        if task_result.status not in {"rendered", "completed", "render_failed", "analyze_failed", "failed"}:
            continue

        if task_result.task_id in kept_task_ids:
            continue

        if options.older_than_days is not None and not _is_older_than_days(
            task_result.created_at,
            days=options.older_than_days,
        ):
            continue

        try:
            delete_task(task_result.task_id)
        except TaskLookupError:
            continue

        deleted_task_ids.append(task_result.task_id)

    return TaskCleanupData(
        scanned_count=len(task_results),
        deleted_count=len(deleted_task_ids),
        skipped_count=len(task_results) - len(deleted_task_ids),
        deleted_task_ids=deleted_task_ids,
    )


def record_task_render_result(task_id: str, render_result: ReportRenderResult) -> None:
    _record_render_result(task_id, render_result)


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
            raise TaskUploadError(
                status_code=400,
                code="invalid_archive",
                message="The uploaded file is not a valid supported archive.",
                details={"filename": filename},
            )
        return

    if not tarfile.is_tarfile(archive_path):
        raise TaskUploadError(
            status_code=400,
            code="invalid_archive",
            message="The uploaded file is not a valid supported archive.",
            details={"filename": filename},
        )


def _extract_archive(
    archive_path: Path,
    target_dir: Path,
    filename: str,
    *,
    archive_suffix: str,
) -> None:
    if archive_suffix == ".zip":
        _extract_zip_archive(archive_path, target_dir, filename)
        return

    _extract_tar_archive(archive_path, target_dir, filename)


def _extract_zip_archive(archive_path: Path, target_dir: Path, filename: str) -> None:
    root = target_dir.resolve()

    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                destination = (target_dir / member.filename).resolve()
                if destination != root and root not in destination.parents:
                    raise TaskUploadError(
                        status_code=500,
                        code="extract_failed",
                        message="Failed to extract the uploaded zip archive.",
                        details={"filename": filename, "reason": "unsafe_archive_path"},
                    )

            archive.extractall(target_dir)
    except TaskUploadError:
        raise
    except zipfile.BadZipFile as exc:
        raise TaskUploadError(
            status_code=400,
            code="invalid_archive",
            message="The uploaded file is not a valid supported archive.",
            details={"filename": filename},
        ) from exc
    except OSError as exc:
        raise TaskUploadError(
            status_code=500,
            code="extract_failed",
            message="Failed to extract the uploaded archive.",
            details={"filename": filename, "reason": str(exc)},
        ) from exc


def _extract_tar_archive(archive_path: Path, target_dir: Path, filename: str) -> None:
    root = target_dir.resolve()

    try:
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                destination = (target_dir / member.name).resolve()
                if destination != root and root not in destination.parents:
                    raise TaskUploadError(
                        status_code=500,
                        code="extract_failed",
                        message="Failed to extract the uploaded archive.",
                        details={"filename": filename, "reason": "unsafe_archive_path"},
                    )

            archive.extractall(target_dir, filter="data")
    except TaskUploadError:
        raise
    except tarfile.TarError as exc:
        raise TaskUploadError(
            status_code=400,
            code="invalid_archive",
            message="The uploaded file is not a valid supported archive.",
            details={"filename": filename},
        ) from exc
    except OSError as exc:
        raise TaskUploadError(
            status_code=500,
            code="extract_failed",
            message="Failed to extract the uploaded archive.",
            details={"filename": filename, "reason": str(exc)},
        ) from exc


def _cleanup_failed_task(archive_path: Path, task_workdir: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()
    if task_workdir.exists():
        shutil.rmtree(task_workdir)


def _build_optional_render_kwargs(template_path: Path) -> dict[str, Path]:
    settings = get_settings()
    if template_path == settings.default_report_template_path:
        return {}
    return {"template_path": template_path}


def _load_task_summary(unified_json_path: Path) -> TaskSummary:
    if not unified_json_path.exists():
        return TaskSummary()

    try:
        unified_json = UnifiedJsonV1.model_validate_json(
            unified_json_path.read_text(encoding="utf-8")
        )
    except (OSError, JSONDecodeError, ValidationError):
        return TaskSummary()

    return TaskSummary(
        service_count=unified_json.summary.service_count,
        container_count=unified_json.summary.container_count,
        issue_count=unified_json.summary.issue_count,
    )


def _resolve_task_paths(
    task_id: str,
    task_record: TaskRecord | None = None,
) -> dict[str, Path]:
    settings = get_settings()
    task_workdir = _path_from_record(task_record.workdir_path) if task_record else None
    outputs_task_dir = (
        _path_from_record(task_record.report_file_path).parent
        if task_record is not None and task_record.report_file_path is not None
        else None
    )
    resolved_task_workdir = task_workdir or settings.workdir_dir / task_id
    resolved_outputs_task_dir = outputs_task_dir or settings.outputs_dir / task_id
    fallback_archive_path = _find_fallback_archive_path(task_id, uploads_dir=settings.uploads_dir)
    return {
        "stored_zip_path": (
            _path_from_record(task_record.archive_path)
            if task_record is not None and task_record.archive_path is not None
            else fallback_archive_path
        ),
        "task_workdir": resolved_task_workdir,
        "unified_json_path": (
            _path_from_record(task_record.unified_json_path)
            if task_record is not None and task_record.unified_json_path is not None
            else resolved_task_workdir / "unified.json"
        ),
        "report_payload_path": (
            _path_from_record(task_record.report_payload_path)
            if task_record is not None and task_record.report_payload_path is not None
            else resolved_task_workdir / "report_payload.json"
        ),
        "outputs_task_dir": resolved_outputs_task_dir,
        "report_file_path": (
            _path_from_record(task_record.report_file_path)
            if task_record is not None and task_record.report_file_path is not None
            else resolved_outputs_task_dir / "report.docx"
        ),
    }


def _ensure_task_exists(task_id: str, *, artifact_paths: dict[str, Path]) -> None:
    if not any(path.exists() for path in artifact_paths.values()):
        raise TaskLookupError(
            status_code=404,
            code="task_not_found",
            message="Task result does not exist.",
            details={"task_id": task_id},
        )


def _derive_task_status(
    *,
    unified_json_path: Path,
    report_payload_path: Path,
    report_file_path: Path,
) -> str:
    if report_file_path.exists():
        return "rendered"
    if unified_json_path.exists() and report_payload_path.exists():
        return "completed"
    return "analyzing"


def _derive_task_created_at(task_id: str, *, artifact_paths: dict[str, Path]) -> str | None:
    parsed_from_task_id = _parse_created_at_from_task_id(task_id)
    if parsed_from_task_id is not None:
        return parsed_from_task_id

    mtimes = [
        path.stat().st_mtime
        for path in artifact_paths.values()
        if path.exists()
    ]
    if not mtimes:
        return None

    latest_mtime = max(mtimes)
    return (
        datetime.fromtimestamp(latest_mtime, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_created_at_from_task_id(task_id: str) -> str | None:
    parts = task_id.split("_")
    if len(parts) < 4 or parts[0] != "tsk":
        return None

    timestamp = f"{parts[1]}_{parts[2]}"
    try:
        parsed = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _discover_task_ids(
    *,
    uploads_dir: Path,
    workdir_dir: Path,
    outputs_dir: Path,
) -> list[str]:
    task_ids: set[str] = set()

    if uploads_dir.exists():
        for path in uploads_dir.iterdir():
            if path.is_file():
                task_id = _task_id_from_archive_name(path.name)
                if task_id is not None:
                    task_ids.add(task_id)

    if workdir_dir.exists():
        for path in workdir_dir.iterdir():
            if path.is_dir() and path.name.startswith("tsk_"):
                task_ids.add(path.name)

    if outputs_dir.exists():
        for path in outputs_dir.iterdir():
            if path.is_dir() and path.name.startswith("tsk_"):
                task_ids.add(path.name)

    return sorted(task_ids)


def _task_sort_key(task_result: TaskResultData) -> tuple[str, str]:
    return (task_result.created_at or "", task_result.task_id)


def _is_older_than_days(created_at: str | None, *, days: int) -> bool:
    parsed_created_at = _parse_iso_datetime(created_at)
    if parsed_created_at is None:
        return False
    return parsed_created_at <= _utc_now() - timedelta(days=days)


def _task_result_from_record(task_record: TaskRecord) -> TaskResultData:
    summary = TaskSummary()
    if task_record.unified_json_path is not None:
        summary = _load_task_summary(Path(task_record.unified_json_path))

    return TaskResultData(
        task_id=task_record.task_id,
        status=task_record.status,
        created_at=task_record.created_at,
        unified_json_path=task_record.unified_json_path,
        report_payload_path=task_record.report_payload_path,
        report_file_path=task_record.report_file_path,
        summary=summary,
        error=_task_error_from_record(task_record),
    )


def _record_render_result(task_id: str, render_result: ReportRenderResult) -> None:
    if render_result.success and render_result.output_path is not None:
        update_task_record(
            task_id,
            status="rendered",
            report_file_path=render_result.output_path.as_posix(),
            error_code=None,
            error_message=None,
            error_details=None,
        )
        return

    if render_result.attempted:
        update_task_record(
            task_id,
            status="render_failed",
            error_code=render_result.error_code,
            error_message=render_result.error_message,
            error_details=_serialize_error_details(render_result.details),
        )


def _path_from_record(path_value: str | None) -> Path:
    if path_value is None:
        raise ValueError("path_value cannot be None")
    return Path(path_value)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _task_error_from_record(task_record: TaskRecord) -> TaskError | None:
    if task_record.error_code is None and task_record.error_message is None:
        return None

    return TaskError(
        code=task_record.error_code or "unknown_error",
        message=task_record.error_message or "Task failed.",
        details=_deserialize_error_details(task_record.error_details),
    )


def _serialize_error_details(
    details: dict[str, str | int | float | bool | None] | None,
) -> str | None:
    if not details:
        return None
    return json.dumps(details, sort_keys=True)


def _deserialize_error_details(
    value: str | None,
) -> dict[str, str | int | float | bool | None]:
    if not value:
        return {}

    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return {}

    if not isinstance(payload, dict):
        return {}

    return {
        str(key): item
        for key, item in payload.items()
        if isinstance(item, (str, int, float, bool)) or item is None
    }


def _detect_upload_archive_suffix(filename: str) -> str | None:
    lowered_name = Path(filename).name.lower()
    if lowered_name == NATIVE_XRAY_MINION_REPORT_FILENAME:
        return ".gz"

    for suffix in STORED_ARCHIVE_SUFFIXES:
        if suffix == ".gz":
            continue
        if lowered_name.endswith(suffix):
            return suffix

    return None


def _detect_archive_suffix(filename: str) -> str | None:
    lowered = filename.lower()
    for suffix in STORED_ARCHIVE_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    return None


def _task_id_from_archive_name(filename: str) -> str | None:
    archive_suffix = _detect_archive_suffix(filename)
    if archive_suffix is None:
        return None

    task_id = filename[: -len(archive_suffix)]
    if not task_id.startswith("tsk_"):
        return None

    return task_id


def _find_fallback_archive_path(task_id: str, *, uploads_dir: Path) -> Path:
    for suffix in (".zip", ".tar.gz", ".tgz", ".gz"):
        candidate = uploads_dir / f"{task_id}{suffix}"
        if candidate.exists():
            return candidate

    return uploads_dir / f"{task_id}.zip"
