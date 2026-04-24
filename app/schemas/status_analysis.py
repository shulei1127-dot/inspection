from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


StatusAnalysisSourceType = Literal["full-log-directory"]
StatusFindingSeverity = Literal["low", "medium", "high"]
StatusEventType = Literal["restart", "panic", "abnormal_exit", "unclean_shutdown"]
StatusScanMode = Literal["selective", "full_copy"]
StatusScanStrategy = Literal["full_read", "bounded_line_scan", "skipped"]
StatusCoverageLevel = Literal["full", "partial", "minimal"]


class StatusAnalysisSource(BaseModel):
    type: StatusAnalysisSourceType = "full-log-directory"
    path: str


class StatusAnalysisMetadata(BaseModel):
    product_type: Literal["waf"] = "waf"
    collect_time: str | None = None
    collect_time_raw: str | None = None
    reference_time: str
    window_start: str
    window_end: str
    window_days: int = 30
    host_hostname: str | None = None
    product_version: str | None = None


class StatusAnalysisMetricSnapshot(BaseModel):
    metric: Literal["cpu", "memory", "disk", "uptime"]
    current_value: float | None = None
    unit: str
    source_ref: str | None = None
    source_excerpt: str | None = None
    note: str | None = None


class StatusAnalysisResourceTimePoint(BaseModel):
    timestamp: str
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None
    source_ref: str
    source_excerpt: str | None = None
    sample_count: int = Field(default=1, ge=1)
    aggregation: Literal["raw", "12h_average"] = "raw"


class StatusAnalysisStabilityEvent(BaseModel):
    timestamp: str | None = None
    component: str | None = None
    event_type: StatusEventType
    summary: str
    severity: StatusFindingSeverity = "medium"
    source_ref: str
    in_recent_window: bool = True


class StatusAnalysisKeyFinding(BaseModel):
    category: Literal["service", "container", "system"]
    component: str | None = None
    severity: StatusFindingSeverity
    summary: str
    source_ref: str
    timestamp: str | None = None


class StatusAnalysisStabilityCounts30D(BaseModel):
    restart_count_30d: int = Field(default=0, ge=0)
    panic_count_30d: int = Field(default=0, ge=0)
    abnormal_exit_count_30d: int = Field(default=0, ge=0)
    unclean_shutdown_count_30d: int = Field(default=0, ge=0)


class StatusAnalysisScanFile(BaseModel):
    path: str
    strategy: StatusScanStrategy
    size_bytes: int | None = None
    evidence_categories: list[str] = Field(default_factory=list)
    reason: str | None = None


class StatusAnalysisScanCoverage(BaseModel):
    mode: StatusScanMode = "selective"
    copied_source: bool = False
    coverage_level: StatusCoverageLevel = "full"
    scanned_files: list[StatusAnalysisScanFile] = Field(default_factory=list)
    skipped_files: list[StatusAnalysisScanFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StatusAnalysisEvidenceV1(BaseModel):
    contract_version: Literal["status-analysis-evidence/v1"] = "status-analysis-evidence/v1"
    run_id: str
    generated_at: str
    source: StatusAnalysisSource
    metadata: StatusAnalysisMetadata
    resource_snapshots: list[StatusAnalysisMetricSnapshot] = Field(default_factory=list)
    resource_time_series: list[StatusAnalysisResourceTimePoint] = Field(default_factory=list)
    stability_events: list[StatusAnalysisStabilityEvent] = Field(default_factory=list)
    key_findings: list[StatusAnalysisKeyFinding] = Field(default_factory=list)
    historical_associations: list[StatusAnalysisStabilityEvent] = Field(default_factory=list)
    scan_coverage: StatusAnalysisScanCoverage = Field(default_factory=StatusAnalysisScanCoverage)
    warnings: list[str] = Field(default_factory=list)


class StatusAnalysisSummaryV1(BaseModel):
    contract_version: Literal["status-analysis-summary/v1"] = "status-analysis-summary/v1"
    run_id: str
    generated_at: str
    source: StatusAnalysisSource
    metadata: StatusAnalysisMetadata
    cpu_snapshot: StatusAnalysisMetricSnapshot | None = None
    memory_snapshot: StatusAnalysisMetricSnapshot | None = None
    disk_snapshot: StatusAnalysisMetricSnapshot | None = None
    uptime_snapshot: StatusAnalysisMetricSnapshot | None = None
    resource_time_series: list[StatusAnalysisResourceTimePoint] = Field(default_factory=list)
    stability_counts_30d: StatusAnalysisStabilityCounts30D = Field(default_factory=StatusAnalysisStabilityCounts30D)
    recent_stability_events: list[StatusAnalysisStabilityEvent] = Field(default_factory=list)
    historical_associations: list[StatusAnalysisStabilityEvent] = Field(default_factory=list)
    service_findings: list[StatusAnalysisKeyFinding] = Field(default_factory=list)
    container_findings: list[StatusAnalysisKeyFinding] = Field(default_factory=list)
    system_findings: list[StatusAnalysisKeyFinding] = Field(default_factory=list)
    coverage_level: StatusCoverageLevel = "full"
    scan_limitations: list[str] = Field(default_factory=list)
    major_skipped_sources: list[str] = Field(default_factory=list)
    coverage_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
