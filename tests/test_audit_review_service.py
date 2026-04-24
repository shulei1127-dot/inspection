from app.schemas.log_evidence import (
    DerivedSummary,
    LogEvidenceV1,
    LogFinding,
    ResourceSignal,
    RuntimeComponentEvidence,
)
from app.schemas.report_claims import ReportClaim, ReportClaimsV1
from app.services.audit_review_service import review_report_claims


def test_review_report_claims_applies_phase1_rules() -> None:
    claims = ReportClaimsV1(
        task_id="waf_audit_test",
        claims=[
            ReportClaim(
                claim_id="clm_001",
                claim_type="product_version",
                source_text="产品版本 7.0.1",
                subject="waf",
                metric=None,
                assertion="version_equals",
                expected_value="7.0.1",
                auditability="direct",
            ),
            ReportClaim(
                claim_id="clm_002",
                claim_type="component_runtime_status",
                source_text="Redis 运行状态重启",
                subject="redis",
                metric=None,
                assertion="status",
                expected_value="restarting",
                auditability="direct",
            ),
            ReportClaim(
                claim_id="clm_003",
                claim_type="resource_usage_assessment",
                source_text="内存使用率偏高，存在异常",
                subject="host",
                metric="memory",
                assertion="level",
                expected_value="high",
                auditability="direct",
            ),
            ReportClaim(
                claim_id="clm_004",
                claim_type="overall_inspection_conclusion",
                source_text="整体运行正常",
                subject="system",
                metric=None,
                assertion="overall_state",
                expected_value="healthy",
                auditability="partial",
            ),
        ],
    )
    evidence = LogEvidenceV1(
        task_id="waf_audit_test",
        product_version="7.0.1",
        runtime_components=[
            RuntimeComponentEvidence(
                component_name="redis",
                source_type="container",
                status="restarting",
                health="unhealthy",
                image_or_version="redis:7.0.1",
                restart_signal=True,
                evidence_text="docker status: Restarting (1)",
                source_refs=["containers/docker_ps"],
            )
        ],
        resource_signals=[
            ResourceSignal(
                scope="host",
                subject="host",
                metric="memory",
                observed_value=88.0,
                unit="percent",
                level="high",
                threshold_hit=True,
                raw_text="memory=88%",
                source_refs=["resources/resource_summary"],
            )
        ],
        log_findings=[
            LogFinding(
                finding_id="fdg_001",
                finding_type="restart",
                subject="redis",
                severity="high",
                summary="redis restarting",
                evidence_text="redis restarting",
                source_refs=["logs/app.log"],
            )
        ],
        derived_summary=DerivedSummary(
            overall_runtime_state="abnormal",
            abnormal_component_count=1,
            high_resource_items=["host:memory:high"],
            key_risks=["redis restarting"],
        ),
    )

    audit_result = review_report_claims(claims, evidence)

    statuses = {result.claim_id: result.status for result in audit_result.claim_results}
    assert statuses["clm_001"] == "无法由日志判断"
    assert statuses["clm_002"] == "证实"
    assert statuses["clm_003"] == "部分证实"
    assert statuses["clm_004"] == "冲突"
    assert audit_result.summary.conflict_count == 1
    assert audit_result.summary.manual_only_count == 1
    assert audit_result.claim_results[0].claim_priority == "manual_only"
    assert audit_result.claim_results[0].evidence_targets == []


def test_review_report_claims_supports_aggregate_service_status_and_warning_summary() -> None:
    claims = ReportClaimsV1(
        task_id="waf_audit_test",
        claims=[
            ReportClaim(
                claim_id="clm_101",
                claim_type="component_runtime_status",
                source_text="服务状态 正常",
                subject="service",
                metric=None,
                assertion="status",
                expected_value="running",
                auditability="direct",
            ),
            ReportClaim(
                claim_id="clm_102",
                claim_type="overall_inspection_conclusion",
                source_text="系统当前运行状态良好",
                subject="system",
                metric=None,
                assertion="overall_state",
                expected_value="healthy",
                auditability="partial",
            ),
        ],
    )
    evidence = LogEvidenceV1(
        task_id="waf_audit_test",
        runtime_components=[
            RuntimeComponentEvidence(
                component_name="mgt-api",
                source_type="container",
                status="running",
                health="unknown",
                image_or_version="mgt-api:latest",
                restart_signal=False,
                evidence_text="docker_stats_detected=true",
                source_refs=["container/docker_stats.txt"],
            ),
            RuntimeComponentEvidence(
                component_name="mgt-redis",
                source_type="container",
                status="running",
                health="unknown",
                image_or_version="redis:7.0.7",
                restart_signal=False,
                evidence_text="docker_stats_detected=true",
                source_refs=["container/docker_stats.txt"],
            ),
        ],
        log_findings=[
            LogFinding(
                finding_id="fdg_201",
                finding_type="dependency_fail",
                subject="traffic-learning",
                severity="high",
                summary="traffic-learning 存在依赖连接失败线索",
                evidence_text="dial tcp 169.254.0.9:9200: connect: connection refused",
                source_refs=["container/traffic-learning.log"],
            )
        ],
        derived_summary=DerivedSummary(
            overall_runtime_state="warning",
            abnormal_component_count=0,
            high_resource_items=[],
            key_risks=["traffic-learning 存在依赖连接失败线索"],
        ),
    )

    audit_result = review_report_claims(claims, evidence)

    statuses = {result.claim_id: result.status for result in audit_result.claim_results}
    assert statuses["clm_101"] == "证实"
    assert statuses["clm_102"] == "部分证实"
    assert audit_result.summary.overall_conclusion == "报告可作为人工巡检记录，但日志侧存在需补充说明的风险线索。"


def test_review_component_version_is_treated_as_report_sourced_metadata() -> None:
    claims = ReportClaimsV1(
        task_id="waf_audit_test",
        claims=[
            ReportClaim(
                claim_id="clm_201",
                claim_type="component_version",
                source_text="引擎版本 5.11.24-a3663104",
                subject="engine",
                metric=None,
                assertion="version_equals",
                expected_value="5.11.24-a3663104",
                auditability="direct",
            )
        ],
    )
    evidence = LogEvidenceV1(
        task_id="waf_audit_test",
        runtime_components=[
            RuntimeComponentEvidence(
                component_name="detector-srv",
                source_type="container",
                status="running",
                health="unknown",
                image_or_version="portus.in.chaitin.net/safeline-2/detector-srv:${IMAGE_TAG}",
                restart_signal=False,
                evidence_text="image placeholder",
                source_refs=["safeline/service_profile.yml"],
            )
        ],
        derived_summary=DerivedSummary(overall_runtime_state="healthy"),
    )

    audit_result = review_report_claims(claims, evidence)

    assert audit_result.claim_results[0].status == "无法由日志判断"
    assert audit_result.claim_results[0].claim_priority == "manual_only"


def test_review_report_claims_skips_manual_only_claims_from_log_backcheck() -> None:
    claims = ReportClaimsV1(
        task_id="waf_audit_test",
        claims=[
            ReportClaim(
                claim_id="clm_301",
                claim_type="manual_inspection_assertion",
                source_text="硬件物理状态 正常",
                subject="硬件物理状态",
                metric=None,
                assertion="manual_check",
                expected_value="normal",
                auditability="manual_only",
                priority="manual_only",
                evidence_targets=[],
            )
        ],
    )
    evidence = LogEvidenceV1(task_id="waf_audit_test", derived_summary=DerivedSummary(overall_runtime_state="healthy"))

    audit_result = review_report_claims(claims, evidence)

    assert audit_result.claim_results[0].status == "无法由日志判断"


def test_review_resource_usage_claim_detects_large_numeric_mismatch() -> None:
    claims = ReportClaimsV1(
        task_id="waf_audit_test",
        claims=[
            ReportClaim(
                claim_id="clm_401",
                claim_type="resource_usage_assessment",
                source_text="CPU 使用率 56%，整体正常。",
                subject="host",
                metric="cpu",
                assertion="level",
                expected_value="normal",
                auditability="direct",
            )
        ],
    )
    evidence = LogEvidenceV1(
        task_id="waf_audit_test",
        resource_signals=[
            ResourceSignal(
                scope="host",
                subject="host",
                metric="cpu",
                observed_value=85.0,
                unit="percent",
                level="high",
                threshold_hit=True,
                raw_text="cpu=85%",
                source_refs=["status_analysis_summary.json"],
            )
        ],
        derived_summary=DerivedSummary(overall_runtime_state="warning"),
    )

    audit_result = review_report_claims(claims, evidence)

    assert audit_result.claim_results[0].status == "冲突"
    assert "56.0%" in audit_result.claim_results[0].reason
    assert "85.0%" in audit_result.claim_results[0].reason
