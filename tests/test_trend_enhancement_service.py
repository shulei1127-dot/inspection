from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.services.trend_enhancement_service import run_trend_enhancement


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trend_reports"


def test_trend_enhancement_service_runs_end_to_end_without_touching_other_chains(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "disabled")
    source_md = FIXTURE_DIR / "multi_point_status_analysis.md"
    source_docx = tmp_path / "base_report.docx"
    source_docx.write_bytes(_build_docx_bytes(["基础巡检报告", "原始正文保留。"]))

    artifacts = run_trend_enhancement(
        source_md,
        base_report_docx_path=source_docx,
    )

    assert Path(artifacts.source_report_md_path).exists()
    assert Path(artifacts.trend_input_path).exists()
    assert Path(artifacts.trend_assessment_path).exists()
    assert Path(artifacts.trend_summary_path).exists()
    assert Path(artifacts.trend_state_graph_path).exists()
    assert Path(artifacts.output_trend_state_graph_path).exists()
    assert artifacts.trend_state_graph_image_path is None
    assert len(artifacts.chart_paths) == 3
    assert artifacts.augmented_report_path is not None
    assert Path(artifacts.augmented_report_path).exists()
    assert artifacts.run_id.startswith("trd_")

    summary_text = Path(artifacts.trend_summary_path).read_text(encoding="utf-8")
    mermaid_text = Path(artifacts.trend_state_graph_path).read_text(encoding="utf-8")
    assert "## 状态趋势图" in summary_text
    assert "不是精确数值预测图" in summary_text
    assert "```mermaid" in summary_text
    assert mermaid_text == Path(artifacts.output_trend_state_graph_path).read_text(encoding="utf-8")
    assert "重点项<br/>CPU：呈恶化趋势" in mermaid_text


def test_trend_enhancement_service_optionally_renders_mermaid_png(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_cli = tmp_path / "fake-mmdc"
    fake_cli.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import sys

output = Path(sys.argv[sys.argv.index("-o") + 1])
output.write_bytes(b"fake-png")
""",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "local_cli")
    monkeypatch.setenv("MERMAID_CLI_PATH", fake_cli.as_posix())

    artifacts = run_trend_enhancement(FIXTURE_DIR / "multi_point_status_analysis.md")

    assert artifacts.trend_state_graph_image_path is not None
    assert Path(artifacts.trend_state_graph_image_path).exists()
    assert Path(artifacts.trend_state_graph_image_path).name == "trend_state_graph.png"
    assert Path(artifacts.trend_state_graph_image_path).read_bytes() == b"fake-png"
    assert len(artifacts.chart_paths) == 3


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    body_items = []
    for paragraph in paragraphs:
        body_items.append(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>")
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
