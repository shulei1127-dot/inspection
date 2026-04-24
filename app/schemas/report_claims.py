from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator


ClaimType: TypeAlias = Literal[
    "product_version",
    "component_version",
    "component_runtime_status",
    "component_health_status",
    "resource_usage_assessment",
    "exception_presence",
    "exception_cause",
    "overall_inspection_conclusion",
    "manual_inspection_assertion",
]

ClaimAuditability: TypeAlias = Literal["direct", "partial", "manual_only"]
ClaimPriority: TypeAlias = Literal["high", "medium", "manual_only"]
EvidenceTarget: TypeAlias = Literal[
    "product_version",
    "runtime_components",
    "resource_signals",
    "log_findings",
    "derived_summary",
]


class ReportClaim(BaseModel):
    claim_id: str
    claim_type: ClaimType
    source_section: str | None = None
    source_text: str
    subject: str
    metric: str | None = None
    assertion: str
    expected_value: str
    auditability: ClaimAuditability
    priority: ClaimPriority = "medium"
    evidence_targets: list[EvidenceTarget] = Field(default_factory=list)

    @model_validator(mode="after")
    def apply_default_review_policy(self) -> "ReportClaim":
        if self.auditability == "manual_only":
            self.priority = "manual_only"
            self.evidence_targets = []
            return self

        if self.evidence_targets:
            return self

        from app.services.claim_review_policy import build_claim_review_policy

        policy = build_claim_review_policy(
            claim_type=self.claim_type,
            expected_value=self.expected_value,
        )
        self.priority = policy.priority
        self.evidence_targets = list(policy.evidence_targets)
        return self


class ReportClaimsV1(BaseModel):
    schema_version: Literal["report-claims/v1"] = "report-claims/v1"
    task_id: str
    product_type: Literal["waf"] = "waf"
    claims: list[ReportClaim] = Field(default_factory=list)
