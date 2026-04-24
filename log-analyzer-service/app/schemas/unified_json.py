from typing import Literal

from pydantic import BaseModel, Field


UnifiedJsonSchemaVersion = Literal["unified-json/v1"]
OverallStatus = Literal["healthy", "warning", "critical", "unknown"]
RuntimeStatus = Literal["running", "stopped", "failed", "unknown"]
IssueSeverity = Literal["critical", "high", "medium", "low", "info"]


class UnifiedJsonSource(BaseModel):
    archive_name: str | None = None
    archive_size_bytes: int | None = None
    collected_at: str | None = None


class UnifiedJsonParser(BaseModel):
    name: str | None = None
    version: str | None = None


class HostInfo(BaseModel):
    hostname: str
    ip: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    kernel_version: str | None = None
    timezone: str | None = None
    uptime_seconds: int | None = None
    last_boot_at: str | None = None


class IssueBySeverity(BaseModel):
    critical: int
    high: int
    medium: int
    low: int
    info: int


class UnifiedJsonSummary(BaseModel):
    overall_status: OverallStatus
    service_count: int
    service_running_count: int
    container_count: int
    container_running_count: int
    issue_count: int
    issue_by_severity: IssueBySeverity


class UnifiedJsonService(BaseModel):
    name: str
    status: RuntimeStatus
    display_name: str | None = None
    enabled: bool | None = None
    version: str | None = None
    listen_ports: list[int] = Field(default_factory=list)
    start_mode: str | None = None
    notes: str | None = None


class UnifiedJsonContainer(BaseModel):
    name: str
    status: RuntimeStatus
    image: str | None = None
    runtime: str | None = None
    ports: list[str] = Field(default_factory=list)
    restart_policy: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    notes: str | None = None


class UnifiedJsonIssue(BaseModel):
    id: str
    severity: IssueSeverity
    category: str
    title: str
    description: str | None = None
    suggestion: str | None = None
    related_object_type: str | None = None
    related_object_name: str | None = None


class UnifiedJsonV1(BaseModel):
    schema_version: UnifiedJsonSchemaVersion
    task_id: str
    generated_at: str
    host_info: HostInfo
    summary: UnifiedJsonSummary
    services: list[UnifiedJsonService]
    containers: list[UnifiedJsonContainer]
    issues: list[UnifiedJsonIssue]
    source: UnifiedJsonSource | None = None
    parser: UnifiedJsonParser | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
