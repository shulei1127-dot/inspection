from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


WafPreprocessingStatus: TypeAlias = Literal["completed"]


class WafPreprocessingSummary(BaseModel):
    coverage_level: Literal["full", "partial", "minimal"] = "minimal"
    resource_history_point_count: int = 0
    stability_event_count: int = 0
    service_finding_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class WafPreprocessingCreateData(BaseModel):
    preprocessing_id: str
    status: WafPreprocessingStatus = "completed"
    contract_version: str = "waf-preprocessing-response/v1"
    filename: str
    source_archive_path: str
    extracted_dir_path: str
    source_directory_path: str
    resource_history_csv_path: str
    status_analysis_evidence_path: str
    status_analysis_summary_path: str
    status_analysis_md_path: str
    summary: WafPreprocessingSummary = Field(default_factory=WafPreprocessingSummary)


class WafPreprocessingCreateSuccessResponse(BaseModel):
    success: Literal[True] = True
    data: WafPreprocessingCreateData


class WafPreprocessingResultSuccessResponse(BaseModel):
    success: Literal[True] = True
    data: WafPreprocessingCreateData


class WafPreprocessingError(BaseModel):
    code: str
    message: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class WafPreprocessingErrorResponse(BaseModel):
    success: Literal[False] = False
    error: WafPreprocessingError
