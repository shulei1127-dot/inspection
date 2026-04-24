from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.schemas.waf_trend_enhancements import (
    WafTrendEnhancementCreateSuccessResponse,
    WafTrendEnhancementErrorResponse,
    WafTrendEnhancementResultSuccessResponse,
)
from app.services.waf_trend_enhancement_task_service import (
    WafTrendEnhancementTaskError,
    create_waf_trend_enhancement_from_preprocessing,
    get_waf_augmented_report_path,
    get_waf_trend_enhancement_result,
    get_waf_trend_summary_path,
)


router = APIRouter()


@router.post(
    "/api/waf/trend-enhancements",
    response_model=WafTrendEnhancementCreateSuccessResponse,
    status_code=201,
    summary="Create a WAF trend enhancement task from a preprocessing artifact",
    responses={
        400: {"model": WafTrendEnhancementErrorResponse},
        404: {"model": WafTrendEnhancementErrorResponse},
        500: {"model": WafTrendEnhancementErrorResponse},
    },
)
async def create_waf_trend_enhancement(
    preprocessing_id: str = Form(...),
    base_report_docx: UploadFile | None = File(default=None),
) -> WafTrendEnhancementCreateSuccessResponse | JSONResponse:
    try:
        data = create_waf_trend_enhancement_from_preprocessing(
            preprocessing_id=preprocessing_id,
            base_report_docx=base_report_docx,
        )
    except WafTrendEnhancementTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return WafTrendEnhancementCreateSuccessResponse(data=data)


@router.get(
    "/api/waf/trend-enhancements/{trend_id}",
    response_model=WafTrendEnhancementResultSuccessResponse,
    status_code=200,
    summary="Get one WAF trend enhancement task artifact summary",
    responses={
        400: {"model": WafTrendEnhancementErrorResponse},
        404: {"model": WafTrendEnhancementErrorResponse},
        500: {"model": WafTrendEnhancementErrorResponse},
    },
)
async def get_waf_trend_enhancement(trend_id: str) -> WafTrendEnhancementResultSuccessResponse | JSONResponse:
    try:
        data = get_waf_trend_enhancement_result(trend_id)
    except WafTrendEnhancementTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return WafTrendEnhancementResultSuccessResponse(data=data)


@router.get(
    "/api/waf/trend-enhancements/{trend_id}/summary",
    response_model=None,
    status_code=200,
    summary="Download the generated WAF trend summary markdown",
    responses={
        400: {"model": WafTrendEnhancementErrorResponse},
        404: {"model": WafTrendEnhancementErrorResponse},
    },
)
async def download_waf_trend_summary(trend_id: str) -> FileResponse | JSONResponse:
    try:
        path = get_waf_trend_summary_path(trend_id)
    except WafTrendEnhancementTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return FileResponse(
        path=path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{trend_id}_trend_summary.md",
    )


@router.get(
    "/api/waf/trend-enhancements/{trend_id}/augmented-report",
    response_model=None,
    status_code=200,
    summary="Download the generated WAF augmented DOCX report",
    responses={
        400: {"model": WafTrendEnhancementErrorResponse},
        404: {"model": WafTrendEnhancementErrorResponse},
    },
)
async def download_waf_augmented_report(trend_id: str) -> FileResponse | JSONResponse:
    try:
        path = get_waf_augmented_report_path(trend_id)
    except WafTrendEnhancementTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{trend_id}_augmented_report.docx",
    )
