from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.schemas.waf_preprocessing import (
    WafPreprocessingCreateSuccessResponse,
    WafPreprocessingErrorResponse,
    WafPreprocessingResultSuccessResponse,
)
from app.services.waf_preprocessing_task_service import (
    WafPreprocessingTaskError,
    create_waf_preprocessing_from_upload,
    get_waf_preprocessing_result,
    get_waf_status_analysis_path,
)


router = APIRouter()


@router.post(
    "/api/waf/preprocessing",
    response_model=WafPreprocessingCreateSuccessResponse,
    status_code=201,
    summary="Create a WAF preprocessing task from a full-log archive upload",
    responses={
        400: {"model": WafPreprocessingErrorResponse},
        415: {"model": WafPreprocessingErrorResponse},
        500: {"model": WafPreprocessingErrorResponse},
    },
)
async def create_waf_preprocessing(
    file: UploadFile | None = File(default=None),
    reference_time: str | None = Form(default=None),
    copy_source: bool | None = Form(default=None),
) -> WafPreprocessingCreateSuccessResponse | JSONResponse:
    try:
        data = create_waf_preprocessing_from_upload(
            file,
            reference_time=reference_time,
            copy_source=copy_source,
        )
    except WafPreprocessingTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return WafPreprocessingCreateSuccessResponse(data=data)


@router.get(
    "/api/waf/preprocessing/{preprocessing_id}",
    response_model=WafPreprocessingResultSuccessResponse,
    status_code=200,
    summary="Get one WAF preprocessing task artifact summary",
    responses={
        400: {"model": WafPreprocessingErrorResponse},
        404: {"model": WafPreprocessingErrorResponse},
        500: {"model": WafPreprocessingErrorResponse},
    },
)
async def get_waf_preprocessing(preprocessing_id: str) -> WafPreprocessingResultSuccessResponse | JSONResponse:
    try:
        data = get_waf_preprocessing_result(preprocessing_id)
    except WafPreprocessingTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return WafPreprocessingResultSuccessResponse(data=data)


@router.get(
    "/api/waf/preprocessing/{preprocessing_id}/status-analysis",
    response_model=None,
    status_code=200,
    summary="Download the generated WAF status analysis markdown",
    responses={
        400: {"model": WafPreprocessingErrorResponse},
        404: {"model": WafPreprocessingErrorResponse},
    },
)
async def download_waf_status_analysis(preprocessing_id: str) -> FileResponse | JSONResponse:
    try:
        path = get_waf_status_analysis_path(preprocessing_id)
    except WafPreprocessingTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return FileResponse(
        path=path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{preprocessing_id}_status_analysis.md",
    )
