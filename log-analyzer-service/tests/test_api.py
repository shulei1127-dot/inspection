import json
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analyze import AnalyzeResponseV1
from app.schemas.waf_evidence import WafEvidenceResponseV1
from app.parsers import linux_default_parser


client = TestClient(app)
XRAY_FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "xray_collector_v1" / "sample-bundle"
)
MINION_REPORT_FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "minion_report_v1" / "sample-bundle"
)


def test_get_health_returns_status_service_and_version() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "log-analyzer-service"
    assert payload["version"] == "0.1.0"


def test_post_analyze_happy_path_returns_versioned_response(tmp_path: Path) -> None:
    _write_supported_bundle(tmp_path)

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_001",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
            "archive_name": "bundle.tar.gz",
            "archive_size_bytes": 1234,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    validated = AnalyzeResponseV1.model_validate(payload)

    assert validated.response_version == "analyze-response/v1"
    assert validated.schema_version == "unified-json/v1"
    assert validated.product_type == "unknown"
    assert validated.result.task_id == "tsk_analyzer_001"
    assert validated.result.host_info.hostname == "host-a"
    assert validated.result.summary.service_count == 1
    assert validated.result.summary.container_count == 1
    assert validated.input_summary is not None
    assert validated.input_summary.path == tmp_path.resolve().as_posix()
    assert validated.input_summary.file_count == 3
    assert validated.input_summary.directory_count == 2


def test_post_analyze_parses_service_enabled_marker_from_canonical_status(tmp_path: Path) -> None:
    system_dir = tmp_path / "system"
    container_dir = tmp_path / "containers"
    system_dir.mkdir(parents=True)
    container_dir.mkdir(parents=True)

    (system_dir / "system_info").write_text(
        "\n".join(
            [
                "hostname=host-service-enabled",
                "kernel=5.15.0-test",
                "timezone=UTC",
                "uptime_seconds=1200",
                "last_boot_at=2026-04-13T08:00:00Z",
            ]
        ),
        encoding="utf-8",
    )
    (system_dir / "systemctl_status").write_text(
        "\n".join(
            [
                "UNIT LOAD ACTIVE SUB DESCRIPTION",
                "minion.service loaded active running minion service [enabled=true]",
                "fwupd-refresh.service loaded failed failed fwupd-refresh.service",
            ]
        ),
        encoding="utf-8",
    )

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_service_enabled",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
        },
    )

    assert response.status_code == 200
    validated = AnalyzeResponseV1.model_validate(response.json())
    minion = next(service for service in validated.result.services if service.name == "minion")
    fwupd = next(service for service in validated.result.services if service.name == "fwupd-refresh")

    assert minion.enabled is True
    assert minion.display_name == "minion service"
    assert fwupd.enabled is None


def test_post_analyze_parses_docker_rows_when_ports_column_is_empty(tmp_path: Path) -> None:
    system_dir = tmp_path / "system"
    container_dir = tmp_path / "containers"
    system_dir.mkdir(parents=True)
    container_dir.mkdir(parents=True)

    (system_dir / "system_info").write_text(
        "\n".join(
            [
                "hostname=host-b",
                "kernel=5.15.0-test",
                "timezone=UTC",
                "uptime_seconds=1200",
                "last_boot_at=2026-04-13T08:00:00Z",
            ]
        ),
        encoding="utf-8",
    )
    (container_dir / "docker_ps").write_text(
        "\n".join(
            [
                "CONTAINER ID   IMAGE          COMMAND             CREATED        STATUS                  PORTS                 NAMES",
                'abc123         nginx:1.27     "/docker-entry"     3 months ago   Up 3 months (healthy)   0.0.0.0:443->443/tcp  xray-nginx',
                'def456         app:latest     "bash deploy.sh"    3 months ago   Up 3 months (healthy)                         xray-deploy',
                'ghi789         app:latest     "bash run.sh"       3 months ago   Exited (1) 2 hours ago                         xray-web',
            ]
        ),
        encoding="utf-8",
    )

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_docker_empty_ports",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
        },
    )

    assert response.status_code == 200
    validated = AnalyzeResponseV1.model_validate(response.json())

    assert validated.result.summary.container_count == 3
    assert [container.name for container in validated.result.containers] == [
        "xray-nginx",
        "xray-deploy",
        "xray-web",
    ]
    assert any(issue.related_object_name == "xray-web" for issue in validated.result.issues)


def test_post_analyze_recognizes_xray_collector_input(tmp_path: Path) -> None:
    xray_root = tmp_path / "xray-collector.20260413123039"
    shutil.copytree(XRAY_FIXTURE_DIR, xray_root)

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_xray_001",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
            "archive_name": "xray-collector.20260413123039.tar.gz",
            "archive_size_bytes": 4096,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    validated = AnalyzeResponseV1.model_validate(payload)

    assert validated.product_type == "xray"
    assert validated.result.task_id == "tsk_analyzer_xray_001"
    assert validated.result.parser is not None
    assert validated.result.parser.name == "xray-collector-parser"
    assert validated.result.host_info.hostname == "24waf"
    assert validated.result.host_info.ip == "10.10.20.30"
    assert validated.result.host_info.timezone == "Etc/UTC"
    assert validated.result.host_info.last_boot_at == "2026-03-22T05:08:48Z"
    assert validated.result.summary.overall_status == "warning"
    assert validated.result.summary.service_count == 2
    assert validated.result.summary.container_count == 3
    assert validated.result.summary.issue_count == 2
    assert [service.name for service in validated.result.services] == [
        "fwupd-refresh",
        "minion",
    ]
    assert any(service.name == "minion" and service.status == "running" for service in validated.result.services)
    assert any(service.name == "minion" and service.enabled is True for service in validated.result.services)
    assert any(service.name == "fwupd-refresh" and service.status == "failed" for service in validated.result.services)
    assert validated.result.containers[0].name == "xray-nginx"
    assert any(container.name == "xray-upgrader" for container in validated.result.containers)
    assert any(container.name == "xray-gunkit-base" for container in validated.result.containers)
    assert validated.result.metadata["collector_type"] == "xray-collector/v1"
    assert validated.result.metadata["product_type"] == "xray"
    assert validated.result.metadata["parser_route"] == "xray-collector-parser"
    assert any("xray-collector/v1 input detected" in warning for warning in validated.warnings)


def test_post_analyze_recognizes_minion_report_input(tmp_path: Path) -> None:
    report_root = tmp_path / "minion-report"
    shutil.copytree(MINION_REPORT_FIXTURE_DIR, report_root)

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_minion_report_001",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
            "archive_name": "minion_report.gz",
            "archive_size_bytes": 8192,
        },
    )

    assert response.status_code == 200
    validated = AnalyzeResponseV1.model_validate(response.json())

    assert validated.product_type == "xray"
    assert validated.result.parser is not None
    assert validated.result.parser.name == "xray-collector-parser"
    assert validated.result.host_info.hostname == "shulei"
    assert validated.result.host_info.os_name == "Ubuntu 22.04.5 LTS"
    assert validated.result.host_info.kernel_version == "5.15.0-174-generic"
    assert validated.result.host_info.timezone == "UTC+08:00"
    assert validated.result.host_info.last_boot_at == "2026-04-15T06:26:35Z"
    assert validated.result.summary.service_count == 8
    assert validated.result.summary.service_running_count == 8
    assert validated.result.summary.container_count == 2
    assert [service.name for service in validated.result.services] == [
        "gccd",
        "haproxy-mgmt",
        "minion",
        "openvpn-client",
        "openvpn-server-engine",
        "openvpn-server-mgmt",
        "reverse",
        "wengine",
    ]
    assert all(service.status == "running" for service in validated.result.services)
    assert any(container.name == "xray-nginx" for container in validated.result.containers)
    assert any(container.name == "xray-redis" for container in validated.result.containers)
    assert validated.result.metadata["collector_type"] == "minion-report/v1"
    assert validated.result.metadata["xray_product_version"] == "10-25.11.001_r15"
    assert validated.result.metadata["xray_engine_version"] == "6.18.8_r12"
    assert validated.result.metadata["xray_machine_id"] == "3bc0c6e9e964477f90dd8175e5e5f181"
    assert validated.result.metadata["xray_mgmt_health_result"] == "正常"
    assert validated.result.metadata["xray_engine_health_result"] == "告警"
    assert validated.result.metadata["xray_mgmt_memory"] == "总量 15.6GB，已用 4.4GB (28.32%)，可用 10.7GB"
    assert validated.result.metadata["xray_mgmt_disk"] == "/，79.3GB (86.73%) / 96.4GB，/dev/dm-0 (ext4)"
    assert validated.result.metadata["xray_minion_log_result"] == "正常"
    assert validated.result.metadata["xray_mgmt_node_ip"] == "169.254.1.1"
    assert validated.result.metadata["xray_engine_node_ip"] == "169.253.0.2"
    assert validated.result.metadata["xray_adapted_minion_report_services"] is True
    assert any("minion-report/v1 input detected" in warning for warning in validated.warnings)


def test_post_analyze_recognizes_xray_custom_collect_input(tmp_path: Path) -> None:
    report_root = tmp_path / "xray_log_collect_shulei_20260416_152002"
    report_root.mkdir()
    _write_xray_custom_collect_bundle(report_root)

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_xray_custom_collect_001",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
            "archive_name": "xray_log_collect_shulei_20260416_152002.tar.gz",
            "archive_size_bytes": 16384,
        },
    )

    assert response.status_code == 200
    validated = AnalyzeResponseV1.model_validate(response.json())

    assert validated.product_type == "xray"
    assert validated.result.parser is not None
    assert validated.result.parser.name == "xray-collector-parser"
    assert validated.result.host_info.hostname == "shulei"
    assert validated.result.host_info.ip == "10.20.20.208"
    assert validated.result.host_info.os_name == "Ubuntu 22.04.5 LTS"
    assert validated.result.host_info.kernel_version == "5.15.0-174-generic"
    assert validated.result.host_info.timezone == "UTC+08:00"
    assert validated.result.host_info.last_boot_at == "2026-04-15T06:26:35Z"
    assert validated.result.summary.container_count == 2
    assert any(container.name == "xray-nginx" for container in validated.result.containers)
    assert any(container.name == "xray-redis" for container in validated.result.containers)
    assert any(issue.related_object_name == "xray-redis" for issue in validated.result.issues)
    assert validated.result.metadata["collector_type"] == "xray-custom-collect/v1"
    assert validated.result.metadata["product_type"] == "xray"
    assert validated.result.metadata["parser_route"] == "xray-collector-parser"
    assert validated.result.metadata["xray_machine_id"] == "RXJL-KWVN-7YRT-UJ5C"
    assert validated.result.metadata["xray_vuln_db_version"] == "hyuna-6_2025-11-28_r1.dump"
    assert validated.result.metadata["xray_product_version"] == "10-25.11.001_r15"
    assert validated.result.metadata["xray_engine_version"] == "10-25.11.001_r15"
    assert any("xray-custom-collect/v1 input detected" in warning for warning in validated.warnings)


def test_post_analyze_recognizes_xray_project_collector_v4_metadata(tmp_path: Path) -> None:
    xray_root = tmp_path / "xray-collector.20260421184735"
    _write_xray_project_collector_v4_bundle(xray_root)

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_xray_project_v4",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
            "archive_name": "xray-collector.20260421184735.tar.gz",
            "archive_size_bytes": 32768,
        },
    )

    assert response.status_code == 200
    validated = AnalyzeResponseV1.model_validate(response.json())

    assert validated.product_type == "xray"
    assert validated.result.parser is not None
    assert validated.result.parser.name == "xray-collector-parser"
    assert validated.result.host_info.hostname == "shulei"
    assert validated.result.host_info.ip == "10.20.20.208"
    assert validated.result.host_info.os_name == "Ubuntu 22.04.5 LTS"
    assert validated.result.host_info.kernel_version == "5.15.0-174-generic"
    assert validated.result.host_info.timezone == "Asia/Shanghai"
    assert validated.result.host_info.last_boot_at == "2026-04-15T14:26:34Z"
    assert validated.result.metadata["collector_type"] == "xray-collector/v1"
    assert validated.result.metadata["xray_collected_at"] == "2026-04-21T10:52:36Z"
    assert validated.result.metadata["xray_product_version"] == "10-25.11.001_r15"
    assert validated.result.metadata["xray_engine_version"] == "6.18.8_r12"
    assert validated.result.metadata["xray_system_version"] == "10-25.11.001_r15"
    assert validated.result.metadata["xray_vuln_db_version"] == "hyuna-6_2025-11-28_r1.dump"
    assert validated.result.metadata["xray_machine_id"] == "RXJL-KWVN-7YRT-UJ5C"
    assert validated.result.metadata["xray_mgmt_cpu"] == (
        "8 cores / Intel(R) Xeon(R) CPU E5-2630 v4 @ 2.20GHz / 当前使用率 22.3%"
    )
    assert validated.result.metadata["xray_mgmt_memory"] == "总量 15987M，已用 4686M (29.3%)"
    assert validated.result.metadata["xray_mgmt_disk"] == "/，87G / 97G，使用率 95%"
    assert validated.result.metadata["xray_mgmt_health_result"] == "正常"
    assert validated.result.metadata["xray_engine_health_result"] == "告警"
    assert "REDIS PORT STATUS" in str(validated.result.metadata["xray_engine_health_note"])
    nginx = next(container for container in validated.result.containers if container.name == "xray-nginx")
    redis = next(container for container in validated.result.containers if container.name == "xray-redis")
    assert nginx.cpu_percent == 0.0
    assert nginx.memory_percent == 21.39
    assert redis.cpu_percent == 1.25
    assert redis.memory_percent == 4.5


def test_post_analyze_rejects_unsupported_source_type(tmp_path: Path) -> None:
    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_bad_source",
            "source": {
                "type": "archive",
                "path": tmp_path.as_posix(),
            },
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "error": {
            "code": "unsupported_source_type",
            "message": "Only directory source is supported in analyze-request/v1.",
            "details": {
                "source_type": "archive",
            },
        },
    }


def test_post_analyze_returns_source_not_found_for_missing_directory() -> None:
    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_missing_dir",
            "source": {
                "type": "directory",
                "path": "/tmp/definitely-missing-analyzer-dir",
            },
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "error": {
            "code": "source_not_found",
            "message": "Requested source directory does not exist.",
            "details": {
                "path": "/tmp/definitely-missing-analyzer-dir",
            },
        },
    }


def test_post_analyze_returns_analyzer_internal_error_when_parser_crashes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_supported_bundle(tmp_path)

    def explode(self, **kwargs):  # noqa: ANN001, ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(linux_default_parser.LinuxDefaultParser, "parse", explode)

    response = client.post(
        "/analyze",
        json={
            "request_version": "analyze-request/v1",
            "task_id": "tsk_analyzer_internal_error",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "error": {
            "code": "analyzer_internal_error",
            "message": "Analyzer failed to process the requested directory.",
            "details": {
                "task_id": "tsk_analyzer_internal_error",
            },
        },
    }


def test_post_waf_evidence_extracts_review_oriented_fields(tmp_path: Path) -> None:
    _write_waf_evidence_bundle(tmp_path)

    response = client.post(
        "/waf-evidence",
        json={
            "request_version": "waf-evidence-request/v1",
            "task_id": "waf_audit_001",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
            "archive_name": "waf-logs.zip",
            "archive_size_bytes": 2048,
        },
    )

    assert response.status_code == 200
    payload = WafEvidenceResponseV1.model_validate(response.json())

    assert payload.result.product_type == "waf"
    assert payload.result.product_version == "7.0.1"
    assert payload.result.host_hostname == "waf-host"
    assert payload.result.host_ip_list == ["10.20.30.40"]
    assert any(component.component_name == "redis" for component in payload.result.runtime_components)
    assert any(component.status == "restarting" for component in payload.result.runtime_components)
    assert any(signal.metric == "memory" and signal.level == "high" for signal in payload.result.resource_signals)
    assert any(finding.finding_type == "restart" for finding in payload.result.log_findings)
    assert payload.result.derived_summary.overall_runtime_state == "abnormal"


def test_post_waf_evidence_supports_realish_safeline_bundle_layout(tmp_path: Path) -> None:
    _write_realish_safeline_bundle(tmp_path)

    response = client.post(
        "/waf-evidence",
        json={
            "request_version": "waf-evidence-request/v1",
            "task_id": "waf_audit_realish_001",
            "source": {
                "type": "directory",
                "path": tmp_path.as_posix(),
            },
            "archive_name": "minion-command-collect.tar.gz",
            "archive_size_bytes": 4096,
        },
    )

    assert response.status_code == 200
    payload = WafEvidenceResponseV1.model_validate(response.json())

    assert payload.result.product_version == "23.01.014_r6"
    assert payload.result.host_hostname == "chaitin-safeline"
    assert payload.result.host_os_name == "Ubuntu 22.04.5 LTS"
    assert payload.result.host_kernel_version == "5.15.0-33-generic"
    assert payload.result.host_ip_list == ["192.168.1.1", "172.29.12.108", "1.1.1.2"]
    assert any(component.component_name == "mgt-api" and component.status == "running" for component in payload.result.runtime_components)
    assert any(signal.metric == "cpu" and signal.subject == "host" and signal.level == "normal" for signal in payload.result.resource_signals)
    assert any(signal.metric == "memory" and signal.subject == "host" and signal.level == "normal" for signal in payload.result.resource_signals)
    assert any(finding.finding_type == "dependency_fail" for finding in payload.result.log_findings)
    assert any(finding.finding_type == "error_log" for finding in payload.result.log_findings)
    assert payload.result.derived_summary.overall_runtime_state == "warning"


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


def _write_xray_custom_collect_bundle(root_dir: Path) -> None:
    (root_dir / "minion_collect.txt").write_text(
        "\n".join(
            [
                "##################################################",
                "Host",
                "##################################################",
                "platform: ubuntu",
                "version: 22.04",
                "host time: 2026-04-16T15:20:04+08:00",
                "boot time: 2026-04-15T14:26:35+08:00",
                "up time: 24:53:30",
                "##################################################",
                "Cpu",
                "##################################################",
                "CPU0",
                "model: Intel(R) Xeon(R) CPU",
                "GHz : 2.60",
                "##################################################",
                "Memory",
                "##################################################",
                "total: 15.6GB",
                "used: 4.4GB",
                "available: 10.7GB",
                "##################################################",
                "Disk",
                "##################################################",
                "/dev/sda1",
                "Total: 96.4GB",
                "Used: 79.3GB",
                "Mounted on: /",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "docker_ps.txt").write_text(
        "\n".join(
            [
                "CONTAINER ID   IMAGE                COMMAND                  CREATED       STATUS                    PORTS                  NAMES",
                'abc123         registry/xray-nginx  "nginx -g daemon"       3 weeks ago   Up 3 weeks (healthy)     0.0.0.0:443->443/tcp   xray-nginx',
                'def456         registry/xray-redis  "redis-server"          3 weeks ago   Restarting (1) 1 minute ago                         xray-redis',
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "machine_id.txt").write_text(
        "Machine ID: RXJL-KWVN-7YRT-UJ5C\n",
        encoding="utf-8",
    )
    (root_dir / "vuln_db_version.txt").write_text(
        "hyuna_target_basename=hyuna-6_2025-11-28_r1.dump\n",
        encoding="utf-8",
    )
    (root_dir / "xray_tree.txt").write_text(
        "\n".join(
            [
                "x-ray-engine-installer-10-25.11.001_r15-linux-amd64",
                "x-ray-mgmt-installer-10-25.11.001_r15-linux-amd64",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "uname.txt").write_text(
        "Linux shulei 5.15.0-174-generic #184-Ubuntu SMP x86_64 GNU/Linux\n",
        encoding="utf-8",
    )
    (root_dir / "os-release.txt").write_text(
        'PRETTY_NAME="Ubuntu 22.04.5 LTS"\n',
        encoding="utf-8",
    )
    (root_dir / "network.txt").write_text(
        "\n".join(
            [
                "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536",
                "    inet 127.0.0.1/8 scope host lo",
                "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500",
                "    inet 10.20.20.208/24 brd 10.20.20.255 scope global eth0",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "date.txt").write_text("2026-04-16T15:20:04+08:00\n", encoding="utf-8")


def _write_xray_project_collector_v4_bundle(root_dir: Path) -> None:
    (root_dir / "summary").mkdir(parents=True)
    (root_dir / "resource-snapshots").mkdir(parents=True)
    (root_dir / "node-info").mkdir(parents=True)
    (root_dir / "xray-logs").mkdir(parents=True)
    (root_dir / "health-check").mkdir(parents=True)
    (root_dir / "resource-usage").mkdir(parents=True)

    (root_dir / "summary" / "xray_collection_summary.json").write_text(
        json.dumps(
            {
                "collector": "xray-collector-4.1-project-compatible",
                "collected_at": "2026-04-21T10:52:36Z",
                "host": {
                    "hostname": "shulei",
                    "ip": "10.20.20.208",
                    "os": "Ubuntu 22.04.5 LTS",
                    "kernel": "5.15.0-174-generic",
                    "timezone": "Asia/Shanghai",
                    "uptime_seconds": "534062",
                    "last_boot_at": "2026-04-15T14:26:34Z",
                    "cpu_model": "Intel(R) Xeon(R) CPU E5-2630 v4 @ 2.20GHz",
                    "cpu_cores": "8",
                },
                "versions": {
                    "product_version": "10-25.11.001_r15",
                    "engine_version": "6.18.8_r12",
                    "system_version": "10-25.11.001_r15",
                    "vuln_db": "hyuna-6_2025-11-28_r1.dump",
                    "machine_id": "RXJL-KWVN-7YRT-UJ5C",
                },
                "resources": {
                    "cpu_usage_percent": "22.3",
                    "memory_used": "4686M",
                    "memory_total": "15987M",
                    "memory_usage_percent": "29.3",
                    "disk_mount": "/",
                    "disk_used": "87G",
                    "disk_total": "97G",
                    "disk_usage": "95%",
                },
                "container_summary": {
                    "total_count": 19,
                    "running_count": 18,
                    "abnormal_count": 4,
                },
                "containers": [
                    {
                        "container": "xray-nginx",
                        "cpu_percent": "0.00",
                        "mem_percent": "21.39",
                    },
                    {
                        "container": "xray-redis",
                        "cpu_percent": "1.25",
                        "mem_percent": "4.50",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (root_dir / "resource-snapshots" / "docker-ps-a.txt").write_text(
        "\n".join(
            [
                "CONTAINER ID   IMAGE                   COMMAND       CREATED       STATUS                   PORTS      NAMES",
                'abc123         registry/xray-nginx     "nginx"       2 weeks ago   Up 2 weeks (healthy)     443/tcp    xray-nginx',
                'def456         registry/xray-redis     "redis"       2 weeks ago   Restarting (1) 1 min ago            xray-redis',
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "node-info" / "versions.txt").write_text(
        "\n".join(
            [
                "product_version=10-25.11.001_r15",
                "engine_version=6.18.8_r12",
                "system_version=10-25.11.001_r15",
                "vuln_db=hyuna-6_2025-11-28_r1.dump",
                "machine_id=RXJL-KWVN-7YRT-UJ5C",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "xray-logs" / "machineid.txt").write_text(
        "machine_id=RXJL-KWVN-7YRT-UJ5C\n",
        encoding="utf-8",
    )
    (root_dir / "xray-logs" / "vuln-db-version.txt").write_text(
        "hyuna-6_2025-11-28_r1.dump\n",
        encoding="utf-8",
    )
    (root_dir / "health-check" / "mgmt-health.txt").write_text(
        "\n".join(
            [
                "MINION GRPC : True",
                "BASELINE GRPC : True",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "health-check" / "engine-health.txt").write_text(
        "\n".join(
            [
                "WENGINE GRPC : True",
                "REDIS PORT STATUS : False",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "resource-usage" / "resource-summary.txt").write_text(
        "\n".join(
            [
                "CPU:",
                "  Cores: 8",
                "  Usage: 22.3%",
                "",
                "Memory:",
                "  Total: 15987M",
                "  Used: 4686M",
                "",
                "Disk:",
                "  Mount: /",
                "  Used: 87G",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "manifest.txt").write_text(
        "collected_at=2026-04-21T10:52:36Z\n",
        encoding="utf-8",
    )
    (root_dir / "uptime.txt").write_text(
        " 15:20:04 up 1 day, 53 min, 1 user, load average: 0.02, 0.03, 0.00\n",
        encoding="utf-8",
    )


def _write_waf_evidence_bundle(root_dir: Path) -> None:
    system_dir = root_dir / "system"
    container_dir = root_dir / "containers"
    resource_dir = root_dir / "resources"
    log_dir = root_dir / "logs"
    meta_dir = root_dir / "meta"
    for path in [system_dir, container_dir, resource_dir, log_dir, meta_dir]:
        path.mkdir(parents=True)

    (system_dir / "system_info").write_text(
        "\n".join(
            [
                "hostname=waf-host",
                "pretty_name=Ubuntu 22.04 LTS",
                "kernel=5.15.0-test",
                "ip=10.20.30.40",
                "timezone=UTC",
            ]
        ),
        encoding="utf-8",
    )
    (system_dir / "systemctl_status").write_text(
        "\n".join(
            [
                "UNIT LOAD ACTIVE SUB DESCRIPTION",
                "gateway.service loaded active running gateway",
                "worker.service loaded active running worker",
            ]
        ),
        encoding="utf-8",
    )
    (container_dir / "docker_ps").write_text(
        "\n".join(
            [
                "NAMES\tIMAGE\tSTATUS\tPORTS",
                "redis\tredis:7\tRestarting (1) 10 seconds ago\t",
                "nginx\tnginx:1.27\tUp 1 hour (healthy)\t0.0.0.0:443->443/tcp",
            ]
        ),
        encoding="utf-8",
    )
    (resource_dir / "resource_summary").write_text(
        "\n".join(
            [
                "cpu=70%",
                "memory=88%",
                "disk=60%",
            ]
        ),
        encoding="utf-8",
    )
    (meta_dir / "product_version.txt").write_text("7.0.1\n", encoding="utf-8")
    (log_dir / "app.log").write_text(
        "\n".join(
            [
                "redis restarting because dependency connection refused",
                "ERROR waf worker health check failed",
            ]
        ),
        encoding="utf-8",
    )


def _write_realish_safeline_bundle(root_dir: Path) -> None:
    (root_dir / "safeline").mkdir(parents=True)
    (root_dir / "container").mkdir(parents=True)
    (root_dir / "system").mkdir(parents=True)
    (root_dir / "network").mkdir(parents=True)
    (root_dir / "safeline" / "logs" / "mario").mkdir(parents=True)

    (root_dir / "safeline" / "minion-version.txt").write_text(
        "Version: 23.01.014_p4\n",
        encoding="utf-8",
    )
    (root_dir / "safeline" / "service_profile.yml").write_text(
        "\n".join(
            [
                "services:",
                "  postgres:",
                "    container_name: mgt-postgres",
                "    image: registry/postgres:11.16",
                "  redis:",
                "    container_name: mgt-redis",
                "    image: registry/redis:7.0.7",
                "  es:",
                "    container_name: mgt-es",
                "    image: registry/elasticsearch:7.17.7",
                "  management:",
                "    container_name: mgt-api",
                "    image: registry/mgt-api:${IMAGE_TAG}",
                "    environment:",
                "    - PRODUCT_VERSION=23.01.014_r6",
                "  mario:",
                "    container_name: mario",
                "    image: registry/mario:${IMAGE_TAG}",
                "  detector:",
                "    container_name: detector-srv",
                "    image: registry/detector:${IMAGE_TAG}",
                "  ripley:",
                "    container_name: ripley-work",
                "    image: registry/ripley:${IMAGE_TAG}",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "container" / "docker_stats.txt").write_text(
        "\n".join(
            [
                "CONTAINER ID   NAME               CPU %     MEM USAGE / LIMIT     MEM %     NET I/O          BLOCK I/O        PIDS",
                "4717b051d51f   ripley-work        200.84%   2.112GiB / 99.01GiB   2.13%     710kB / 89.8kB   28.7kB / 0B      15",
                "f79c73219f93   mgt-api            4.65%     4.074GiB / 42.43GiB    9.60%     292GB / 184GB    328kB / 287MB    1267",
                "4c56c6117893   mgt-es             1.24%     16.3GiB / 28.29GiB     57.61%    127MB / 119MB    309MB / 1.07GB   331",
                "85b7da628748   mgt-redis          0.46%     10.66MiB / 14.14GiB    0.07%     131GB / 147GB    13MB / 1.94GB    5",
                "6837fa86fd16   mgt-postgres       0.58%     8.717GiB / 28.29GiB    30.81%    42.3GB / 138GB   1.95GB / 121GB   73",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "system" / "top.txt").write_text(
        "\n".join(
            [
                "top - 16:14:48 up 53 days, 17:46,  1 user,  load average: 2.79, 2.89, 2.90",
                "%Cpu(s):  3.8 us,  0.3 sy,  0.0 ni, 95.9 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st",
                "MiB Mem : 193111.3 total,  74399.7 free,  73852.7 used,  44859.0 buff/cache",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "system" / "kernel_version.txt").write_text(
        "\n".join(
            [
                'PRETTY_NAME="Ubuntu 22.04.5 LTS"',
                "Linux chaitin-safeline 5.15.0-33-generic #34-Ubuntu SMP Wed May 18 13:34:26 UTC 2022 x86_64 x86_64 x86_64 GNU/Linux",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "network" / "ip-addr.txt").write_text(
        "\n".join(
            [
                "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536",
                "    inet 127.0.0.1/8 scope host lo",
                "2: mgmt: <BROADCAST,MULTICAST,UP> mtu 1500",
                "    inet 192.168.1.1/24 brd 192.168.1.255 scope global mgmt",
                "3: mgmt: <BROADCAST,MULTICAST,UP> mtu 1500",
                "    inet 172.29.12.108/24 brd 172.29.12.255 scope global mgmt",
                "4: ha: <BROADCAST,MULTICAST,UP> mtu 1500",
                "    inet 1.1.1.2/30 brd 1.1.1.3 scope global ha",
                "5: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500",
                "    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0",
                "6: safeline: <BROADCAST,MULTICAST,UP> mtu 1500",
                "    inet 169.254.0.1/24 brd 169.254.0.255 scope global safeline",
            ]
        ),
        encoding="utf-8",
    )
    (root_dir / "container" / "traffic-learning.log").write_text(
        'time="2025/12/12 14:29:07" level=error msg="Failed to connect to ElasticSearch: health check timeout: Head http://169.254.0.9:9200: dial tcp 169.254.0.9:9200: connect: connection refused"\n',
        encoding="utf-8",
    )
    (root_dir / "safeline" / "logs" / "mario" / "mario.log").write_text(
        'time="2024/02/23 13:09:56" level=warning msg="Failed to report plugin state to mgt server: Server return error: invalid-license, msg: License does not exist"\n',
        encoding="utf-8",
    )
