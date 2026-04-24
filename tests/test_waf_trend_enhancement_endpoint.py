import io
import tarfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_waf_trend_enhancement_endpoint_runs_from_preprocessing_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _configure_runtime_dirs(tmp_path, monkeypatch)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "disabled")

    preprocessing_id = _create_preprocessing_task()

    response = client.post(
        "/api/waf/trend-enhancements",
        data={"preprocessing_id": preprocessing_id},
    )

    assert response.status_code == 201
    payload = response.json()
    data = payload["data"]
    assert payload["success"] is True
    assert data["trend_id"].startswith("trd_")
    assert data["preprocessing_id"] == preprocessing_id
    assert data["status"] == "completed"
    assert data["contract_version"] == "waf-trend-enhancement-response/v1"
    assert data["source_status_analysis_md_path"].endswith(f"/workdir/{preprocessing_id}/status_analysis.md")
    assert data["source_report_docx_path"] is None
    assert data["augmented_report_path"] is None
    assert data["summary"]["data_quality"] == "sufficient"
    assert data["summary"]["chart_count"] == 3
    assert data["summary"]["metric_statuses"]["cpu"] in {"stable", "deteriorating", "pressure_high", "unknown"}

    for key in [
        "source_report_md_path",
        "trend_input_path",
        "trend_assessment_path",
        "trend_summary_path",
        "trend_state_graph_path",
        "output_trend_state_graph_path",
    ]:
        assert Path(data[key]).exists()
    assert len(data["chart_paths"]) == 3
    assert all(Path(path).exists() for path in data["chart_paths"])

    detail_response = client.get(f"/api/waf/trend-enhancements/{data['trend_id']}")
    assert detail_response.status_code == 200
    detail_data = detail_response.json()["data"]
    assert detail_data["trend_id"] == data["trend_id"]
    assert detail_data["trend_summary_path"] == data["trend_summary_path"]

    summary_response = client.get(f"/api/waf/trend-enhancements/{data['trend_id']}/summary")
    assert summary_response.status_code == 200
    assert "趋势增强摘要" in summary_response.text
    assert summary_response.headers["content-type"].startswith("text/markdown")


def test_waf_trend_enhancement_endpoint_can_append_to_uploaded_docx(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _configure_runtime_dirs(tmp_path, monkeypatch)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "disabled")
    preprocessing_id = _create_preprocessing_task()

    response = client.post(
        "/api/waf/trend-enhancements",
        data={"preprocessing_id": preprocessing_id},
        files={
            "base_report_docx": (
                "base_report.docx",
                _build_docx_bytes(["基础巡检报告", "原始正文保留。"]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["source_report_docx_path"] is not None
    assert data["augmented_report_path"] is not None
    assert Path(data["source_report_docx_path"]).exists()
    assert Path(data["augmented_report_path"]).exists()

    report_response = client.get(f"/api/waf/trend-enhancements/{data['trend_id']}/augmented-report")
    assert report_response.status_code == 200
    assert report_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_waf_trend_enhancement_endpoint_returns_404_for_missing_preprocessing_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _configure_runtime_dirs(tmp_path, monkeypatch)

    response = client.post(
        "/api/waf/trend-enhancements",
        data={"preprocessing_id": "prep_20260418_120000_deadbeef"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "preprocessing_artifact_not_found"


def test_waf_trend_enhancement_read_endpoint_returns_400_for_invalid_id_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _configure_runtime_dirs(tmp_path, monkeypatch)

    response = client.get("/api/waf/trend-enhancements/not-a-trend-id")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_trend_id"


def test_waf_trend_enhancement_read_endpoint_returns_404_for_missing_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _configure_runtime_dirs(tmp_path, monkeypatch)

    response = client.get("/api/waf/trend-enhancements/trd_20260418_120000_deadbeef")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "artifact_not_found"


def test_waf_trend_enhancement_augmented_report_download_returns_404_when_not_generated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _configure_runtime_dirs(tmp_path, monkeypatch)
    monkeypatch.setenv("MERMAID_RENDERER_MODE", "disabled")
    preprocessing_id = _create_preprocessing_task()
    response = client.post(
        "/api/waf/trend-enhancements",
        data={"preprocessing_id": preprocessing_id},
    )
    trend_id = response.json()["data"]["trend_id"]

    report_response = client.get(f"/api/waf/trend-enhancements/{trend_id}/augmented-report")

    assert report_response.status_code == 404
    assert report_response.json()["error"]["code"] == "artifact_not_found"


def test_waf_trend_enhancement_endpoint_rejects_invalid_docx(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _configure_runtime_dirs(tmp_path, monkeypatch)
    preprocessing_id = _create_preprocessing_task()

    response = client.post(
        "/api/waf/trend-enhancements",
        data={"preprocessing_id": preprocessing_id},
        files={
            "base_report_docx": (
                "base_report.docx",
                b"not a docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_report_file"


def _configure_runtime_dirs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOADS_DIR", (tmp_path / "uploads").as_posix())
    monkeypatch.setenv("WORKDIR_DIR", (tmp_path / "workdir").as_posix())
    monkeypatch.setenv("OUTPUTS_DIR", (tmp_path / "outputs").as_posix())


def _create_preprocessing_task() -> str:
    response = client.post(
        "/api/waf/preprocessing",
        files={
            "file": (
                "waf-full-log.tar.gz",
                _build_tar_gz_bytes(
                    {
                        "waf-log/metadata/collection_info.txt": "collected_at: 2026-04-16 04:54:04 UTC\n",
                        "waf-log/resources/resource_history.csv": "\n".join(
                            [
                                "timestamp,cpu,memory,disk",
                                "2026-04-14 00:00:00,20%,60%,50%",
                                "2026-04-14 12:00:00,22%,62%,52%",
                                "2026-04-15 00:00:00,24%,64%,54%",
                                "2026-04-15 12:00:00,26%,66%,56%",
                                "2026-04-16 00:00:00,28%,68%,58%",
                            ]
                        ),
                        "waf-log/system/top.txt": "\n".join(
                            [
                                "top - 04:54:34 up 10 days, 01:00, 1 user, load average: 0.86, 0.35, 0.25",
                                "%Cpu(s): 20.0 us,  8.0 sy,  0.0 ni, 72.0 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st",
                                "MiB Mem :  100.0 total,    10.0 free,  68.0 used,   22.0 buff/cache",
                            ]
                        ),
                    }
                ),
                "application/gzip",
            )
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["preprocessing_id"]


def _build_tar_gz_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
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
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()
