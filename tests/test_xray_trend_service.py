from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.services.xray_trend_service import maybe_run_xray_trend_enhancement


def test_xray_trend_service_degrades_cleanly_without_resource_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "disabled")

    task_id = "tsk_xray_trend_001"
    task_workdir = tmp_path / "workdir" / task_id
    output_dir = tmp_path / "outputs" / task_id
    task_workdir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    (task_workdir / "unified.json").write_text(
        json.dumps(_build_xray_unified_json(task_id=task_id), ensure_ascii=False),
        encoding="utf-8",
    )
    report_docx_path = output_dir / "report.docx"
    report_docx_path.write_bytes(_build_docx_bytes(["洞鉴巡检报告", "原始正文。"]))

    artifacts = maybe_run_xray_trend_enhancement(
        task_id,
        base_report_docx_path=report_docx_path,
    )

    assert artifacts is not None
    assert Path(artifacts.trend_input_path).exists()
    assert Path(artifacts.trend_assessment_path).exists()
    assert Path(artifacts.trend_summary_path).exists()
    assert Path(artifacts.trend_state_graph_path).exists()
    assert artifacts.resource_history_path is None
    assert artifacts.chart_paths == []
    assert artifacts.trend_state_graph_image_path is None
    assert artifacts.augmented_report_path is None
    assert any("未检测到 xray resource_history.csv" in warning for warning in artifacts.warnings)

    summary_text = Path(artifacts.trend_summary_path).read_text(encoding="utf-8")
    assert "未生成图表" in summary_text


def test_xray_trend_service_generates_charts_and_augments_report_when_history_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_cli = tmp_path / "fake-mmdc"
    fake_cli.write_text(
        """#!/usr/bin/env python3
import base64
from pathlib import Path
import sys

output = Path(sys.argv[sys.argv.index("-o") + 1])
output.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1d8AAAAASUVORK5CYII="))
""",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "local_cli")
    monkeypatch.setenv("MERMAID_CLI_PATH", fake_cli.as_posix())

    task_id = "tsk_xray_trend_002"
    task_workdir = tmp_path / "workdir" / task_id
    resource_dir = task_workdir / "resources"
    output_dir = tmp_path / "outputs" / task_id
    resource_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    (task_workdir / "unified.json").write_text(
        json.dumps(_build_xray_unified_json(task_id=task_id), ensure_ascii=False),
        encoding="utf-8",
    )
    (resource_dir / "resource_history.csv").write_text(
        "\n".join(
            [
                "timestamp,cpu,memory,disk",
                "2026-04-17T00:00:00Z,24.0,61.0,71.0",
                "2026-04-17T12:00:00Z,36.0,68.0,74.0",
                "2026-04-18T00:00:00Z,52.0,79.0,82.0",
            ]
        ),
        encoding="utf-8",
    )
    report_docx_path = output_dir / "report.docx"
    report_docx_path.write_bytes(_build_docx_bytes(["洞鉴巡检报告", "原始正文。"]))

    artifacts = maybe_run_xray_trend_enhancement(
        task_id,
        base_report_docx_path=report_docx_path,
    )

    assert artifacts is not None
    assert artifacts.resource_history_path is not None
    assert len(artifacts.chart_paths) == 3
    assert artifacts.trend_state_graph_image_path is not None
    assert artifacts.augmented_report_path == report_docx_path.as_posix()
    assert report_docx_path.exists()

    with ZipFile(report_docx_path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        names = set(archive.namelist())

    assert "附录：趋势增强分析" in document_xml
    assert "四、趋势图表" in document_xml
    assert any(name.startswith("word/media/trend_image_") for name in names)


def _build_xray_unified_json(*, task_id: str) -> dict[str, object]:
    return {
        "schema_version": "unified-json/v1",
        "task_id": task_id,
        "generated_at": "2026-04-18T16:12:40Z",
        "source": {
            "archive_name": "xray-log.tar.gz",
            "archive_size_bytes": 12345,
            "collected_at": None,
        },
        "parser": {
            "name": "xray-collector-parser",
            "version": "0.1.0",
        },
        "host_info": {
            "hostname": "shulei",
            "ip": "10.20.20.208",
            "os_name": "Ubuntu 22.04.5 LTS",
            "os_version": None,
            "kernel_version": "5.15.0-174-generic",
            "timezone": "Asia/Shanghai",
            "uptime_seconds": 89610,
            "last_boot_at": "2026-04-15T06:26:35Z",
        },
        "summary": {
            "overall_status": "warning",
            "service_count": 0,
            "service_running_count": 0,
            "container_count": 20,
            "container_running_count": 18,
            "issue_count": 1,
            "issue_by_severity": {
                "critical": 0,
                "high": 0,
                "medium": 1,
                "low": 0,
                "info": 0,
            },
        },
        "services": [],
        "containers": [],
        "issues": [],
        "warnings": [],
        "metadata": {
            "product_type": "xray",
            "xray_mgmt_memory": "总量 15.6GB，已用 4.3GB (27.69%)，可用 10.8GB",
            "xray_mgmt_disk": "/，80.0GB (87.46%) / 96.4GB，/dev/dm-0 (ext4)",
        },
    }


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
