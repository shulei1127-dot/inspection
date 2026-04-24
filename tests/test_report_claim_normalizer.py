from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.services.manual_report_parser import parse_manual_report
from app.services.report_claim_normalizer import normalize_report_claims


def test_normalize_report_claims_ignores_instructional_text_and_extracts_summary(tmp_path: Path) -> None:
    report_path = tmp_path / "report.docx"
    report_path.write_bytes(
        _build_docx_bytes(
            paragraphs=[
                "3、在巡检项目中检查结果分为：正常、异常、未涉及。",
                "-异常：表示该项目的检查结果不符合预期，并在小节 4 巡检结果分析和处理建议 中给出异常描述和处理建议；",
                "此次共巡检了一台设备，巡检过程中发现0个异常(风险)，系统当前运行状态良好，各项核心功能正常，容器状态均正常，满足安全巡检要求。",
            ],
            tables=[
                [
                    ["检查项", "检查结果"],
                    ["产品版本", "21.07.005_stable_r1"],
                    ["引擎版本", "5.11.24-a3663104"],
                    ["服务状态", "正常", "符合预期"],
                    ["CPU", "正常", "CPU使用率：3.58%"],
                ]
            ],
        )
    )

    parsed_report = parse_manual_report(report_path)
    claims = normalize_report_claims(parsed_report, task_id="waf_audit_test")

    assert not any(claim.claim_type == "exception_presence" for claim in claims.claims)
    assert any(
        claim.claim_type == "overall_inspection_conclusion" and claim.expected_value == "healthy"
        for claim in claims.claims
    )
    assert any(
        claim.claim_type == "component_runtime_status" and claim.subject == "service" and claim.expected_value == "running"
        for claim in claims.claims
    )
    assert not any(claim.claim_type in {"product_version", "component_version"} for claim in claims.claims)
    assert any(
        claim.claim_type == "overall_inspection_conclusion"
        and claim.priority == "high"
        and claim.evidence_targets == ["derived_summary", "runtime_components", "resource_signals", "log_findings"]
        for claim in claims.claims
    )


def test_normalize_report_claims_marks_manual_checks_as_manual_only(tmp_path: Path) -> None:
    report_path = tmp_path / "manual.docx"
    report_path.write_bytes(
        _build_docx_bytes(
            paragraphs=["一、巡检项"],
            tables=[
                [
                    ["检查类", "检查项", "检查结果", "详细描述"],
                    ["物理状态", "硬件物理状态", "正常", "符合预期"],
                ]
            ],
        )
    )

    parsed_report = parse_manual_report(report_path)
    claims = normalize_report_claims(parsed_report, task_id="waf_audit_test")

    manual_claim = next(claim for claim in claims.claims if claim.claim_type == "manual_inspection_assertion")
    assert manual_claim.priority == "manual_only"
    assert manual_claim.auditability == "manual_only"
    assert manual_claim.evidence_targets == []


def test_normalize_report_claims_extracts_waf_resource_rows_from_realistic_table(tmp_path: Path) -> None:
    report_path = tmp_path / "waf_resource_report.docx"
    report_path.write_bytes(
        _build_docx_bytes(
            paragraphs=["二、巡检内容"],
            tables=[
                [
                    ["检查类", "检查项", "检查结果"],
                    ["管理节点功能", "功能状态", "符合预期"],
                    ["节点负载状态", "CPU", "使用率稳定在4.38%左右， 无异常值"],
                    ["", "内存", "使用率稳定在72.99%左右， 无异常值"],
                    ["", "服务状态", "全部正常"],
                    ["磁盘状态", "磁盘使用率", "硬盘空间大小 ：50.91 TB使用率：77.71%"],
                ]
            ],
        )
    )

    parsed_report = parse_manual_report(report_path)
    claims = normalize_report_claims(parsed_report, task_id="waf_audit_test")
    resource_claims = {
        (claim.metric, claim.expected_value): claim
        for claim in claims.claims
        if claim.claim_type == "resource_usage_assessment"
    }

    assert ("cpu", "normal") in resource_claims
    assert ("memory", "normal") in resource_claims
    assert ("disk", "normal") in resource_claims
    assert "4.38%" in resource_claims[("cpu", "normal")].source_text
    assert "72.99%" in resource_claims[("memory", "normal")].source_text
    assert "77.71%" in resource_claims[("disk", "normal")].source_text


def test_normalize_report_claims_uses_numeric_threshold_when_resource_row_has_only_percent(tmp_path: Path) -> None:
    report_path = tmp_path / "waf_resource_threshold.docx"
    report_path.write_bytes(
        _build_docx_bytes(
            paragraphs=["二、巡检内容"],
            tables=[
                [
                    ["检查类", "检查项", "检查结果"],
                    ["磁盘状态", "磁盘使用率", "硬盘空间大小 ：10 TB 使用率：91.20%"],
                ]
            ],
        )
    )

    parsed_report = parse_manual_report(report_path)
    claims = normalize_report_claims(parsed_report, task_id="waf_audit_test")
    disk_claims = [
        claim
        for claim in claims.claims
        if claim.claim_type == "resource_usage_assessment" and claim.metric == "disk"
    ]

    assert len(disk_claims) == 1
    assert disk_claims[0].expected_value == "critical"


def _build_docx_bytes(
    *,
    paragraphs: list[str],
    tables: list[list[list[str]]],
) -> bytes:
    body_items = []
    for paragraph in paragraphs:
        body_items.append(
            "<w:p><w:r><w:t>{}</w:t></w:r></w:p>".format(_xml_escape(paragraph))
        )
    for table in tables:
        rows = []
        for row in table:
            cells = "".join(
                f"<w:tc><w:p><w:r><w:t>{_xml_escape(cell)}</w:t></w:r></w:p></w:tc>"
                for cell in row
            )
            rows.append(f"<w:tr>{cells}</w:tr>")
        body_items.append(f"<w:tbl>{''.join(rows)}</w:tbl>")

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
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
