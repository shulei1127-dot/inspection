import io
import json
import tarfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_waf_preprocessing_endpoint_generates_status_analysis_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPLOADS_DIR", (tmp_path / "uploads").as_posix())
    monkeypatch.setenv("WORKDIR_DIR", (tmp_path / "workdir").as_posix())
    monkeypatch.setenv("OUTPUTS_DIR", (tmp_path / "outputs").as_posix())

    response = client.post(
        "/api/waf/preprocessing",
        files={
            "file": (
                "waf-full-log.tar.gz",
                _build_tar_gz_bytes(
                    {
                        "waf-log/metadata/collection_info.txt": "collected_at: 2026-04-16 04:54:04 UTC\n",
                        "waf-log/system/top.txt": "\n".join(
                            [
                                "top - 04:54:34 up 125 days, 23:00, 1 user, load average: 0.86, 0.35, 0.25",
                                "%Cpu(s): 1.3 us,  6.3 sy,  0.0 ni, 92.4 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st",
                                "MiB Mem :  7944.9 total,    632.3 free,  4309.7 used,   3002.9 buff/cache",
                            ]
                        ),
                        "waf-log/system/disk.txt": "\n".join(
                            [
                                "Filesystem      Size  Used Avail Use% Mounted on",
                                "/dev/sda2       100G   66G   34G  66% /",
                            ]
                        ),
                    }
                ),
                "application/gzip",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    data = payload["data"]
    assert payload["success"] is True
    assert data["preprocessing_id"].startswith("prep_")
    assert data["status"] == "completed"
    assert data["contract_version"] == "waf-preprocessing-response/v1"
    assert data["filename"] == "waf-full-log.tar.gz"
    assert data["source_archive_path"].endswith(".tar.gz")
    assert data["source_directory_path"].endswith("/waf-log")
    assert data["summary"]["coverage_level"] == "full"
    assert data["summary"]["resource_history_point_count"] == 1

    for key in [
        "source_archive_path",
        "extracted_dir_path",
        "resource_history_csv_path",
        "status_analysis_evidence_path",
        "status_analysis_summary_path",
        "status_analysis_md_path",
    ]:
        assert Path(data[key]).exists()

    resource_history_text = Path(data["resource_history_csv_path"]).read_text(encoding="utf-8")
    assert resource_history_text.splitlines() == [
        "timestamp,cpu,memory,disk",
        "2026-04-16T00:00:00Z,7.6,54.2,66.0",
    ]
    summary = json.loads(Path(data["status_analysis_summary_path"]).read_text(encoding="utf-8"))
    assert summary["cpu_snapshot"]["current_value"] == 7.6
    assert summary["memory_snapshot"]["current_value"] == 54.2
    assert summary["disk_snapshot"]["current_value"] == 66.0

    detail_response = client.get(f"/api/waf/preprocessing/{data['preprocessing_id']}")
    assert detail_response.status_code == 200
    detail_data = detail_response.json()["data"]
    assert detail_data["preprocessing_id"] == data["preprocessing_id"]
    assert detail_data["status_analysis_md_path"] == data["status_analysis_md_path"]

    markdown_response = client.get(f"/api/waf/preprocessing/{data['preprocessing_id']}/status-analysis")
    assert markdown_response.status_code == 200
    assert "SafeLine WAF 状态分析报告" in markdown_response.text
    assert markdown_response.headers["content-type"].startswith("text/markdown")


def test_waf_preprocessing_read_endpoint_rejects_invalid_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = client.get("/api/waf/preprocessing/../../etc/passwd")

    assert response.status_code == 404


def test_waf_preprocessing_read_endpoint_returns_400_for_invalid_id_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = client.get("/api/waf/preprocessing/not-a-prep-id")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_preprocessing_id"


def test_waf_preprocessing_read_endpoint_returns_404_for_missing_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = client.get("/api/waf/preprocessing/prep_20260418_120000_deadbeef")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "artifact_not_found"


def test_waf_preprocessing_endpoint_rejects_unsupported_archive_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = client.post(
        "/api/waf/preprocessing",
        files={"file": ("waf.log", b"not an archive", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_archive_type"


def test_waf_preprocessing_endpoint_rejects_invalid_archive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = client.post(
        "/api/waf/preprocessing",
        files={"file": ("waf-full-log.tar.gz", b"not a tar archive", "application/gzip")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_archive"


def test_waf_preprocessing_endpoint_rejects_unsafe_zip_member(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = client.post(
        "/api/waf/preprocessing",
        files={"file": ("unsafe.zip", _build_zip_bytes({"../escape.txt": "bad"}), "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "extract_failed"
    assert response.json()["error"]["details"]["reason"] == "unsafe_archive_path"


def _build_tar_gz_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _build_zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
