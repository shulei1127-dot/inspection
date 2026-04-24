from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.services.manual_report_parser import parse_manual_report


def test_parse_manual_report_extracts_paragraphs_tables_and_sections(tmp_path: Path) -> None:
    report_path = tmp_path / "report.docx"
    report_path.write_bytes(
        _build_docx_bytes(
            paragraphs=[
                "一、部署信息",
                "本次巡检产品版本为 7.0.1",
                "二、巡检结论",
                "整体运行存在告警，需要关注 Redis 重启问题。",
            ],
            tables=[
                [
                    ["检查项", "检查结果"],
                    ["Redis 运行状态", "重启"],
                    ["内存使用情况", "偏高"],
                ]
            ],
        )
    )

    parsed = parse_manual_report(report_path)

    assert parsed.paragraphs[0].section == "一、部署信息"
    assert parsed.paragraphs[1].section == "一、部署信息"
    assert parsed.paragraphs[-1].section == "二、巡检结论"
    assert parsed.tables[0].section == "二、巡检结论"
    assert parsed.tables[0].rows[1] == ["Redis 运行状态", "重启"]


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
