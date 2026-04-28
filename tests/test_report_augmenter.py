from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas.audit_result import AuditResultV1, AuditSummary, ClaimReviewResult
from app.schemas.log_evidence import LogEvidenceV1, ResourceSignal, RuntimeComponentEvidence
from app.schemas.waf_document_review import WafDocumentExceptionAction, WafDocumentReviewResultV1
from app.services.report_augmenter import (
    augment_report_with_audit_appendix,
    augment_report_with_document_review_appendix,
    augment_report_with_trend_appendix,
)
from app.services.trend_chart_renderer import render_trend_charts
from app.services.trend_forecaster import build_trend_assessment
from app.services.trend_input_builder import build_trend_input_from_markdown


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trend_reports"


def test_report_augmenter_appends_trend_appendix_and_embeds_png(tmp_path: Path) -> None:
    trend_input = build_trend_input_from_markdown(
        FIXTURE_DIR / "multi_point_status_analysis.md",
        run_id="trd_augment_001",
        generated_at="2026-04-16T00:00:00Z",
    )
    assessment = build_trend_assessment(
        trend_input,
        input_path="workdir/trd_augment_001/trend_input.json",
        generated_at="2026-04-16T00:01:00Z",
    )
    chart_dir = tmp_path / "charts"
    chart_paths = [artifact.path for artifact in render_trend_charts(trend_input, chart_dir)]

    base_docx = tmp_path / "base_report.docx"
    base_docx.write_bytes(_build_docx_bytes(["原始巡检报告", "这里是原正文。"]))
    output_docx = tmp_path / "augmented_report.docx"

    augment_report_with_trend_appendix(
        base_docx,
        assessment=assessment,
        chart_paths=chart_paths,
        output_path=output_docx,
    )

    assert output_docx.exists()
    with ZipFile(output_docx) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        names = set(archive.namelist())

    assert "附录：趋势增强分析" in document_xml
    assert "总体状态：压力较高" in document_xml
    assert "状态=呈恶化趋势" in document_xml
    assert "事件拆分=restart=2" in document_xml
    assert "故障链=2026-04-13 nginx.service 故障链：重启 2 次" in document_xml
    assert any(name.startswith("word/media/trend_image_") for name in names)
    assert "word/_rels/document.xml.rels" in names


def test_report_augmenter_appends_waf_audit_appendix(tmp_path: Path) -> None:
    base_docx = tmp_path / "base_report.docx"
    base_docx.write_bytes(_build_docx_bytes(["原始 WAF 巡检报告", "这里是原正文。"]))
    output_docx = tmp_path / "audit_augmented_report.docx"
    audit_result = AuditResultV1(
        task_id="waf_audit_test",
        summary=AuditSummary(
            overall_conclusion="报告存在与日志证据冲突的内容，建议优先修订。",
            confirmed_count=1,
            partially_confirmed_count=1,
            conflict_count=1,
            insufficient_count=1,
            manual_only_count=1,
        ),
        claim_results=[
            ClaimReviewResult(
                claim_id="claim_001",
                claim_type="component_runtime_status",
                claim_priority="high",
                status="冲突",
                reason="报告认为 Redis 正常，日志显示 Redis 重启。",
                evidence_refs=["status_analysis_summary.json"],
                suggested_revision="建议将 Redis 状态修订为存在重启风险。",
            ),
            ClaimReviewResult(
                claim_id="claim_002",
                claim_type="resource_usage_assessment",
                claim_priority="medium",
                claim_metric="memory",
                status="证据不足",
                reason="清洗结果中缺少 CPU 历史证据。",
            ),
        ],
    )
    log_evidence = LogEvidenceV1(
        task_id="waf_audit_test",
        runtime_components=[
            RuntimeComponentEvidence(
                component_name="mgt-redis",
                source_type="container",
                status="running",
                health="unknown",
                evidence_text="CPU 91.2% ; 内存 48.0% (480MiB / 1GiB)",
                source_refs=["container/docker_stats.txt"],
            )
        ],
        resource_signals=[
            ResourceSignal(
                scope="container",
                subject="mgt-redis",
                metric="cpu",
                observed_value=91.2,
                unit="percent",
                level="high",
                threshold_hit=True,
                raw_text="mgt-redis 91.2%",
                source_refs=["container/docker_stats.txt"],
            ),
            ResourceSignal(
                scope="container",
                subject="mgt-redis",
                metric="memory",
                observed_value=48.0,
                unit="percent",
                level="normal",
                threshold_hit=False,
                raw_text="mgt-redis 48.0%",
                source_refs=["container/docker_stats.txt"],
            ),
        ],
    )

    augment_report_with_audit_appendix(
        base_docx,
        audit_result=audit_result,
        log_evidence=log_evidence,
        output_path=output_docx,
    )

    assert output_docx.exists()
    with ZipFile(output_docx) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "原始 WAF 巡检报告" in document_xml
    assert "附录：日志核验意见" in document_xml
    assert "资源使用率核验" in document_xml
    assert "容器运行状况核验" in document_xml
    assert "容器名称" in document_xml
    assert "当前状态" in document_xml
    assert "CPU使用率" in document_xml
    assert "日志依据" in document_xml
    assert "处置建议" in document_xml
    assert "报告存在与日志证据冲突的内容" in document_xml
    assert "建议将 Redis 状态修订为存在重启风险" in document_xml
    assert "mgt-redis" in document_xml


def test_report_augmenter_appends_waf_document_only_review_appendix(tmp_path: Path) -> None:
    base_docx = tmp_path / "base_report.docx"
    base_docx.write_bytes(_build_docx_bytes(["原始 WAF 巡检报告", "这里是原正文。"]))
    output_docx = tmp_path / "document_only_augmented_report.docx"
    review_result = WafDocumentReviewResultV1(
        task_id="waf_doc_review_test",
        llm_status="disabled",
        llm_model="-",
        llm_error="-",
        disclaimer="以下建议基于巡检文档内容整理，未结合原始日志做一致性核验。",
        exception_actions=[
            WafDocumentExceptionAction(
                problem="内存使用率达到87%",
                evidence="文档显示内存使用率达到87%。",
                action="建议通过 docker stats 和 free -h 核查内存占用情况。",
            )
        ],
        inspection_summary="根据巡检文档内容，当前存在资源占用偏高风险，建议优先核查内存占用与关键组件状态。",
    )

    augment_report_with_document_review_appendix(
        base_docx,
        review_result=review_result,
        output_path=output_docx,
    )

    assert output_docx.exists()
    with ZipFile(output_docx) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "附录：文档直审意见" in document_xml
    assert "未结合原始日志做一致性核验" in document_xml
    assert "问题 1：内存使用率达到87%" in document_xml
    assert "巡检总结" in document_xml


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    body_items = []
    for paragraph in paragraphs:
        body_items.append(
            "<w:p><w:r><w:t>{}</w:t></w:r></w:p>".format(_xml_escape(paragraph))
        )

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(body_items)}
    <w:sectPr/>
  </w:body>
</w:document>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
