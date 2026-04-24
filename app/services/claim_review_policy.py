from __future__ import annotations

from dataclasses import dataclass

from app.schemas.report_claims import ClaimPriority, ClaimType, EvidenceTarget, ReportClaim


@dataclass(frozen=True)
class ClaimReviewPolicy:
    priority: ClaimPriority
    evidence_targets: list[EvidenceTarget]


def build_claim_review_policy(
    *,
    claim_type: ClaimType,
    expected_value: str,
) -> ClaimReviewPolicy:
    if claim_type in {"product_version", "component_version"}:
        return ClaimReviewPolicy(priority="manual_only", evidence_targets=[])
    if claim_type in {"component_runtime_status", "component_health_status"}:
        return ClaimReviewPolicy(
            priority="high",
            evidence_targets=["runtime_components", "log_findings"],
        )
    if claim_type == "resource_usage_assessment":
        priority: ClaimPriority = "high" if expected_value in {"high", "critical"} else "medium"
        return ClaimReviewPolicy(
            priority=priority,
            evidence_targets=["resource_signals", "log_findings"],
        )
    if claim_type in {"exception_presence", "exception_cause"}:
        return ClaimReviewPolicy(
            priority="high",
            evidence_targets=["log_findings", "runtime_components"],
        )
    if claim_type == "overall_inspection_conclusion":
        return ClaimReviewPolicy(
            priority="high",
            evidence_targets=["derived_summary", "runtime_components", "resource_signals", "log_findings"],
        )
    if claim_type == "manual_inspection_assertion":
        return ClaimReviewPolicy(
            priority="manual_only",
            evidence_targets=[],
        )
    return ClaimReviewPolicy(priority="medium", evidence_targets=[])


def claim_requires_log_review(claim: ReportClaim) -> bool:
    return claim.priority in {"high", "medium"} and claim.auditability != "manual_only"
