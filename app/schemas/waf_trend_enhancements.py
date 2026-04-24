from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WafTrendMetricStatuses(BaseModel):
    cpu: Literal["stable", "pressure_high", "deteriorating", "unknown"]
    memory: Literal["stable", "pressure_high", "deteriorating", "unknown"]
    disk: Literal["stable", "pressure_high", "deteriorating", "unknown"]
    stability: Literal["stable", "pressure_high", "deteriorating", "unknown"]


class WafTrendEnhancementSummary(BaseModel):
    overall_status: Literal["stable", "pressure_high", "deteriorating", "unknown"]
    data_quality: Literal["sufficient", "partial", "insufficient"]
    metric_statuses: WafTrendMetricStatuses
    chart_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class WafTrendEnhancementCreateData(BaseModel):
    trend_id: str
    preprocessing_id: str
    status: Literal["completed"] = "completed"
    contract_version: str = "waf-trend-enhancement-response/v1"
    source_status_analysis_md_path: str
    source_report_md_path: str
    source_report_docx_path: str | None = None
    trend_input_path: str
    trend_assessment_path: str
    trend_summary_path: str
    trend_state_graph_path: str
    output_trend_state_graph_path: str
    trend_state_graph_image_path: str | None = None
    chart_paths: list[str] = Field(default_factory=list)
    augmented_report_path: str | None = None
    summary: WafTrendEnhancementSummary


class WafTrendEnhancementCreateSuccessResponse(BaseModel):
    success: Literal[True] = True
    data: WafTrendEnhancementCreateData


class WafTrendEnhancementResultSuccessResponse(BaseModel):
    success: Literal[True] = True
    data: WafTrendEnhancementCreateData


class WafTrendEnhancementError(BaseModel):
    code: str
    message: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class WafTrendEnhancementErrorResponse(BaseModel):
    success: Literal[False] = False
    error: WafTrendEnhancementError
