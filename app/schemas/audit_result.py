from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

from app.schemas.report_claims import ClaimPriority, EvidenceTarget


AuditStatus: TypeAlias = Literal[
    "证实",
    "部分证实",
    "冲突",
    "证据不足",
    "无法由日志判断",
]


class ClaimReviewResult(BaseModel):
    claim_id: str
    claim_type: str
    claim_priority: ClaimPriority = "medium"
    claim_subject: str | None = None
    claim_metric: str | None = None
    claim_source_text: str | None = None
    status: AuditStatus
    reason: str
    evidence_targets: list[EvidenceTarget] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    suggested_revision: str | None = None


class AuditSummary(BaseModel):
    overall_conclusion: str
    confirmed_count: int = 0
    partially_confirmed_count: int = 0
    conflict_count: int = 0
    insufficient_count: int = 0
    manual_only_count: int = 0
    key_conflicts: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)


class AuditResultV1(BaseModel):
    schema_version: Literal["audit-result/v1"] = "audit-result/v1"
    task_id: str
    product_type: Literal["waf"] = "waf"
    summary: AuditSummary
    claim_results: list[ClaimReviewResult] = Field(default_factory=list)
