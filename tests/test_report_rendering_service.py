from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.schemas.report_payload import (
    ReportHost,
    ReportMeta,
    ReportPayloadV1,
    ReportSummary,
)
from app.services.report_rendering_service import (
    HttpCarboneAdapter,
    ReportRenderingError,
    maybe_render_report_from_payload_file,
    render_report_from_payload_file,
)


client = TestClient(app)


def test_render_service_requires_existing_report_payload(tmp_path: Path) -> None:
    template_path = tmp_path / "inspection_report.docx"
    template_path.write_bytes(b"fake-docx")

    with pytest.raises(ReportRenderingError) as exc_info:
        render_report_from_payload_file(
            "tsk_test_001",
            tmp_path / "missing_report_payload.json",
            template_path=template_path,
        )

    assert exc_info.value.code == "report_payload_missing"


def test_render_service_rejects_missing_template(tmp_path: Path) -> None:
    report_payload_path = _write_report_payload(tmp_path / "report_payload.json")

    with pytest.raises(ReportRenderingError) as exc_info:
        render_report_from_payload_file(
            "tsk_test_002",
            report_payload_path,
            template_path=tmp_path / "inspection_report.docx",
        )

    assert exc_info.value.code == "template_missing"


def test_default_template_exists_and_is_valid_docx() -> None:
    template_path = get_settings().default_report_template_path

    assert template_path.exists()
    assert template_path.suffix.lower() == ".docx"

    with ZipFile(template_path) as archive:
        assert archive.testzip() is None
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "{d.report.task_id}" in document_xml
    assert "{d.host.hostname}" in document_xml
    assert "{d.summary.overall_status_label}" in document_xml
    assert "{d.service_rows[i].name}" in document_xml
    assert "{d.service_rows[i+1].name}" in document_xml
    assert "{d.container_rows[i].name}" in document_xml
    assert "{d.container_rows[i+1].name}" in document_xml
    assert "{d.issue_rows[i].id}" in document_xml
    assert "{d.issue_rows[i+1].id}" in document_xml


def test_render_service_detects_existing_template_before_adapter_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CARBONE_BASE_URL", "http://127.0.0.1:4999")
    monkeypatch.setenv("CARBONE_API_TIMEOUT_SECONDS", "1")
    report_payload_path = _write_report_payload(tmp_path / "report_payload.json")
    template_path = get_settings().default_report_template_path

    result = maybe_render_report_from_payload_file(
        "tsk_test_004",
        report_payload_path,
        enabled=True,
        template_path=template_path,
    )

    assert result.attempted is True
    assert result.success is False
    assert result.error_code in {"carbone_unreachable", "carbone_status_failed"}


def test_upload_flow_stays_compatible_when_rendering_is_disabled(tmp_path: Path) -> None:
    report_payload_path = _write_report_payload(tmp_path / "report_payload.json")

    result = maybe_render_report_from_payload_file(
        "tsk_test_003",
        report_payload_path,
        enabled=False,
    )

    assert result.attempted is False
    assert result.success is False
    assert result.output_path is None
    assert result.error_code is None


def test_http_carbone_adapter_fails_cleanly_when_runtime_is_unreachable(
    tmp_path: Path,
) -> None:
    report_payload_path = _write_report_payload(tmp_path / "report_payload.json")
    template_path = get_settings().default_report_template_path
    output_path = tmp_path / "report.docx"
    adapter = HttpCarboneAdapter(
        base_url="http://127.0.0.1:4999",
        timeout_seconds=1,
        carbone_version="5",
    )

    with pytest.raises(ReportRenderingError) as exc_info:
        render_report_from_payload_file(
            "tsk_test_005",
            report_payload_path,
            template_path=template_path,
            output_path=output_path,
            adapter=adapter,
        )

    assert exc_info.value.code == "carbone_unreachable"


def test_render_report_endpoint_returns_structured_error_when_carbone_is_unreachable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_template_path = Path(__file__).resolve().parents[1] / "templates" / "inspection_report.docx"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CARBONE_BASE_URL", "http://127.0.0.1:4999")
    monkeypatch.setenv("CARBONE_API_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv(
        "DEFAULT_REPORT_TEMPLATE_PATH",
        repo_template_path.as_posix(),
    )

    response = client.post(
        "/api/tasks",
        files={"file": ("host-a-logs.zip", _build_zip_bytes(), "application/zip")},
        data={"parser_profile": "default", "report_lang": "zh-CN"},
    )
    task_id = response.json()["data"]["task_id"]

    render_response = client.post(f"/api/tasks/{task_id}/render-report")

    assert render_response.status_code == 503
    payload = render_response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "carbone_unreachable"

    task_response = client.get(f"/api/tasks/{task_id}")
    assert task_response.status_code == 200
    assert task_response.json()["data"]["status"] == "render_failed"


def test_render_service_runs_xray_trend_post_processing_when_history_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "disabled")
    task_id = "tsk_xray_render_trend_001"
    task_workdir = tmp_path / "workdir" / task_id
    resource_dir = task_workdir / "resources"
    resource_dir.mkdir(parents=True)

    (task_workdir / "unified.json").write_text(
        json.dumps(
            {
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
                "host_info": {"hostname": "shulei"},
                "summary": {
                    "overall_status": "warning",
                    "service_count": 0,
                    "service_running_count": 0,
                    "container_count": 0,
                    "container_running_count": 0,
                    "issue_count": 0,
                    "issue_by_severity": {
                        "critical": 0,
                        "high": 0,
                        "medium": 0,
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
            },
            ensure_ascii=False,
        ),
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

    report_payload_path = _write_report_payload(tmp_path / "report_payload.json")
    template_path = tmp_path / "inspection_report.docx"
    template_path.write_bytes(b"fake-docx")
    output_path = tmp_path / "outputs" / task_id / "report.docx"

    class FakeDocxAdapter:
        def render(self, *, template_path: Path, report_payload, output_path: Path) -> None:  # noqa: ANN001
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(_build_docx_bytes(["洞鉴巡检报告", "原始正文。"]))

    result = maybe_render_report_from_payload_file(
        task_id,
        report_payload_path,
        enabled=True,
        template_path=template_path,
        output_path=output_path,
        adapter=FakeDocxAdapter(),
    )

    assert result.success is True
    assert result.details["xray_trend_status"] == "augmented"
    assert result.details["xray_trend_chart_count"] == 3
    assert Path(str(result.details["xray_trend_input_path"])).exists()
    assert Path(str(result.details["xray_trend_assessment_path"])).exists()
    with ZipFile(output_path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "附录：趋势增强分析" in document_xml


def _write_report_payload(target_path: Path) -> Path:
    report_payload = ReportPayloadV1(
        payload_version="report-payload/v1",
        report=ReportMeta(
            title="Inspection Report",
            generated_at="2026-04-11T10:15:34Z",
            task_id="tsk_test_payload",
            report_lang="zh-CN",
        ),
        host=ReportHost(
            hostname="host-a",
            ip=None,
            os=None,
            kernel_version=None,
            timezone=None,
        ),
        summary=ReportSummary(
            overall_status="unknown",
            overall_status_label="Unknown",
            service_count=0,
            service_running_count=0,
            container_count=0,
            container_running_count=0,
            issue_count=0,
        ),
        service_rows=[],
        container_rows=[],
        issue_rows=[],
        highlights=["Upload completed."],
        recommendations=["Enable real rendering later."],
        appendix={"parser_name": "upload-parser-stub"},
    )
    target_path.write_text(
        report_payload.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return target_path


def _build_zip_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("logs/system.log", "system ok\n")
        archive.writestr("meta/info.txt", "metadata\n")
    return buffer.getvalue()


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
