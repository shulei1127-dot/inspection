from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.schemas.log_analyzer import AnalyzeDirectorySource, AnalyzeRequestV1, AnalyzeResponseV1
from app.services.log_analyzer import (
    LocalLogAnalyzer,
    LogAnalyzerError,
    RemoteLogAnalyzer,
    build_log_analyzer,
)


def test_local_log_analyzer_returns_versioned_contract_response(tmp_path: Path) -> None:
    _write_supported_bundle(tmp_path)
    analyzer = LocalLogAnalyzer()
    request = AnalyzeRequestV1(
        task_id="tsk_local_contract_001",
        source=AnalyzeDirectorySource(path=tmp_path.as_posix()),
        archive_name="bundle.zip",
        archive_size_bytes=123,
    )

    response = analyzer.analyze(request)

    assert response.response_version == "analyze-response/v1"
    assert response.schema_version == "unified-json/v1"
    assert response.product_type == "unknown"
    assert response.result.schema_version == "unified-json/v1"
    assert response.result.task_id == "tsk_local_contract_001"
    assert response.result.host_info.hostname == "host-a"
    assert response.input_summary is not None
    assert response.input_summary.path == tmp_path.as_posix()
    assert response.input_summary.file_count == 3
    assert response.input_summary.directory_count == 2
    assert AnalyzeResponseV1.model_validate(response.model_dump()).result.task_id == "tsk_local_contract_001"


def test_build_log_analyzer_switches_between_local_and_remote(monkeypatch) -> None:
    monkeypatch.setenv("ANALYZER_MODE", "remote")
    monkeypatch.setenv("ANALYZER_BASE_URL", "http://analyzer.local")

    remote_analyzer = build_log_analyzer()

    assert isinstance(remote_analyzer, RemoteLogAnalyzer)

    monkeypatch.setenv("ANALYZER_MODE", "local")
    local_analyzer = build_log_analyzer()

    assert isinstance(local_analyzer, LocalLogAnalyzer)


def test_platform_config_defaults_to_remote_analyzer_when_env_is_unset(monkeypatch) -> None:
    monkeypatch.delenv("ANALYZER_MODE", raising=False)

    settings = get_settings()
    analyzer = build_log_analyzer()

    assert settings.analyzer_mode == "remote"
    assert isinstance(analyzer, RemoteLogAnalyzer)


def test_remote_log_analyzer_validates_versioned_response_contract() -> None:
    expected_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal expected_request
        expected_request = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "response_version": "analyze-response/v1",
                "schema_version": "unified-json/v1",
                "product_type": "unknown",
                "analyzer_version": "0.1.0",
                "analysis_started_at": "2026-04-13T10:00:00Z",
                "analysis_finished_at": "2026-04-13T10:00:01Z",
                "warnings": [],
                "input_summary": {
                    "source_type": "directory",
                    "path": "/tmp/task-1",
                    "file_count": 3,
                    "directory_count": 2,
                },
                "result": {
                    "schema_version": "unified-json/v1",
                    "task_id": "tsk_remote_contract_001",
                    "generated_at": "2026-04-13T10:00:01Z",
                    "source": {
                        "archive_name": "bundle.zip",
                        "archive_size_bytes": 321,
                        "collected_at": None,
                    },
                    "parser": {
                        "name": "default-linux-parser",
                        "version": "0.5.0",
                    },
                    "host_info": {
                        "hostname": "host-a",
                        "ip": "10.0.0.8",
                        "os_name": "Ubuntu",
                        "os_version": "22.04",
                        "kernel_version": "5.15.0",
                        "timezone": "UTC",
                        "uptime_seconds": 7200,
                        "last_boot_at": "2026-04-13T08:00:00Z",
                    },
                    "summary": {
                        "overall_status": "healthy",
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
                        "extracted_file_count": 3,
                        "extracted_directory_count": 2,
                    },
                },
            },
        )

    analyzer = RemoteLogAnalyzer(
        base_url="http://analyzer.local",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    request = AnalyzeRequestV1(
        task_id="tsk_remote_contract_001",
        source=AnalyzeDirectorySource(path="/tmp/task-1"),
        archive_name="bundle.zip",
        archive_size_bytes=321,
    )

    response = analyzer.analyze(request)

    assert '"request_version":"analyze-request/v1"' in expected_request
    assert '"type":"directory"' in expected_request
    assert response.response_version == "analyze-response/v1"
    assert response.product_type == "unknown"
    assert response.result.task_id == "tsk_remote_contract_001"
    assert response.input_summary is not None
    assert response.input_summary.path == "/tmp/task-1"


def test_remote_log_analyzer_rejects_invalid_contract_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json={"response_version": "analyze-response/v1"})

    analyzer = RemoteLogAnalyzer(
        base_url="http://analyzer.local",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    request = AnalyzeRequestV1(
        task_id="tsk_remote_contract_002",
        source=AnalyzeDirectorySource(path="/tmp/task-2"),
    )

    with pytest.raises(LogAnalyzerError) as exc_info:
        analyzer.analyze(request)

    assert exc_info.value.code == "analyzer_invalid_response"


def test_remote_log_analyzer_preserves_structured_json_errors_from_analyzer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(
            404,
            json={
                "success": False,
                "error": {
                    "code": "source_not_found",
                    "message": "Requested source directory does not exist.",
                    "details": {"path": "/tmp/missing"},
                },
            },
        )

    analyzer = RemoteLogAnalyzer(
        base_url="http://analyzer.local",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    request = AnalyzeRequestV1(
        task_id="tsk_remote_contract_003",
        source=AnalyzeDirectorySource(path="/tmp/task-3"),
    )

    with pytest.raises(LogAnalyzerError) as exc_info:
        analyzer.analyze(request)

    assert exc_info.value.code == "source_not_found"
    assert exc_info.value.message == "Requested source directory does not exist."
    assert exc_info.value.details["path"] == "/tmp/missing"
    assert exc_info.value.details["status_code"] == 404


def test_remote_log_analyzer_falls_back_for_non_json_error_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(
            500,
            text="upstream exploded in plain text",
            headers={"content-type": "text/plain"},
        )

    analyzer = RemoteLogAnalyzer(
        base_url="http://analyzer.local",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    request = AnalyzeRequestV1(
        task_id="tsk_remote_contract_004",
        source=AnalyzeDirectorySource(path="/tmp/task-4"),
    )

    with pytest.raises(LogAnalyzerError) as exc_info:
        analyzer.analyze(request)

    assert exc_info.value.code == "analyzer_request_failed"
    assert exc_info.value.details["status_code"] == 500
    assert exc_info.value.details["content_type"] == "text/plain"
    assert "upstream exploded" in str(exc_info.value.details["response_excerpt"])


def _write_supported_bundle(root_dir: Path) -> None:
    system_dir = root_dir / "system"
    container_dir = root_dir / "containers"
    system_dir.mkdir(parents=True)
    container_dir.mkdir(parents=True)

    (system_dir / "system_info").write_text(
        "\n".join(
            [
                "hostname=host-a",
                "pretty_name=Ubuntu 22.04 LTS",
                "kernel=5.15.0-105-generic",
                "timezone=UTC",
                "uptime_seconds=7200",
                "ip=10.0.0.8",
                "last_boot_at=2026-04-13T08:00:00Z",
            ]
        ),
        encoding="utf-8",
    )
    (system_dir / "systemctl_status").write_text(
        "UNIT LOAD ACTIVE SUB DESCRIPTION\n"
        "nginx.service loaded active running A high performance web server\n",
        encoding="utf-8",
    )
    (container_dir / "docker_ps").write_text(
        "NAMES\tIMAGE\tSTATUS\tPORTS\n"
        "api\tnginx:1.27\tUp 5 minutes\t0.0.0.0:8080->80/tcp\n",
        encoding="utf-8",
    )
