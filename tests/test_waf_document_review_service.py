from pathlib import Path

import httpx

from app.schemas.report_claims import ReportClaim, ReportClaimsV1
from app.services.waf_document_review_service import (
    build_waf_document_review_input,
    generate_waf_document_review,
)
from app.services.waf_llm_review_service import RemoteWafLlmReviewService


def test_build_waf_document_review_input_extracts_topics_and_help_docs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    help_docs_dir = tmp_path / "help_docs" / "waf"
    help_docs_dir.mkdir(parents=True)
    (help_docs_dir / "resource_alerts.md").write_text(
        "建议通过 docker stats 和 free -h 核查内存占用情况。",
        encoding="utf-8",
    )
    monkeypatch.setenv("WAF_HELP_DOCS_DIR", help_docs_dir.as_posix())

    report_claims = ReportClaimsV1(
        task_id="waf_doc_review_001",
        claims=[
            ReportClaim(
                claim_id="clm_001",
                claim_type="resource_usage_assessment",
                source_text="内存使用率达到87%",
                subject="host",
                metric="memory",
                assertion="level",
                expected_value="high",
                auditability="direct",
            ),
            ReportClaim(
                claim_id="clm_002",
                claim_type="component_health_status",
                source_text="xray-web容器服务异常，容器不健康",
                subject="xray-web",
                metric=None,
                assertion="health",
                expected_value="unhealthy",
                auditability="direct",
            ),
        ],
    )

    review_input = build_waf_document_review_input(report_claims)

    assert len(review_input.resource_claims) == 1
    assert review_input.resource_claims[0].metric == "memory"
    assert len(review_input.abnormal_topics) == 2
    assert any(topic.topic == "memory_high" for topic in review_input.abnormal_topics)
    assert any(topic.topic == "container_unhealthy" for topic in review_input.abnormal_topics)
    assert review_input.matched_help_docs


def test_generate_waf_document_review_prefers_llm_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "exception_actions": [
                                {
                                  "problem": "内存使用率达到87%",
                                  "evidence": "文档显示内存使用率达到87%。",
                                  "action": "建议通过 docker stats 和 free -h 核查内存占用。"
                                }
                              ],
                              "inspection_summary": "根据巡检文档内容，当前存在内存占用偏高风险，建议优先复核资源占用和关键组件运行状态。"
                            }
                            """
                        }
                    }
                ]
            },
        )

    service = RemoteWafLlmReviewService(
        base_url="http://llm.local/v1",
        api_key="test-key",
        model="glm-test",
        timeout_seconds=10,
        temperature=0.2,
        transport=httpx.MockTransport(handler),
    )
    review_input = ReportClaimsV1(
        task_id="waf_doc_review_002",
        claims=[
            ReportClaim(
                claim_id="clm_001",
                claim_type="resource_usage_assessment",
                source_text="内存使用率达到87%",
                subject="host",
                metric="memory",
                assertion="level",
                expected_value="high",
                auditability="direct",
            )
        ],
    )

    result = generate_waf_document_review(
        build_waf_document_review_input(review_input),
        llm_service=service,
    )

    assert result.llm_status == "ok"
    assert result.exception_actions[0].problem == "内存使用率达到87%"
    assert "根据巡检文档内容" in result.inspection_summary
