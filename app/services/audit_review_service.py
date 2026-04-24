from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.schemas.audit_result import (
    AuditResultV1,
    AuditSummary,
    ClaimReviewResult,
)
from app.schemas.log_evidence import (
    DerivedSummary,
    LogEvidenceV1,
    LogFinding,
    ResourceSignal,
    RuntimeComponentEvidence,
)
from app.schemas.report_claims import ReportClaim, ReportClaimsV1
from app.services.claim_review_policy import claim_requires_log_review


COMPONENT_ALIAS_MAP = {
    "waf": "waf",
    "engine": "engine",
    "引擎": "engine",
    "service": "service",
    "services": "service",
    "服务": "service",
    "服务状态": "service",
    "container": "service",
    "containers": "service",
    "容器": "service",
    "容器状态": "service",
    "host": "host",
    "system": "host",
    "节点": "host",
    "redis": "redis",
    "mgt-redis": "redis",
    "postgres": "postgres",
    "mgt-postgres": "postgres",
    "es": "es",
    "elasticsearch": "es",
    "mgt-es": "es",
    "management": "management",
    "mgt-api": "management",
    "api": "management",
    "mario": "mario",
    "detector": "engine",
    "detector-srv": "engine",
    "ripley": "engine",
    "ripley-work": "engine",
    "traffic-learning": "traffic-learning",
}
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass(frozen=True)
class ClaimEvidenceBundle:
    product_version: str | None = None
    runtime_components: list[RuntimeComponentEvidence] = field(default_factory=list)
    resource_signals: list[ResourceSignal] = field(default_factory=list)
    log_findings: list[LogFinding] = field(default_factory=list)
    derived_summary: DerivedSummary | None = None


def review_report_claims(
    report_claims: ReportClaimsV1,
    log_evidence: LogEvidenceV1,
) -> AuditResultV1:
    claim_results = [
        _review_claim(claim, log_evidence)
        for claim in report_claims.claims
    ]

    confirmed_count = sum(result.status == "证实" for result in claim_results)
    partially_confirmed_count = sum(result.status == "部分证实" for result in claim_results)
    conflict_count = sum(result.status == "冲突" for result in claim_results)
    insufficient_count = sum(result.status == "证据不足" for result in claim_results)
    manual_only_count = sum(result.status == "无法由日志判断" for result in claim_results)
    key_conflicts = [result.reason for result in claim_results if result.status == "冲突"][:5]
    key_risks = [
        result.reason
        for result in claim_results
        if result.claim_priority == "high" and result.status in {"冲突", "部分证实", "证据不足"}
    ][:5]

    if conflict_count > 0:
        overall_conclusion = "报告存在与日志证据冲突的内容，建议优先修订。"
    elif key_risks and (partially_confirmed_count > 0 or insufficient_count > 0):
        overall_conclusion = "报告可作为人工巡检记录，但日志侧存在需补充说明的风险线索。"
    elif partially_confirmed_count > 0 or insufficient_count > 0:
        overall_conclusion = "报告总体可参考，但部分结论需要补证据或收敛措辞。"
    else:
        overall_conclusion = "报告中的核心技术结论与当前日志证据基本一致。"

    return AuditResultV1(
        task_id=report_claims.task_id,
        summary=AuditSummary(
            overall_conclusion=overall_conclusion,
            confirmed_count=confirmed_count,
            partially_confirmed_count=partially_confirmed_count,
            conflict_count=conflict_count,
            insufficient_count=insufficient_count,
            manual_only_count=manual_only_count,
            key_conflicts=key_conflicts,
            key_risks=key_risks,
        ),
        claim_results=claim_results,
    )


def _review_claim(claim: ReportClaim, log_evidence: LogEvidenceV1) -> ClaimReviewResult:
    if claim.auditability == "manual_only" or claim.priority == "manual_only":
        return _result(
            claim,
            status="无法由日志判断",
            reason="该检查项依赖人工验证或界面观察，当前日志无法直接判断。",
        )
    if not claim_requires_log_review(claim):
        return _result(
            claim,
            status="无法由日志判断",
            reason="该检查项当前不在日志核验范围内，仍需人工判断。",
        )

    evidence_bundle = _build_claim_evidence_bundle(claim, log_evidence)

    handlers = {
        "product_version": _review_product_version,
        "component_version": _review_component_version,
        "component_runtime_status": _review_component_runtime_status,
        "component_health_status": _review_component_health_status,
        "resource_usage_assessment": _review_resource_usage_assessment,
        "exception_presence": _review_exception_presence,
        "exception_cause": _review_exception_cause,
        "overall_inspection_conclusion": _review_overall_conclusion,
        "manual_inspection_assertion": _review_manual_only_claim,
    }
    return handlers[claim.claim_type](claim, evidence_bundle)


def _review_product_version(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    if not evidence_bundle.product_version:
        return _result(claim, status="证据不足", reason="日志中未提取到稳定产品版本。")

    if evidence_bundle.product_version == claim.expected_value:
        return _result(
            claim,
            status="证实",
            reason=f"日志版本 {evidence_bundle.product_version} 与报告一致。",
        )

    if evidence_bundle.product_version.startswith(claim.expected_value.split(".")[0]):
        return _result(
            claim,
            status="部分证实",
            reason=f"日志版本 {evidence_bundle.product_version} 与报告版本族接近，但粒度不完全一致。",
            suggested_revision="建议在报告中补充精确版本号。",
        )

    return _result(
        claim,
        status="冲突",
        reason=f"报告版本为 {claim.expected_value}，日志版本为 {evidence_bundle.product_version}。",
        suggested_revision="建议按日志中的实际版本修订报告。",
    )


def _review_component_version(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    component = _find_component(evidence_bundle.runtime_components, claim.subject)
    if component is None or not component.image_or_version:
        return _result(claim, status="证据不足", reason="日志中未找到可比对的组件版本信息。")

    version_hint = _extract_version_hint(component.image_or_version)
    if version_hint is None:
        return _result(
            claim,
            status="证据不足",
            reason="日志中的组件版本信息仍是占位或镜像标签，无法稳定比对精确版本。",
            evidence_refs=component.source_refs,
        )

    if claim.expected_value in component.image_or_version or claim.expected_value in version_hint:
        return _result(
            claim,
            status="证实",
            reason=f"组件 {component.component_name} 的日志版本信息与报告一致。",
            evidence_refs=component.source_refs,
        )

    return _result(
        claim,
        status="冲突",
        reason=f"组件 {component.component_name} 的日志版本信息与报告不一致。",
        evidence_refs=component.source_refs,
        suggested_revision="建议按日志中的组件版本信息修订报告。",
    )


def _review_component_runtime_status(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    if _is_aggregate_runtime_subject(claim.subject):
        return _review_aggregate_runtime_status(claim, evidence_bundle)

    component = _find_component(evidence_bundle.runtime_components, claim.subject)
    if component is None:
        return _result(claim, status="证据不足", reason="日志中未找到对应组件运行状态。")
    if component.status == claim.expected_value:
        return _result(
            claim,
            status="证实",
            reason=f"组件 {component.component_name} 的运行状态与报告一致。",
            evidence_refs=component.source_refs,
        )

    if claim.expected_value == "running" and component.status in {"unknown"}:
        return _result(
            claim,
            status="证据不足",
            reason=f"组件 {component.component_name} 的日志状态不足以支撑“运行正常”结论。",
            evidence_refs=component.source_refs,
        )

    return _result(
        claim,
        status="冲突",
        reason=f"报告认为 {component.component_name} 状态为 {claim.expected_value}，日志实际为 {component.status}。",
        evidence_refs=component.source_refs,
        suggested_revision="建议按日志中的组件运行状态修订报告。",
    )


def _review_component_health_status(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    if _is_aggregate_runtime_subject(claim.subject):
        abnormal_components = _aggregate_abnormal_components(evidence_bundle.runtime_components)
        if not evidence_bundle.runtime_components:
            return _result(claim, status="证据不足", reason="日志中没有稳定组件清单，无法支撑健康汇总结论。")
        if claim.expected_value == "healthy" and not abnormal_components:
            return _result(claim, status="部分证实", reason="日志未见明确异常运行态，但缺少稳定健康探针结果。")
        if abnormal_components:
            first = abnormal_components[0]
            return _result(
                claim,
                status="冲突",
                reason=f"日志显示 {first.component_name} 存在异常运行态，无法支撑整体健康结论。",
                evidence_refs=first.source_refs,
                suggested_revision="建议将健康结论收敛为“运行基本正常，但存在需关注风险”。",
            )
        return _result(claim, status="证据不足", reason="日志中没有稳定健康状态证据。")

    component = _find_component(evidence_bundle.runtime_components, claim.subject)
    if component is None or component.health == "unknown":
        return _result(claim, status="证据不足", reason="日志中没有稳定健康状态证据。")
    if component.health == claim.expected_value:
        return _result(
            claim,
            status="证实",
            reason=f"组件 {component.component_name} 的健康状态与报告一致。",
            evidence_refs=component.source_refs,
        )
    return _result(
        claim,
        status="冲突",
        reason=f"报告认为 {component.component_name} 健康状态为 {claim.expected_value}，日志显示为 {component.health}。",
        evidence_refs=component.source_refs,
        suggested_revision="建议按日志中的健康状态修订报告。",
    )


def _review_resource_usage_assessment(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    signal = _find_resource_signal(evidence_bundle.resource_signals, metric=claim.metric or "")
    if signal is None:
        return _result(claim, status="证据不足", reason="日志中未提取到对应资源指标。")

    report_percent = _extract_reported_percent(claim.source_text)
    signal_percent = signal.observed_value if (signal.unit or "").lower() in {"percent", "%"} else None
    metric_label = _format_metric_label(claim.metric)
    if report_percent is not None and signal_percent is not None:
        delta = abs(report_percent - signal_percent)
        if delta > 15:
            return _result(
                claim,
                status="冲突",
                reason=(
                    f"{metric_label}在报告中写为 {report_percent:.1f}%，"
                    f"日志实测约为 {signal_percent:.1f}%，差异较大。"
                ),
                evidence_refs=signal.source_refs,
                suggested_revision="建议按日志中的实际资源值修订报告描述。",
            )
        if delta > 10:
            return _result(
                claim,
                status="部分证实",
                reason=(
                    f"{metric_label}的定性判断基本可参考，但报告值 {report_percent:.1f}% "
                    f"与日志值 {signal_percent:.1f}% 存在明显偏差。"
                ),
                evidence_refs=signal.source_refs,
                suggested_revision="建议将资源数值修订为与日志快照更接近的口径。",
            )

    anomaly_findings = _find_resource_related_findings(evidence_bundle.log_findings, metric=claim.metric or "")
    if claim.expected_value in {"high", "critical"}:
        if signal.level in {"high", "critical"} and anomaly_findings:
            return _result(
                claim,
                status="证实",
                reason=f"{metric_label}达到 {signal.level}，且存在伴随异常证据。",
                evidence_refs=signal.source_refs + _collect_finding_refs(anomaly_findings),
            )
        if signal.level in {"high", "critical"}:
            return _result(
                claim,
                status="部分证实",
                reason=f"{metric_label}偏高，但缺少足够伴随异常证据，当前更像高负载信号。",
                evidence_refs=signal.source_refs,
                suggested_revision="建议将绝对异常表述收敛为高负载/高占用描述。",
            )
        return _result(
            claim,
            status="冲突",
            reason=f"报告认为{metric_label}异常，但日志指标为 {signal.level}。",
            evidence_refs=signal.source_refs,
            suggested_revision="建议按当前日志指标修订异常结论。",
        )

    if claim.expected_value == "normal":
        if signal.level == "normal":
            if report_percent is not None and signal_percent is not None:
                return _result(
                    claim,
                    status="证实",
                    reason=(
                        f"{metric_label}正常，且报告值 {report_percent:.1f}% "
                        f"与日志值 {signal_percent:.1f}% 基本一致。"
                    ),
                    evidence_refs=signal.source_refs,
                )
            return _result(
                claim,
                status="证实",
                reason=f"{metric_label}处于正常范围。",
                evidence_refs=signal.source_refs,
            )
        return _result(
            claim,
            status="冲突",
            reason=f"报告认为{metric_label}正常，但日志指标为 {signal.level}。",
            evidence_refs=signal.source_refs,
            suggested_revision="建议补充资源风险说明。",
        )

    return _result(claim, status="证据不足", reason="当前资源评估口径无法稳定匹配。")


def _review_exception_presence(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    findings = _find_findings(evidence_bundle.log_findings, subject=claim.subject)
    if any(_finding_matches_exception(finding, claim.expected_value) for finding in findings):
        matching = [finding for finding in findings if _finding_matches_exception(finding, claim.expected_value)]
        return _result(
            claim,
            status="证实",
            reason=f"日志存在与报告一致的异常信号：{claim.expected_value}。",
            evidence_refs=_collect_finding_refs(matching),
        )

    if findings:
        return _result(
            claim,
            status="部分证实",
            reason="日志中存在异常线索，但与报告描述的异常类型不完全一致。",
            evidence_refs=_collect_finding_refs(findings),
            suggested_revision="建议明确异常对象和异常类型。",
        )

    return _result(claim, status="证据不足", reason="日志中未找到对应异常证据。")


def _review_exception_cause(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    findings = _find_findings(evidence_bundle.log_findings, subject=claim.subject)
    if not findings:
        return _result(claim, status="证据不足", reason="日志中未找到可支持原因分析的异常证据。")

    if any(_cause_matches_finding(claim.expected_value, finding) for finding in findings):
        matching = [finding for finding in findings if _cause_matches_finding(claim.expected_value, finding)]
        return _result(
            claim,
            status="证实",
            reason=f"日志中存在可直接支持“{claim.expected_value}”的原因证据。",
            evidence_refs=_collect_finding_refs(matching),
        )

    if claim.expected_value != "unknown":
        if any(finding.finding_type in {"restart", "health_fail", "error_log"} for finding in findings):
            return _result(
                claim,
                status="部分证实",
                reason="日志中存在相关异常，但不足以直接证明报告给出的原因。",
                evidence_refs=_collect_finding_refs(findings),
                suggested_revision="建议将原因表述从确定性因果收敛为推测性描述。",
            )

    return _result(claim, status="证据不足", reason="当前日志证据不足以支撑该原因判断。")


def _review_overall_conclusion(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    actual = (evidence_bundle.derived_summary.overall_runtime_state if evidence_bundle.derived_summary else "unknown")
    if actual == "unknown":
        return _result(claim, status="证据不足", reason="日志覆盖面不足，无法支撑整体结论。")
    if actual == claim.expected_value:
        return _result(
            claim,
            status="证实",
            reason=f"日志汇总态势为 {actual}，与报告整体结论一致。",
        )
    if {actual, claim.expected_value} <= {"warning", "healthy"} or {actual, claim.expected_value} <= {"warning", "abnormal"}:
        return _result(
            claim,
            status="部分证实",
            reason=f"日志汇总态势为 {actual}，与报告方向接近但措辞强度不完全一致。",
            suggested_revision="建议收敛整体结论措辞，使其与日志风险等级一致。",
        )
    return _result(
        claim,
        status="冲突",
        reason=f"报告整体结论为 {claim.expected_value}，日志汇总态势为 {actual}。",
        suggested_revision="建议按日志汇总结论修订整体评价。",
    )


def _review_manual_only_claim(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    del evidence_bundle
    return _result(
        claim,
        status="无法由日志判断",
        reason="该检查项主要依赖人工巡检、控制台截图或业务确认，当前不走日志核验。",
    )


def _result(
    claim: ReportClaim,
    *,
    status: str,
    reason: str,
    evidence_refs: list[str] | None = None,
    suggested_revision: str | None = None,
) -> ClaimReviewResult:
    return ClaimReviewResult(
        claim_id=claim.claim_id,
        claim_type=claim.claim_type,
        claim_priority=claim.priority,
        claim_subject=claim.subject,
        claim_metric=claim.metric,
        claim_source_text=claim.source_text,
        status=status,
        reason=reason,
        evidence_targets=list(claim.evidence_targets),
        evidence_refs=evidence_refs or [],
        suggested_revision=suggested_revision,
    )


def _extract_reported_percent(text: str) -> float | None:
    match = PERCENT_RE.search(text)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _format_metric_label(metric: str | None) -> str:
    mapping = {
        "cpu": "CPU使用率",
        "memory": "内存使用率",
        "disk": "磁盘使用率",
    }
    return mapping.get(metric or "", metric or "资源指标")


def _build_claim_evidence_bundle(claim: ReportClaim, log_evidence: LogEvidenceV1) -> ClaimEvidenceBundle:
    targets = set(claim.evidence_targets)
    return ClaimEvidenceBundle(
        product_version=log_evidence.product_version if "product_version" in targets else None,
        runtime_components=list(log_evidence.runtime_components) if "runtime_components" in targets else [],
        resource_signals=list(log_evidence.resource_signals) if "resource_signals" in targets else [],
        log_findings=list(log_evidence.log_findings) if "log_findings" in targets else [],
        derived_summary=log_evidence.derived_summary if "derived_summary" in targets else None,
    )


def _find_component(
    runtime_components: list[RuntimeComponentEvidence],
    subject: str,
) -> RuntimeComponentEvidence | None:
    normalized_subject = _normalize_component_subject(subject)
    for component in runtime_components:
        normalized_component_name = _normalize_component_subject(component.component_name)
        if normalized_component_name == normalized_subject:
            return component
        if normalized_subject in component.component_name.lower():
            return component
    return None


def _find_resource_signal(
    resource_signals: list[ResourceSignal],
    *,
    metric: str,
) -> ResourceSignal | None:
    for signal in resource_signals:
        if signal.metric == metric:
            return signal
    return None


def _find_findings(log_findings: list[LogFinding], *, subject: str) -> list[LogFinding]:
    normalized_subject = _normalize_component_subject(subject)
    direct = [
        finding
        for finding in log_findings
        if _normalize_component_subject(finding.subject) == normalized_subject
        or normalized_subject in finding.subject.lower()
    ]
    if direct:
        return direct
    if subject == "host":
        return list(log_findings)
    return []


def _finding_matches_exception(finding: LogFinding, expected_value: str) -> bool:
    if expected_value == "restart":
        return finding.finding_type == "restart"
    if expected_value == "disk_high":
        return finding.finding_type == "disk_high"
    if expected_value == "health_fail":
        return finding.finding_type == "health_fail"
    if expected_value in {"error", "oom"}:
        return finding.finding_type in {expected_value, "error_log"}
    return False


def _cause_matches_finding(expected_cause: str, finding: LogFinding) -> bool:
    return (
        expected_cause == finding.finding_type
        or (expected_cause == "disk_high" and finding.finding_type == "disk_high")
        or (expected_cause == "dependency_fail" and finding.finding_type == "dependency_fail")
        or (expected_cause == "oom" and finding.finding_type == "oom")
    )


def _collect_finding_refs(findings: list[LogFinding]) -> list[str]:
    refs: list[str] = []
    for finding in findings:
        refs.extend(finding.source_refs)
    return list(dict.fromkeys(refs))


def _find_resource_related_findings(
    log_findings: list[LogFinding],
    *,
    metric: str,
) -> list[LogFinding]:
    findings: list[LogFinding] = []
    for finding in log_findings:
        if finding.subject.lower() == "host" and finding.finding_type in {"oom", "disk_high", "error_log"}:
            findings.append(finding)
            continue
        if metric == "memory" and finding.finding_type == "oom":
            findings.append(finding)
        elif metric == "disk" and finding.finding_type == "disk_high":
            findings.append(finding)
    return findings


def _review_aggregate_runtime_status(claim: ReportClaim, evidence_bundle: ClaimEvidenceBundle) -> ClaimReviewResult:
    if not evidence_bundle.runtime_components:
        return _result(claim, status="证据不足", reason="日志中未找到可用于汇总服务状态的组件清单。")

    abnormal_components = _aggregate_abnormal_components(evidence_bundle.runtime_components)
    unknown_components = [
        component for component in evidence_bundle.runtime_components if component.status == "unknown"
    ]
    if claim.expected_value == "running":
        if abnormal_components:
            first = abnormal_components[0]
            return _result(
                claim,
                status="冲突",
                reason=f"日志显示 {first.component_name} 运行态异常，无法支撑“服务状态正常”。",
                evidence_refs=first.source_refs,
                suggested_revision="建议补充异常组件说明，避免使用绝对正常表述。",
            )
        if unknown_components:
            return _result(
                claim,
                status="部分证实",
                reason="日志中的主要组件运行正常，但仍有部分配置组件未在运行快照中稳定命中。",
                evidence_refs=_collect_component_refs(evidence_bundle.runtime_components),
                suggested_revision="建议将“服务状态正常”收敛为“主要服务运行正常”。",
            )
        return _result(
            claim,
            status="证实",
            reason="日志中的主要组件在采集时均处于运行态，可支撑“服务状态正常”表述。",
            evidence_refs=_collect_component_refs(evidence_bundle.runtime_components),
        )

    return _result(claim, status="证据不足", reason="当前汇总服务状态口径无法稳定匹配。")


def _aggregate_abnormal_components(runtime_components: list[RuntimeComponentEvidence]) -> list[RuntimeComponentEvidence]:
    return [
        component
        for component in runtime_components
        if component.status in {"failed", "restarting", "stopped"} or component.health == "unhealthy"
    ]


def _collect_component_refs(components: list[RuntimeComponentEvidence]) -> list[str]:
    refs: list[str] = []
    for component in components:
        refs.extend(component.source_refs)
    return list(dict.fromkeys(refs))


def _normalize_component_subject(subject: str) -> str:
    lowered = subject.lower().strip()
    return COMPONENT_ALIAS_MAP.get(lowered, lowered)


def _is_aggregate_runtime_subject(subject: str) -> bool:
    return _normalize_component_subject(subject) in {"service", "host"}


def _extract_version_hint(raw_value: str) -> str | None:
    if "${" in raw_value:
        return None
    match = re.search(r"(\d+(?:\.\d+){1,4}(?:[-_a-zA-Z0-9]+)?)", raw_value)
    if match is None:
        return None
    return match.group(1)
