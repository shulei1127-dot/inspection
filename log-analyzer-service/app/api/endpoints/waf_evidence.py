from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.waf_evidence import (
    ErrorResponse,
    WafEvidenceRequestV1,
    WafEvidenceResponseV1,
)
from app.services.waf_log_evidence_extractor import (
    WafEvidenceExtractorError,
    build_waf_log_evidence_extractor,
)


router = APIRouter()


@router.post(
    "/waf-evidence",
    response_model=WafEvidenceResponseV1,
    summary="Extract review-oriented WAF log evidence from an extracted directory",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def extract_waf_evidence(
    request: WafEvidenceRequestV1,
) -> WafEvidenceResponseV1 | JSONResponse:
    try:
        response = build_waf_log_evidence_extractor().extract(request)
    except WafEvidenceExtractorError as exc:
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
    return response
