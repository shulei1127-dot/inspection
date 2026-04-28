from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


WafAuditStatus: TypeAlias = Literal[
    "parsing_report",
    "extracting_evidence",
    "reviewing",
    "completed",
    "failed",
]
WafAuditReviewMode: TypeAlias = Literal["log_grounded", "document_only"]


class WafAuditSummary(BaseModel):
    claim_count: int = 0
    confirmed_count: int = 0
    conflict_count: int = 0


class WafAuditCreateData(BaseModel):
    task_id: str
    status: Literal["completed"]
    contract_version: str = "waf-audit-response/v1"
    review_mode: WafAuditReviewMode = "log_grounded"
    report_file_path: str
    log_file_path: str | None
    preprocessing_id: str | None = None
    report_claims_path: str
    log_evidence_path: str | None = None
    audit_result_path: str | None = None
    audit_opinion_path: str
    audit_augmented_report_path: str | None = None
    document_review_input_path: str | None = None
    llm_review_json_path: str | None = None
    summary: WafAuditSummary = Field(default_factory=WafAuditSummary)


class WafAuditCreateSuccessResponse(BaseModel):
    success: Literal[True] = True
    data: WafAuditCreateData


class WafAuditResultData(BaseModel):
    task_id: str
    status: WafAuditStatus
    contract_version: str = "waf-audit-response/v1"
    review_mode: WafAuditReviewMode = "log_grounded"
    created_at: str | None = None
    report_file_path: str | None = None
    log_file_path: str | None = None
    preprocessing_id: str | None = None
    report_claims_path: str | None = None
    log_evidence_path: str | None = None
    audit_result_path: str | None = None
    audit_opinion_path: str | None = None
    audit_augmented_report_path: str | None = None
    document_review_input_path: str | None = None
    llm_review_json_path: str | None = None
    summary: WafAuditSummary = Field(default_factory=WafAuditSummary)
    error: "WafAuditError | None" = None


class WafAuditResultSuccessResponse(BaseModel):
    success: Literal[True] = True
    data: WafAuditResultData


class WafAuditListSuccessResponse(BaseModel):
    success: Literal[True] = True
    data: list[WafAuditResultData]


class WafAuditError(BaseModel):
    code: str
    message: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class WafAuditErrorResponse(BaseModel):
    success: Literal[False] = False
    error: WafAuditError
