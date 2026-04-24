from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import get_settings
from app.schemas.tasks import (
    RenderReportData,
    RenderReportSuccessResponse,
    TaskCleanupOptions,
    TaskCleanupSuccessResponse,
    TaskCreateOptions,
    TaskCreateSuccessResponse,
    TaskDeleteSuccessResponse,
    TaskErrorResponse,
    TaskListSuccessResponse,
    TaskResultSuccessResponse,
)
from app.services.report_rendering_service import render_task_report
from app.services.report_template_selector import resolve_report_template_path_for_unified_json_file
from app.services.task_service import (
    TaskLookupError,
    TaskUploadError,
    cleanup_tasks,
    create_task_from_upload,
    delete_task,
    get_task_report_path,
    get_task_result,
    list_task_results,
    record_task_render_result,
)


router = APIRouter()


@router.post(
    "/api/tasks",
    response_model=TaskCreateSuccessResponse,
    status_code=201,
    summary="Create an inspection task from a supported archive upload",
    responses={
        400: {"model": TaskErrorResponse},
        415: {"model": TaskErrorResponse},
        503: {"model": TaskErrorResponse},
        500: {"model": TaskErrorResponse},
    },
)
async def create_task(
    file: UploadFile | None = File(default=None),
    parser_profile: str = Form("default"),
    report_lang: str = Form("zh-CN"),
) -> TaskCreateSuccessResponse | JSONResponse:
    options = TaskCreateOptions(
        parser_profile=parser_profile,
        report_lang=report_lang,
    )

    try:
        data = create_task_from_upload(file, options)
    except TaskUploadError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return TaskCreateSuccessResponse(data=data)


@router.get(
    "/api/tasks",
    response_model=TaskListSuccessResponse,
    status_code=200,
    summary="List recent inspection tasks",
)
async def list_tasks() -> TaskListSuccessResponse:
    return TaskListSuccessResponse(data=list_task_results())


@router.post(
    "/api/tasks/cleanup",
    response_model=TaskCleanupSuccessResponse,
    status_code=200,
    summary="Batch cleanup retained task artifacts and records using minimal retention filters",
)
async def cleanup_task_artifacts(
    cleanup_options: TaskCleanupOptions,
) -> TaskCleanupSuccessResponse:
    return TaskCleanupSuccessResponse(data=cleanup_tasks(cleanup_options))


@router.get(
    "/api/tasks/{task_id}",
    response_model=TaskResultSuccessResponse,
    status_code=200,
    summary="Get the current result for an inspection task",
    responses={
        404: {"model": TaskErrorResponse},
    },
)
async def get_task(task_id: str) -> TaskResultSuccessResponse | JSONResponse:
    try:
        data = get_task_result(task_id)
    except TaskLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return TaskResultSuccessResponse(data=data)


@router.post(
    "/api/tasks/{task_id}/render-report",
    response_model=RenderReportSuccessResponse,
    status_code=200,
    summary="Render a DOCX report from an existing report payload",
    responses={
        400: {"model": TaskErrorResponse},
        404: {"model": TaskErrorResponse},
        503: {"model": TaskErrorResponse},
    },
)
async def render_report(task_id: str) -> RenderReportSuccessResponse | JSONResponse:
    result = render_task_report(task_id)
    record_task_render_result(task_id, result)
    settings = get_settings()

    if not result.success or result.output_path is None:
        status_code = 503
        if result.error_code == "report_payload_missing":
            status_code = 404
        elif result.error_code in {"invalid_report_payload", "template_missing"}:
            status_code = 400

        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": {
                    "code": result.error_code or "render_failed",
                    "message": result.error_message or "Report rendering failed.",
                    "details": result.details,
                },
            },
        )

    return RenderReportSuccessResponse(
        data=RenderReportData(
            task_id=task_id,
            template_path=resolve_report_template_path_for_unified_json_file(
                settings.workdir_dir / task_id / "unified.json",
                settings=settings,
            ).as_posix(),
            report_payload_path=(
                settings.workdir_dir / task_id / "report_payload.json"
            ).as_posix(),
            report_file_path=result.output_path.as_posix(),
            renderer=result.renderer or "HttpCarboneAdapter",
            status="rendered",
        )
    )


@router.get(
    "/api/tasks/{task_id}/report",
    response_model=None,
    status_code=200,
    summary="Download the rendered DOCX report for an inspection task",
    responses={
        404: {"model": TaskErrorResponse},
    },
)
async def download_report(task_id: str) -> FileResponse | JSONResponse:
    try:
        report_path = get_task_report_path(task_id)
    except TaskLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return FileResponse(
        path=report_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=f"{task_id}.docx",
    )


@router.delete(
    "/api/tasks/{task_id}",
    response_model=TaskDeleteSuccessResponse,
    status_code=200,
    summary="Delete the uploaded archive, workdir, and outputs for an inspection task",
    responses={
        404: {"model": TaskErrorResponse},
    },
)
async def delete_task_endpoint(task_id: str) -> TaskDeleteSuccessResponse | JSONResponse:
    try:
        data = delete_task(task_id)
    except TaskLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return TaskDeleteSuccessResponse(data=data)
