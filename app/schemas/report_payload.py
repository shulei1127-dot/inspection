from typing import Literal

from pydantic import BaseModel, Field


ReportPayloadSchemaVersion = Literal["report-payload/v1"]


class ReportMeta(BaseModel):
    title: str
    generated_at: str
    task_id: str
    report_lang: str


class ReportHost(BaseModel):
    hostname: str
    ip: str | None = None
    os: str | None = None
    kernel_version: str | None = None
    timezone: str | None = None


class ReportSummary(BaseModel):
    overall_status: str
    overall_status_label: str
    service_count: int
    service_running_count: int
    container_count: int
    container_running_count: int
    issue_count: int


class ServiceRow(BaseModel):
    name: str
    status: str
    status_label: str
    enabled: str
    version: str
    ports: str
    notes: str


class ContainerRow(BaseModel):
    name: str
    image: str
    status: str
    status_label: str
    cpu_percent: str = "-"
    memory_percent: str = "-"
    ports: str
    notes: str


class IssueRow(BaseModel):
    id: str
    severity: str
    severity_label: str
    category: str
    title: str
    description: str
    suggestion: str


class ReportPayloadV1(BaseModel):
    payload_version: ReportPayloadSchemaVersion
    report: ReportMeta
    host: ReportHost
    summary: ReportSummary
    service_rows: list[ServiceRow] = Field(default_factory=list)
    container_rows: list[ContainerRow] = Field(default_factory=list)
    issue_rows: list[IssueRow] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    appendix: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
