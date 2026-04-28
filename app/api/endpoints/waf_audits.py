from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.schemas.audit_result import AuditResultV1
from app.schemas.report_claims import ReportClaimsV1
from app.schemas.waf_document_review import (
    WafDocumentReviewInputV1,
    WafDocumentReviewResultV1,
)
from app.schemas.waf_audits import (
    WafAuditCreateSuccessResponse,
    WafAuditErrorResponse,
    WafAuditListSuccessResponse,
    WafAuditResultSuccessResponse,
)
from app.services.waf_audit_task_service import (
    WafAuditLookupError,
    WafAuditTaskError,
    create_waf_audit_from_preprocessing,
    create_waf_audit_from_upload,
    create_waf_document_only_review,
    get_waf_audit_augmented_report_path,
    get_waf_document_review_input,
    get_waf_document_review_result,
    get_waf_audit_opinion_path,
    get_waf_audit_result,
    get_waf_audit_structured_result,
    get_waf_report_claims,
    list_waf_audit_results,
)


router = APIRouter()


@router.post(
    "/api/waf-audits",
    response_model=WafAuditCreateSuccessResponse,
    status_code=201,
    summary="Create a WAF audit task from one manual docx report and WAF preprocessing evidence",
    responses={
        400: {"model": WafAuditErrorResponse},
        415: {"model": WafAuditErrorResponse},
        503: {"model": WafAuditErrorResponse},
        500: {"model": WafAuditErrorResponse},
    },
)
async def create_waf_audit(
    report_file: UploadFile | None = File(default=None),
    log_file: UploadFile | None = File(default=None),
    preprocessing_id: str | None = Form(default=None),
    report_lang: str = Form("zh-CN"),
) -> WafAuditCreateSuccessResponse | JSONResponse:
    try:
        if preprocessing_id and preprocessing_id.strip():
            data = create_waf_audit_from_preprocessing(
                report_file,
                preprocessing_id,
                report_lang=report_lang,
            )
        else:
            data = create_waf_audit_from_upload(
                report_file,
                log_file,
                report_lang=report_lang,
            )
    except WafAuditTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )
    return WafAuditCreateSuccessResponse(data=data)


@router.post(
    "/api/waf-audits/document-only",
    response_model=WafAuditCreateSuccessResponse,
    status_code=201,
    summary="Create a WAF document-only review task from one manual docx report",
    responses={
        400: {"model": WafAuditErrorResponse},
        500: {"model": WafAuditErrorResponse},
    },
)
async def create_waf_document_only_audit(
    report_file: UploadFile | None = File(default=None),
    report_lang: str = Form("zh-CN"),
) -> WafAuditCreateSuccessResponse | JSONResponse:
    try:
        data = create_waf_document_only_review(
            report_file,
            report_lang=report_lang,
        )
    except WafAuditTaskError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )
    return WafAuditCreateSuccessResponse(data=data)


@router.get(
    "/api/waf-audits",
    response_model=WafAuditListSuccessResponse,
    status_code=200,
    summary="List recent WAF audit tasks",
)
async def list_waf_audits() -> WafAuditListSuccessResponse:
    return WafAuditListSuccessResponse(data=list_waf_audit_results())


@router.get(
    "/api/waf-audits/{task_id}",
    response_model=WafAuditResultSuccessResponse,
    status_code=200,
    summary="Get one WAF audit task summary",
    responses={404: {"model": WafAuditErrorResponse}},
)
async def get_waf_audit(task_id: str) -> WafAuditResultSuccessResponse | JSONResponse:
    try:
        data = get_waf_audit_result(task_id)
    except WafAuditLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_error().model_dump()},
        )
    return WafAuditResultSuccessResponse(data=data)


@router.get(
    "/api/waf-audits/{task_id}/claims",
    response_model=ReportClaimsV1,
    status_code=200,
    summary="Get normalized report claims for a WAF audit task",
    responses={404: {"model": WafAuditErrorResponse}},
)
async def get_waf_audit_claims(task_id: str) -> ReportClaimsV1 | JSONResponse:
    try:
        return get_waf_report_claims(task_id)
    except WafAuditLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_error().model_dump()},
        )


@router.get(
    "/api/waf-audits/{task_id}/audit-result",
    response_model=AuditResultV1,
    status_code=200,
    summary="Get structured audit review output for a WAF audit task",
    responses={404: {"model": WafAuditErrorResponse}},
)
async def get_waf_audit_result_endpoint(task_id: str) -> AuditResultV1 | JSONResponse:
    try:
        return get_waf_audit_structured_result(task_id)
    except WafAuditLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_error().model_dump()},
        )


@router.get(
    "/api/waf-audits/{task_id}/audit-opinion",
    response_model=None,
    status_code=200,
    summary="Download the markdown audit opinion for a WAF audit task",
    responses={404: {"model": WafAuditErrorResponse}},
)
async def get_waf_audit_opinion(task_id: str) -> FileResponse | JSONResponse:
    try:
        path = get_waf_audit_opinion_path(task_id)
    except WafAuditLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_error().model_dump()},
        )

    return FileResponse(
        path=path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{task_id}.md",
    )


@router.get(
    "/api/waf-audits/{task_id}/augmented-report",
    response_model=None,
    status_code=200,
    summary="Download the DOCX report with WAF audit appendix",
    responses={404: {"model": WafAuditErrorResponse}},
)
async def get_waf_audit_augmented_report(task_id: str) -> FileResponse | JSONResponse:
    try:
        path = get_waf_audit_augmented_report_path(task_id)
    except WafAuditLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_error().model_dump()},
        )

    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{task_id}_audit_augmented_report.docx",
    )


@router.get(
    "/api/waf-audits/{task_id}/document-review-input",
    response_model=WafDocumentReviewInputV1,
    status_code=200,
    summary="Get structured document-only review input for a WAF audit task",
    responses={404: {"model": WafAuditErrorResponse}},
)
async def get_waf_document_review_input_endpoint(
    task_id: str,
) -> WafDocumentReviewInputV1 | JSONResponse:
    try:
        return get_waf_document_review_input(task_id)
    except WafAuditLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_error().model_dump()},
        )


@router.get(
    "/api/waf-audits/{task_id}/document-review",
    response_model=WafDocumentReviewResultV1,
    status_code=200,
    summary="Get structured document-only LLM review result for a WAF audit task",
    responses={404: {"model": WafAuditErrorResponse}},
)
async def get_waf_document_review_result_endpoint(
    task_id: str,
) -> WafDocumentReviewResultV1 | JSONResponse:
    try:
        return get_waf_document_review_result(task_id)
    except WafAuditLookupError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_error().model_dump()},
        )
