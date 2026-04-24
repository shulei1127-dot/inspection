from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


RuntimeStatus: TypeAlias = Literal[
    "running",
    "stopped",
    "failed",
    "restarting",
    "unknown",
]
HealthStatus: TypeAlias = Literal["healthy", "unhealthy", "unknown"]
ResourceMetric: TypeAlias = Literal["cpu", "memory", "disk"]
ResourceLevel: TypeAlias = Literal["normal", "high", "critical", "unknown"]
FindingType: TypeAlias = Literal[
    "health_fail",
    "restart",
    "oom",
    "error_log",
    "disk_high",
    "dependency_fail",
    "port_bind_fail",
]


class RuntimeComponentEvidence(BaseModel):
    component_name: str
    source_type: str
    status: RuntimeStatus
    health: HealthStatus
    image_or_version: str | None = None
    restart_signal: bool = False
    evidence_text: str
    source_refs: list[str] = Field(default_factory=list)


class ResourceSignal(BaseModel):
    scope: str
    subject: str
    metric: ResourceMetric
    observed_value: float | None = None
    unit: str | None = None
    level: ResourceLevel = "unknown"
    threshold_hit: bool = False
    raw_text: str
    source_refs: list[str] = Field(default_factory=list)


class LogFinding(BaseModel):
    finding_id: str
    finding_type: FindingType
    subject: str
    severity: str
    summary: str
    evidence_text: str
    source_refs: list[str] = Field(default_factory=list)


class DerivedSummary(BaseModel):
    overall_runtime_state: str = "unknown"
    abnormal_component_count: int = 0
    high_resource_items: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)


class LogEvidenceV1(BaseModel):
    schema_version: Literal["log-evidence/v1"] = "log-evidence/v1"
    task_id: str
    product_type: Literal["waf"] = "waf"
    product_version: str | None = None
    host_hostname: str | None = None
    host_ip_list: list[str] = Field(default_factory=list)
    host_os_name: str | None = None
    host_kernel_version: str | None = None
    runtime_components: list[RuntimeComponentEvidence] = Field(default_factory=list)
    resource_signals: list[ResourceSignal] = Field(default_factory=list)
    log_findings: list[LogFinding] = Field(default_factory=list)
    derived_summary: DerivedSummary = Field(default_factory=DerivedSummary)
