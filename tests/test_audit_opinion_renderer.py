from app.schemas.audit_result import AuditResultV1, AuditSummary, ClaimReviewResult
from app.schemas.log_evidence import LogEvidenceV1, ResourceSignal, RuntimeComponentEvidence
from app.services.audit_opinion_renderer import render_audit_opinion_markdown


def test_render_audit_opinion_markdown_outputs_fixed_sections() -> None:
    audit_result = AuditResultV1(
        task_id="waf_audit_001",
        summary=AuditSummary(
            overall_conclusion="报告存在与日志证据冲突的内容，建议优先修订。",
            confirmed_count=1,
            partially_confirmed_count=1,
            conflict_count=1,
            insufficient_count=0,
            manual_only_count=1,
        ),
        claim_results=[
            ClaimReviewResult(
                claim_id="clm_001",
                claim_type="product_version",
                claim_priority="high",
                status="证实",
                reason="版本一致。",
                evidence_targets=["product_version"],
            ),
            ClaimReviewResult(
                claim_id="clm_002",
                claim_type="resource_usage_assessment",
                claim_priority="high",
                claim_metric="cpu",
                status="部分证实",
                reason="CPU 使用率的定性判断基本可参考，但报告值 56.0% 与日志值 68.0% 存在明显偏差。",
                evidence_targets=["resource_signals", "log_findings"],
                suggested_revision="建议将异常表述收敛为高负载描述。",
            ),
            ClaimReviewResult(
                claim_id="clm_003",
                claim_type="overall_inspection_conclusion",
                claim_priority="high",
                status="冲突",
                reason="日志态势为 abnormal。",
                evidence_targets=["derived_summary"],
                suggested_revision="建议修订整体结论。",
            ),
            ClaimReviewResult(
                claim_id="clm_004",
                claim_type="manual_inspection_assertion",
                claim_priority="manual_only",
                status="无法由日志判断",
                reason="需要人工判断。",
                evidence_targets=[],
            ),
        ],
    )

    log_evidence = LogEvidenceV1(
        task_id="waf_audit_001",
        runtime_components=[
            RuntimeComponentEvidence(
                component_name="mgt-redis",
                source_type="container",
                status="running",
                health="unknown",
                evidence_text="CPU 92.0% ; 内存 45.0% (450MiB / 1GiB)",
                source_refs=["container/docker_stats.txt"],
            )
        ],
        resource_signals=[
            ResourceSignal(
                scope="container",
                subject="mgt-redis",
                metric="cpu",
                observed_value=92.0,
                unit="percent",
                level="high",
                threshold_hit=True,
                raw_text="mgt-redis 92%",
                source_refs=["container/docker_stats.txt"],
            ),
            ResourceSignal(
                scope="container",
                subject="mgt-redis",
                metric="memory",
                observed_value=45.0,
                unit="percent",
                level="normal",
                threshold_hit=False,
                raw_text="mgt-redis 45%",
                source_refs=["container/docker_stats.txt"],
            ),
        ],
    )

    markdown = render_audit_opinion_markdown(audit_result, log_evidence=log_evidence)

    assert "## 总体审核结论" in markdown
    assert "## 资源使用率核验" in markdown
    assert "## 容器运行状况核验" in markdown
    assert "## 仍需人工判断" in markdown
    assert "## 建议修订" in markdown
    assert "建议修订整体结论。" in markdown
    assert "CPU使用率" in markdown
    assert "容器 `mgt-redis`" in markdown
    assert "redis restarting" not in markdown
