from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TrendDataQuality = Literal["sufficient", "partial", "insufficient"]
TrendMetricStatus = Literal["stable", "pressure_high", "deteriorating", "unknown"]
TrendConfidence = Literal["low", "medium", "high"]
TrendInputSourceType = Literal["cleaned-status-analysis-md", "xray-task-v1"]
TrendEventType = Literal[
    "restart",
    "reboot",
    "unhealthy",
    "restarting",
    "abnormal_exit",
    "panic",
    "unclean_shutdown",
]


class TrendInputSource(BaseModel):
    type: TrendInputSourceType = "cleaned-status-analysis-md"
    path: str


class TrendParseSummary(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    time_points_detected: int = 0
    data_quality: TrendDataQuality = "insufficient"


class TrendMetricSample(BaseModel):
    timestamp: str
    value: float
    source_excerpt: str


class TrendMetricSeries(BaseModel):
    unit: Literal["percent"] = "percent"
    samples: list[TrendMetricSample] = Field(default_factory=list)


class TrendUptimeSample(BaseModel):
    timestamp: str
    uptime_seconds: int = Field(ge=0)
    source_excerpt: str


class TrendRestartEvent(BaseModel):
    timestamp: str | None = None
    subject: str | None = None
    event_type: TrendEventType
    count: int = Field(default=1, ge=1)
    source_excerpt: str


class TrendStabilityEventCounts(BaseModel):
    restart_count: int = Field(default=0, ge=0)
    panic_count: int = Field(default=0, ge=0)
    abnormal_exit_count: int = Field(default=0, ge=0)
    unclean_shutdown_count: int = Field(default=0, ge=0)


class TrendFaultChain(BaseModel):
    subject: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    event_types: list[TrendEventType] = Field(default_factory=list)
    event_counts: TrendStabilityEventCounts = Field(default_factory=TrendStabilityEventCounts)
    event_count: int = Field(default=0, ge=0)
    summary: str
    evidence: list[str] = Field(default_factory=list)


class TrendStabilityInput(BaseModel):
    uptime_samples: list[TrendUptimeSample] = Field(default_factory=list)
    restart_events: list[TrendRestartEvent] = Field(default_factory=list)
    event_counts: TrendStabilityEventCounts = Field(default_factory=TrendStabilityEventCounts)
    fault_chains: list[TrendFaultChain] = Field(default_factory=list)


class TrendInputMetrics(BaseModel):
    cpu: TrendMetricSeries = Field(default_factory=TrendMetricSeries)
    memory: TrendMetricSeries = Field(default_factory=TrendMetricSeries)
    disk: TrendMetricSeries = Field(default_factory=TrendMetricSeries)


class TrendInputV1(BaseModel):
    contract_version: Literal["trend-input/v1"] = "trend-input/v1"
    run_id: str
    generated_at: str
    source: TrendInputSource
    parse_summary: TrendParseSummary = Field(default_factory=TrendParseSummary)
    metrics: TrendInputMetrics = Field(default_factory=TrendInputMetrics)
    stability: TrendStabilityInput = Field(default_factory=TrendStabilityInput)


class TrendMetricAssessment(BaseModel):
    status: TrendMetricStatus
    confidence: TrendConfidence
    current_value: float | None = None
    baseline_value: float | None = None
    delta: float | None = None
    evidence: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    event_counts: TrendStabilityEventCounts | None = None
    fault_chains: list[TrendFaultChain] = Field(default_factory=list)


class TrendAssessmentMetrics(BaseModel):
    cpu: TrendMetricAssessment
    memory: TrendMetricAssessment
    disk: TrendMetricAssessment
    stability: TrendMetricAssessment


class TrendAssessmentOverall(BaseModel):
    summary_status: TrendMetricStatus
    data_quality: TrendDataQuality
    cautions: list[str] = Field(default_factory=list)


class TrendAssessmentV1(BaseModel):
    contract_version: Literal["trend-assessment/v1"] = "trend-assessment/v1"
    run_id: str
    generated_at: str
    input_path: str
    overall: TrendAssessmentOverall
    metrics: TrendAssessmentMetrics
    warnings: list[str] = Field(default_factory=list)
