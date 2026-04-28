from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.log_evidence import (
    DerivedSummary,
    LogEvidenceV1,
    LogFinding,
    ResourceSignal,
    RuntimeComponentEvidence,
)
from app.services import waf_audit_task_service


client = TestClient(app)


def test_waf_audit_endpoint_flow_generates_all_phase1_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPLOADS_DIR", (tmp_path / "uploads").as_posix())
    monkeypatch.setenv("WORKDIR_DIR", (tmp_path / "workdir").as_posix())
    monkeypatch.setenv("OUTPUTS_DIR", (tmp_path / "outputs").as_posix())
    monkeypatch.setenv("TASKS_DB_PATH", (tmp_path / "tasks.sqlite3").as_posix())

    def fake_extract_waf_log_evidence(**kwargs):  # noqa: ANN003
        return LogEvidenceV1(
            task_id=kwargs["task_id"],
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

    monkeypatch.setattr(
        waf_audit_task_service,
        "extract_waf_log_evidence",
        fake_extract_waf_log_evidence,
    )

    response = client.post(
        "/api/waf-audits",
        files={
            "report_file": ("report.docx", _build_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "log_file": ("waf_logs.zip", _build_log_zip_bytes(), "application/zip"),
        },
        data={"report_lang": "zh-CN"},
    )

    assert response.status_code == 201
    payload = response.json()
    task_id = payload["data"]["task_id"]
    assert payload["data"]["status"] == "completed"
    assert Path(payload["data"]["report_claims_path"]).exists()
    assert Path(payload["data"]["log_evidence_path"]).exists()
    assert Path(payload["data"]["audit_result_path"]).exists()
    assert Path(payload["data"]["audit_opinion_path"]).exists()
    assert Path(payload["data"]["audit_augmented_report_path"]).exists()

    list_response = client.get("/api/waf-audits")
    assert list_response.status_code == 200
    assert any(item["task_id"] == task_id for item in list_response.json()["data"])

    detail_response = client.get(f"/api/waf-audits/{task_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["summary"]["claim_count"] >= 1

    claims_response = client.get(f"/api/waf-audits/{task_id}/claims")
    assert claims_response.status_code == 200
    assert claims_response.json()["schema_version"] == "report-claims/v1"

    audit_result_response = client.get(f"/api/waf-audits/{task_id}/audit-result")
    assert audit_result_response.status_code == 200
    assert audit_result_response.json()["schema_version"] == "audit-result/v1"

    opinion_response = client.get(f"/api/waf-audits/{task_id}/audit-opinion")
    assert opinion_response.status_code == 200
    assert "雷池 WAF 巡检报告审核意见单" in opinion_response.text
    assert "资源使用率核验" in opinion_response.text
    assert "容器运行状况核验" in opinion_response.text

    augmented_response = client.get(f"/api/waf-audits/{task_id}/augmented-report")
    assert augmented_response.status_code == 200
    assert augmented_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    with ZipFile(BytesIO(augmented_response.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "附录：日志核验意见" in document_xml
    assert "资源使用率核验" in document_xml
    assert "容器运行状况核验" in document_xml


def test_waf_audit_endpoint_reuses_preprocessing_id_without_reuploading_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPLOADS_DIR", (tmp_path / "uploads").as_posix())
    monkeypatch.setenv("WORKDIR_DIR", (tmp_path / "workdir").as_posix())
    monkeypatch.setenv("OUTPUTS_DIR", (tmp_path / "outputs").as_posix())
    monkeypatch.setenv("TASKS_DB_PATH", (tmp_path / "tasks.sqlite3").as_posix())

    preprocessing_response = client.post(
        "/api/waf/preprocessing",
        files={"file": ("waf_logs.zip", _build_log_zip_bytes(), "application/zip")},
    )
    assert preprocessing_response.status_code == 201
    preprocessing_id = preprocessing_response.json()["data"]["preprocessing_id"]

    response = client.post(
        "/api/waf-audits",
        files={
            "report_file": ("report.docx", _build_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        },
        data={"preprocessing_id": preprocessing_id, "report_lang": "zh-CN"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["preprocessing_id"] == preprocessing_id
    assert data["log_file_path"] is None
    assert Path(data["report_claims_path"]).exists()
    assert Path(data["log_evidence_path"]).exists()
    assert Path(data["audit_result_path"]).exists()
    assert Path(data["audit_opinion_path"]).exists()
    assert Path(data["audit_augmented_report_path"]).exists()
    opinion_text = Path(data["audit_opinion_path"]).read_text(encoding="utf-8")
    assert "容器运行状况核验" in opinion_text

    detail_response = client.get(f"/api/waf-audits/{data['task_id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["preprocessing_id"] == preprocessing_id


def test_waf_audit_endpoint_rejects_invalid_preprocessing_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPLOADS_DIR", (tmp_path / "uploads").as_posix())
    monkeypatch.setenv("WORKDIR_DIR", (tmp_path / "workdir").as_posix())
    monkeypatch.setenv("OUTPUTS_DIR", (tmp_path / "outputs").as_posix())
    monkeypatch.setenv("TASKS_DB_PATH", (tmp_path / "tasks.sqlite3").as_posix())

    response = client.post(
        "/api/waf-audits",
        files={
            "report_file": ("report.docx", _build_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        },
        data={"preprocessing_id": "not-a-prep-id", "report_lang": "zh-CN"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_preprocessing_id"


def test_waf_document_only_endpoint_generates_review_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPLOADS_DIR", (tmp_path / "uploads").as_posix())
    monkeypatch.setenv("WORKDIR_DIR", (tmp_path / "workdir").as_posix())
    monkeypatch.setenv("OUTPUTS_DIR", (tmp_path / "outputs").as_posix())
    monkeypatch.setenv("TASKS_DB_PATH", (tmp_path / "tasks.sqlite3").as_posix())

    response = client.post(
        "/api/waf-audits/document-only",
        files={
            "report_file": (
                "report.docx",
                _build_document_only_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
        data={"report_lang": "zh-CN"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    task_id = data["task_id"]
    assert data["review_mode"] == "document_only"
    assert data["log_evidence_path"] is None
    assert data["audit_result_path"] is None
    assert Path(data["document_review_input_path"]).exists()
    assert Path(data["llm_review_json_path"]).exists()
    assert Path(data["audit_opinion_path"]).exists()
    assert Path(data["audit_augmented_report_path"]).exists()

    detail_response = client.get(f"/api/waf-audits/{task_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["review_mode"] == "document_only"

    review_input_response = client.get(f"/api/waf-audits/{task_id}/document-review-input")
    assert review_input_response.status_code == 200
    assert review_input_response.json()["review_mode"] == "document_only"
    assert review_input_response.json()["abnormal_topics"]

    review_result_response = client.get(f"/api/waf-audits/{task_id}/document-review")
    assert review_result_response.status_code == 200
    assert review_result_response.json()["review_mode"] == "document_only"
    assert "未结合原始日志做一致性核验" in review_result_response.json()["disclaimer"]

    opinion_response = client.get(f"/api/waf-audits/{task_id}/audit-opinion")
    assert opinion_response.status_code == 200
    assert "雷池 WAF 文档直审意见" in opinion_response.text
    assert "异常情况及处置操作" in opinion_response.text
    assert "经日志核验" not in opinion_response.text

    augmented_response = client.get(f"/api/waf-audits/{task_id}/augmented-report")
    assert augmented_response.status_code == 200
    with ZipFile(BytesIO(augmented_response.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "附录：文档直审意见" in document_xml
    assert "未结合原始日志做一致性核验" in document_xml


def _build_docx_bytes() -> bytes:
    paragraphs = [
        "一、部署信息",
        "本次巡检产品版本为 7.0.1",
        "二、巡检结论",
        "Redis 组件存在异常，且整体运行异常。",
    ]
    tables = [
        [
            ["检查项", "检查结果"],
            ["Redis 运行状态", "重启"],
            ["内存使用情况", "偏高"],
        ]
    ]
    body_items = []
    for paragraph in paragraphs:
        body_items.append(f"<w:p><w:r><w:t>{_xml_escape(paragraph)}</w:t></w:r></w:p>")
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


def _build_log_zip_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("system/system_info", "hostname=waf-host\nkernel=5.15.0-test\n")
        archive.writestr("containers/docker_ps", "NAMES\tIMAGE\tSTATUS\tPORTS\nredis\tredis:7\tRestarting (1)\t\n")
        archive.writestr(
            "container/docker_stats.txt",
            "\n".join(
                [
                    "CONTAINER ID NAME CPU % MEM USAGE / LIMIT MEM % NET I/O BLOCK I/O PIDS",
                    "abc123 redis 12.5% 120MiB / 1GiB 11.7% 0B / 0B 0B / 0B 12",
                ]
            ),
        )
        archive.writestr("resources/resource_summary", "memory=88%\n")
        archive.writestr("logs/app.log", "redis restarting\n")
    return buffer.getvalue()


def _build_document_only_docx_bytes() -> bytes:
    paragraphs = [
        "一、巡检发现",
        "内存使用率达到87%，建议关注。",
        "xray-web容器服务异常，容器不健康。",
        "二、巡检结论",
        "当前系统存在异常，需要进一步处理。",
    ]
    body_items = []
    for paragraph in paragraphs:
        body_items.append(f"<w:p><w:r><w:t>{_xml_escape(paragraph)}</w:t></w:r></w:p>")

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
