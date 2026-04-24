from __future__ import annotations

import json
import re
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from tempfile import TemporaryDirectory

from app.parsers.linux_default_parser import LinuxDefaultParser
from app.schemas.unified_json import UnifiedJsonParser, UnifiedJsonV1


XRAY_ROOT_MARKERS = ("system-logs", "resource-snapshots", "xray-logs")
MINION_REPORT_ROOT_MARKERS = ("info", "config", "logs")
CUSTOM_COLLECT_ROOT_MARKERS = ("minion_collect.txt", "docker_ps.txt", "machine_id.txt")


@dataclass(frozen=True)
class XrayCollectorInput:
    input_variant: str
    root: Path
    hostnamectl_path: Path | None
    timedatectl_path: Path | None
    uname_path: Path | None
    uptime_path: Path | None
    list_boot_path: Path | None
    os_release_path: Path | None
    minion_service_status_path: Path | None
    systemctl_failed_path: Path | None
    docker_ps_path: Path | None
    ip_addr_path: Path | None
    info_path: Path | None
    mgmt_config_path: Path | None
    engine_config_path: Path | None
    minion_log_path: Path | None
    wengine_supervisord_log_path: Path | None
    link_mgmt_supervisord_log_path: Path | None
    link_engine_supervisord_log_path: Path | None
    machine_id_path: Path | None
    vuln_db_version_path: Path | None
    xray_tree_path: Path | None
    summary_json_path: Path | None
    versions_path: Path | None
    mgmt_health_path: Path | None
    engine_health_path: Path | None
    resource_summary_path: Path | None
    manifest_path: Path | None


class XrayCollectorParser:
    parser_name = "xray-collector-parser"
    parser_version = "0.1.0"

    def detect(self, analysis_root: Path) -> XrayCollectorInput | None:
        candidates = [analysis_root.resolve()]
        candidates.extend(
            path.resolve()
            for path in sorted(analysis_root.iterdir())
            if path.is_dir()
        )

        for candidate in candidates:
            detected = self._detect_root(candidate)
            if detected is not None:
                return detected

        return None

    def parse(
        self,
        *,
        task_id: str,
        analysis_root: Path,
        archive_name: str | None = None,
        archive_size_bytes: int | None = None,
    ) -> UnifiedJsonV1:
        detected = self.detect(analysis_root)
        if detected is None:
            raise ValueError("xray collector input was not detected")

        with TemporaryDirectory(prefix="xray-canonical-") as temp_dir:
            canonical_root = Path(temp_dir)
            self._materialize_canonical_bundle(detected, canonical_root)
            unified_json = LinuxDefaultParser().parse(
                task_id=task_id,
                analysis_root=canonical_root,
                archive_name=archive_name,
                archive_size_bytes=archive_size_bytes,
            )

        self._enrich_container_metrics(unified_json, detected)
        unified_json.parser = UnifiedJsonParser(
            name=self.parser_name,
            version=self.parser_version,
        )
        unified_json.warnings = [
            f"{detected.input_variant} input detected and normalized into canonical parser inputs.",
            *unified_json.warnings,
        ]
        unified_json.metadata = {
            **unified_json.metadata,
            "collector_type": detected.input_variant,
            "xray_root_path": detected.root.as_posix(),
            "xray_adapted_system_info": self._has_host_data(detected),
            "xray_adapted_service_inventory": detected.minion_service_status_path is not None,
            "xray_adapted_minion_report_services": any(
                path is not None
                for path in [
                    detected.minion_log_path,
                    detected.wengine_supervisord_log_path,
                    detected.link_mgmt_supervisord_log_path,
                    detected.link_engine_supervisord_log_path,
                ]
            ),
            "xray_adapted_systemctl_failed": detected.systemctl_failed_path is not None,
            "xray_adapted_docker_ps": (
                detected.docker_ps_path is not None or detected.info_path is not None
            ),
            **self._build_xray_metadata(detected),
        }
        return unified_json

    def _detect_root(self, candidate: Path) -> XrayCollectorInput | None:
        if not candidate.is_dir():
            return None

        has_xray_markers = any((candidate / marker).exists() for marker in XRAY_ROOT_MARKERS)
        has_minion_report_markers = all(
            (candidate / marker).exists() for marker in MINION_REPORT_ROOT_MARKERS
        )
        has_custom_collect_markers = all(
            (candidate / marker).is_file() for marker in CUSTOM_COLLECT_ROOT_MARKERS
        )
        if not has_xray_markers and not has_minion_report_markers and not has_custom_collect_markers:
            return None

        system_logs_dir = candidate / "system-logs"
        resource_dir = candidate / "resource-snapshots"
        xray_logs_dir = candidate / "xray-logs" / "container-logs"
        network_dir = candidate / "network"

        detected = XrayCollectorInput(
            input_variant=(
                "xray-custom-collect/v1"
                if has_custom_collect_markers and not has_xray_markers and not has_minion_report_markers
                else "minion-report/v1"
                if has_minion_report_markers and not has_xray_markers
                else "xray-collector/v1"
            ),
            root=candidate,
            hostnamectl_path=_first_existing(
                system_logs_dir / "hostnamectl.txt",
            ),
            timedatectl_path=_first_existing(
                system_logs_dir / "timedatectl.txt",
                candidate / "date.txt",
            ),
            uname_path=_first_existing(
                system_logs_dir / "uname.txt",
                candidate / "uname.txt",
            ),
            uptime_path=_first_existing(
                system_logs_dir / "uptime.txt",
                candidate / "uptime.txt",
            ),
            list_boot_path=_first_existing(
                system_logs_dir / "list-boot.txt",
            ),
            os_release_path=_first_existing(
                candidate / "os-release.txt",
            ),
            minion_service_status_path=_first_existing(
                candidate / "minion-logs" / "minion-service-status.txt",
            ),
            systemctl_failed_path=_first_existing(
                system_logs_dir / "systemctl-failed.txt",
            ),
            docker_ps_path=_first_existing(
                resource_dir / "docker-ps-a.txt",
                xray_logs_dir / "docker_ps.log",
                candidate / "docker_ps.txt",
            ),
            ip_addr_path=_first_existing(
                network_dir / "ip-addr.txt",
                system_logs_dir / "ip.addr.txt",
                candidate / "network.txt",
            ),
            info_path=_first_existing(candidate / "info", candidate / "minion_collect.txt"),
            mgmt_config_path=_first_existing(candidate / "config" / "mgmt_config.yml"),
            engine_config_path=_first_existing(candidate / "config" / "engine_config.yml"),
            minion_log_path=_first_existing(candidate / "logs" / "minion.log"),
            wengine_supervisord_log_path=_first_existing(
                candidate / "logs" / "wengine" / "supervisord.log",
            ),
            link_mgmt_supervisord_log_path=_first_existing(
                candidate / "logs" / "link-mgmt" / "supervisord.log",
            ),
            link_engine_supervisord_log_path=_first_existing(
                candidate / "logs" / "link-engine" / "supervisord.log",
            ),
            machine_id_path=_first_existing(
                candidate / "machine_id.txt",
                candidate / "node-info" / "machine-id.txt",
                candidate / "xray-logs" / "machineid.txt",
            ),
            vuln_db_version_path=_first_existing(
                candidate / "vuln_db_version.txt",
                candidate / "xray-logs" / "vuln-db-version.txt",
            ),
            xray_tree_path=_first_existing(candidate / "xray_tree.txt"),
            summary_json_path=_first_existing(
                candidate / "summary" / "xray_collection_summary.json",
            ),
            versions_path=_first_existing(candidate / "node-info" / "versions.txt"),
            mgmt_health_path=_first_existing(
                candidate / "health-check" / "mgmt-health.txt",
                candidate / "health-checks" / "minion-mgmt-health.txt",
            ),
            engine_health_path=_first_existing(
                candidate / "health-check" / "engine-health.txt",
                candidate / "health-checks" / "minion-engine-health.txt",
            ),
            resource_summary_path=_first_existing(
                candidate / "resource-usage" / "resource-summary.txt",
            ),
            manifest_path=_first_existing(candidate / "manifest.txt"),
        )

        if not any(
            [
                self._has_host_data(detected),
                detected.minion_service_status_path is not None,
                detected.minion_log_path is not None,
                detected.systemctl_failed_path is not None,
                detected.docker_ps_path is not None,
                detected.info_path is not None,
                detected.machine_id_path is not None,
                detected.summary_json_path is not None,
                detected.versions_path is not None,
            ]
        ):
            return None

        return detected

    def _materialize_canonical_bundle(
        self,
        detected: XrayCollectorInput,
        canonical_root: Path,
    ) -> None:
        system_dir = canonical_root / "system"
        containers_dir = canonical_root / "containers"
        system_dir.mkdir(parents=True, exist_ok=True)
        containers_dir.mkdir(parents=True, exist_ok=True)

        system_info_lines = self._build_system_info_lines(detected)
        if system_info_lines:
            (system_dir / "system_info").write_text(
                "\n".join(system_info_lines) + "\n",
                encoding="utf-8",
            )

        systemctl_status_lines = self._build_systemctl_status_lines(detected)
        if systemctl_status_lines:
            (system_dir / "systemctl_status").write_text(
                "\n".join(systemctl_status_lines) + "\n",
                encoding="utf-8",
            )

        docker_ps_content = self._build_docker_ps_content(detected)
        if docker_ps_content:
            (containers_dir / "docker_ps").write_text(
                docker_ps_content + "\n",
                encoding="utf-8",
            )

    def _build_system_info_lines(self, detected: XrayCollectorInput) -> list[str]:
        values: dict[str, str] = {}

        summary = _load_json_dict(detected.summary_json_path)
        if summary:
            host = _dict_value(summary, "host")
            if isinstance(host, dict):
                _set_if_truthy(values, "hostname", host.get("hostname"))
                _set_if_truthy(values, "ip", host.get("ip"))
                _set_if_truthy(values, "pretty_name", host.get("os"))
                _set_if_truthy(values, "kernel", host.get("kernel"))
                _set_if_truthy(values, "timezone", host.get("timezone"))
                _set_if_truthy(values, "uptime_seconds", host.get("uptime_seconds"))
                _set_if_truthy(values, "last_boot_at", host.get("last_boot_at"))

        if detected.info_path is not None:
            info_sections = _parse_info_sections(
                detected.info_path.read_text(encoding="utf-8", errors="ignore")
            )
            host_values = _parse_info_key_values(info_sections.get("host", ""))
            docker_info_values = _parse_info_key_values(info_sections.get("docker info", ""))

            hostname = docker_info_values.get("name")
            pretty_name = docker_info_values.get("operating system") or _compose_platform_version(
                host_values.get("platform"),
                host_values.get("version"),
            )
            kernel = docker_info_values.get("kernel version")
            uptime_seconds = _parse_duration_to_seconds(host_values.get("up time"))
            host_time = host_values.get("host time")
            last_boot_at = host_values.get("boot time")

            if hostname:
                values.setdefault("hostname", hostname)
            if pretty_name:
                values.setdefault("pretty_name", pretty_name)
            if kernel:
                values.setdefault("kernel", kernel)
            if uptime_seconds is not None:
                values.setdefault("uptime_seconds", str(uptime_seconds))
            if last_boot_at:
                values.setdefault("last_boot_at", last_boot_at)
            if host_time:
                timezone = _extract_timezone_label(host_time)
                if timezone:
                    values.setdefault("timezone", timezone)

        if detected.hostnamectl_path is not None:
            hostnamectl_text = detected.hostnamectl_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            hostname = _extract_field(hostnamectl_text, r"Static hostname:\s*(.+)")
            pretty_name = _extract_field(
                hostnamectl_text,
                r"Operating System:\s*(.+)",
            )
            kernel = _extract_field(hostnamectl_text, r"Kernel:\s*Linux\s+(.+)")
            if hostname:
                values["hostname"] = hostname
            if pretty_name:
                values["pretty_name"] = pretty_name
            if kernel:
                values["kernel"] = kernel

        if detected.os_release_path is not None:
            os_release_values = _parse_shell_key_values(
                detected.os_release_path.read_text(encoding="utf-8", errors="ignore")
            )
            pretty_name = os_release_values.get("PRETTY_NAME")
            if pretty_name:
                values["pretty_name"] = pretty_name

        if detected.uname_path is not None:
            uname_line = _first_non_comment_line(
                detected.uname_path.read_text(encoding="utf-8", errors="ignore"),
            )
            if uname_line:
                parts = uname_line.split()
                if len(parts) >= 3:
                    values.setdefault("hostname", parts[1])
                    values.setdefault("kernel", parts[2])

        if detected.timedatectl_path is not None:
            timedatectl_text = detected.timedatectl_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            timezone = _extract_field(timedatectl_text, r"Time zone:\s*([A-Za-z0-9_./+-]+)")
            if timezone:
                values["timezone"] = timezone

        if detected.uptime_path is not None:
            uptime_line = _first_non_comment_line(
                detected.uptime_path.read_text(encoding="utf-8", errors="ignore"),
            )
            uptime_seconds = _parse_uptime_shell_line(uptime_line) if uptime_line else None
            if uptime_seconds is not None:
                values["uptime_seconds"] = str(uptime_seconds)

        if detected.list_boot_path is not None:
            list_boot_text = detected.list_boot_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            last_boot_at = _extract_last_boot_at(list_boot_text)
            if last_boot_at:
                values["last_boot_at"] = last_boot_at

        if detected.ip_addr_path is not None:
            ip_text = detected.ip_addr_path.read_text(encoding="utf-8", errors="ignore")
            ip_value = _extract_first_ipv4(ip_text)
            if ip_value:
                values["ip"] = ip_value

        ordered_keys = [
            "hostname",
            "ip",
            "pretty_name",
            "kernel",
            "timezone",
            "uptime_seconds",
            "last_boot_at",
        ]
        return [f"{key}={values[key]}" for key in ordered_keys if key in values]

    def _build_systemctl_status_lines(
        self,
        detected: XrayCollectorInput,
    ) -> list[str]:
        service_rows: dict[str, str] = {}

        for inventory_row in self._build_inventory_rows(detected):
            service_rows[inventory_row.split()[0]] = inventory_row

        if detected.systemctl_failed_path is not None:
            for raw_line in detected.systemctl_failed_path.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines():
                line = raw_line.strip().lstrip("●").strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(
                    r"^([A-Za-z0-9_.:@-]+\.service)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(.*\S))?$",
                    line,
                )
                if not match:
                    continue
                description = match.group(5) or ""
                service_rows[match.group(1)] = " ".join(
                    [
                        match.group(1),
                        match.group(2),
                        match.group(3),
                        match.group(4),
                        description,
                    ]
                ).strip()

        if not service_rows:
            return []

        lines = ["UNIT LOAD ACTIVE SUB DESCRIPTION"]
        lines.extend(service_rows[unit_name] for unit_name in sorted(service_rows))
        return lines

    def _build_inventory_rows(
        self,
        detected: XrayCollectorInput,
    ) -> list[str]:
        rows: dict[str, str] = {}

        inventory_row = self._build_minion_inventory_row(detected)
        if inventory_row is not None:
            rows[inventory_row.split()[0]] = inventory_row

        for service_name, status in self._build_minion_report_inventory(detected).items():
            unit_name = f"{service_name}.service"
            active, sub = _runtime_status_to_systemctl_columns(status)
            description = service_name.replace("-", " ")
            rows[unit_name] = " ".join(
                [
                    unit_name,
                    "loaded",
                    active,
                    sub,
                    description,
                ]
            ).strip()

        return [rows[unit_name] for unit_name in sorted(rows)]

    def _build_minion_inventory_row(
        self,
        detected: XrayCollectorInput,
    ) -> str | None:
        if detected.minion_service_status_path is None:
            return None

        unit_line = None
        loaded_line = None
        active_line = None

        for raw_line in detected.minion_service_status_path.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if unit_line is None and ".service -" in line:
                unit_line = line.lstrip("●").strip()
                continue
            if loaded_line is None and line.startswith("Loaded:"):
                loaded_line = line
                continue
            if active_line is None and line.startswith("Active:"):
                active_line = line
                continue

        if unit_line is None or loaded_line is None or active_line is None:
            return None

        unit_match = re.match(r"^([A-Za-z0-9_.:@-]+\.service)\s+-\s+(.+)$", unit_line)
        loaded_match = re.match(r"^Loaded:\s+(\S+)\s+.*$", loaded_line)
        active_match = re.match(r"^Active:\s+(\S+)\s+\(([^)]+)\).*$", active_line)
        if not unit_match or not loaded_match or not active_match:
            return None

        description = unit_match.group(2)
        enabled = _extract_enabled_value(loaded_line)
        if enabled is not None:
            description = f"{description} [enabled={'true' if enabled else 'false'}]"

        return " ".join(
            [
                unit_match.group(1),
                loaded_match.group(1),
                active_match.group(1),
                active_match.group(2),
                description,
            ]
        ).strip()

    def _build_docker_ps_content(self, detected: XrayCollectorInput) -> str | None:
        if detected.docker_ps_path is not None:
            content = detected.docker_ps_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            return _normalize_docker_ps_table(content)

        if detected.info_path is not None:
            info_sections = _parse_info_sections(
                detected.info_path.read_text(encoding="utf-8", errors="ignore")
            )
            docker_ps_section = info_sections.get("docker ps", "")
            if docker_ps_section:
                return _normalize_docker_ps_table(docker_ps_section)

        return None

    def _build_minion_report_inventory(
        self,
        detected: XrayCollectorInput,
    ) -> dict[str, str]:
        services: dict[str, str] = {}

        if detected.minion_log_path is not None:
            minion_status = _parse_minion_systemd_status(
                detected.minion_log_path.read_text(encoding="utf-8", errors="ignore"),
            )
            if minion_status is not None:
                services["minion"] = minion_status

        for log_path in [
            detected.wengine_supervisord_log_path,
            detected.link_mgmt_supervisord_log_path,
            detected.link_engine_supervisord_log_path,
        ]:
            if log_path is None:
                continue
            services.update(
                _parse_supervisord_runtime_statuses(
                    log_path.read_text(encoding="utf-8", errors="ignore"),
                )
            )

        return services

    def _build_xray_metadata(
        self,
        detected: XrayCollectorInput,
    ) -> dict[str, str | int | float | bool | None]:
        metadata: dict[str, str | int | float | bool | None] = {}

        if detected.info_path is not None:
            info_sections = _parse_info_sections(
                detected.info_path.read_text(encoding="utf-8", errors="ignore")
            )
            docker_images_section = info_sections.get("docker images", "")
            docker_info_section = info_sections.get("docker info", "")
            minion_health_section = info_sections.get("minion health", "")
            cpu_section = info_sections.get("cpu", "")
            memory_section = info_sections.get("memory", "")
            disk_section = info_sections.get("disk", "")

            product_version = _extract_image_tag(
                docker_images_section,
                repository_pattern=r"/x-ray/balisong$",
            )
            engine_version = _extract_image_tag(
                docker_images_section,
                repository_pattern=r"/x-ray/gungnir$",
            )
            if product_version:
                metadata["xray_product_version"] = product_version
            if engine_version:
                metadata["xray_engine_version"] = engine_version

            docker_info_values = _parse_info_key_values(docker_info_section)
            if docker_info_values.get("name"):
                metadata["xray_detected_hostname"] = docker_info_values["name"]

            mgmt_health_checks, engine_health_checks = _parse_minion_health_section(
                minion_health_section
            )
            mgmt_result, mgmt_note = _summarize_health_checks(mgmt_health_checks)
            engine_result, engine_note = _summarize_health_checks(engine_health_checks)
            if mgmt_result:
                metadata["xray_mgmt_health_result"] = mgmt_result
                metadata["xray_mgmt_node_health"] = mgmt_result
            if mgmt_note:
                metadata["xray_mgmt_health_note"] = mgmt_note
            if engine_result:
                metadata["xray_engine_health_result"] = engine_result
                metadata["xray_engine_node_health"] = engine_result
            if engine_note:
                metadata["xray_engine_health_note"] = engine_note

            minion_status = _find_health_check(
                mgmt_health_checks,
                "MINION GRPC",
            )
            if minion_status is not None:
                metadata["xray_minion_log_result"] = "正常" if minion_status else "告警"
                metadata["xray_minion_log_note"] = (
                    "MINION GRPC 检查通过。"
                    if minion_status
                    else "MINION GRPC 检查失败。"
                )

            cpu_summary = _summarize_cpu_section(cpu_section)
            memory_summary = _summarize_memory_section(memory_section)
            disk_summary = _summarize_disk_section(disk_section)
            if cpu_summary:
                metadata["xray_mgmt_cpu"] = cpu_summary
            if memory_summary:
                metadata["xray_mgmt_memory"] = memory_summary
            if disk_summary:
                metadata["xray_mgmt_disk"] = disk_summary

        metadata.update(self._build_custom_collect_metadata(detected))
        metadata.update(self._build_project_collector_metadata(detected))
        metadata.update(self._build_config_metadata(detected))
        return metadata

    def _build_custom_collect_metadata(
        self,
        detected: XrayCollectorInput,
    ) -> dict[str, str | int | float | bool | None]:
        metadata: dict[str, str | int | float | bool | None] = {}

        if detected.machine_id_path is not None:
            machine_id = _extract_field(
                detected.machine_id_path.read_text(encoding="utf-8", errors="ignore"),
                r"(?:Machine ID|machine_id)\s*[:=]\s*(.+)",
            )
            if machine_id:
                metadata["xray_machine_id"] = machine_id

        if detected.vuln_db_version_path is not None:
            vuln_db_text = detected.vuln_db_version_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            vuln_db_version = _extract_vuln_db_version(vuln_db_text)
            if vuln_db_version:
                metadata["xray_vuln_db_version"] = vuln_db_version

        if detected.xray_tree_path is not None:
            xray_tree_text = detected.xray_tree_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            product_version = _extract_installer_version(
                xray_tree_text,
                installer_prefix="x-ray-mgmt-installer",
            )
            engine_version = _extract_installer_version(
                xray_tree_text,
                installer_prefix="x-ray-engine-installer",
            )
            if product_version:
                metadata["xray_product_version"] = product_version
            if engine_version:
                metadata["xray_engine_version"] = engine_version

        return metadata

    def _build_project_collector_metadata(
        self,
        detected: XrayCollectorInput,
    ) -> dict[str, str | int | float | bool | None]:
        metadata: dict[str, str | int | float | bool | None] = {}

        summary = _load_json_dict(detected.summary_json_path)
        if summary:
            _set_metadata_if_truthy(metadata, "xray_collected_at", summary.get("collected_at"))
            versions = summary.get("versions")
            if isinstance(versions, dict):
                _set_metadata_if_truthy(metadata, "xray_product_version", versions.get("product_version"))
                _set_metadata_if_truthy(metadata, "xray_engine_version", versions.get("engine_version"))
                _set_metadata_if_truthy(metadata, "xray_system_version", versions.get("system_version"))
                _set_metadata_if_truthy(metadata, "xray_vuln_db_version", versions.get("vuln_db"))
                _set_metadata_if_truthy(metadata, "xray_machine_id", versions.get("machine_id"))

            resources = summary.get("resources")
            if isinstance(resources, dict):
                cpu_summary = _format_project_cpu_summary(summary)
                memory_summary = _format_project_memory_summary(resources)
                disk_summary = _format_project_disk_summary(resources)
                if cpu_summary:
                    metadata["xray_mgmt_cpu"] = cpu_summary
                if memory_summary:
                    metadata["xray_mgmt_memory"] = memory_summary
                if disk_summary:
                    metadata["xray_mgmt_disk"] = disk_summary

            container_summary = summary.get("container_summary")
            if isinstance(container_summary, dict):
                _set_metadata_if_truthy(
                    metadata,
                    "xray_container_abnormal_count",
                    container_summary.get("abnormal_count"),
                )

        if detected.versions_path is not None:
            versions = _parse_shell_key_values(
                detected.versions_path.read_text(encoding="utf-8", errors="ignore")
            )
            version_mapping = {
                "product_version": "xray_product_version",
                "engine_version": "xray_engine_version",
                "system_version": "xray_system_version",
                "vuln_db": "xray_vuln_db_version",
                "machine_id": "xray_machine_id",
            }
            for source_key, target_key in version_mapping.items():
                _set_metadata_if_truthy(metadata, target_key, versions.get(source_key))

        if detected.mgmt_health_path is not None:
            checks = _parse_health_checks_text(
                detected.mgmt_health_path.read_text(encoding="utf-8", errors="ignore")
            )
            result, note = _summarize_health_checks(checks)
            if result:
                metadata["xray_mgmt_health_result"] = result
                metadata["xray_mgmt_node_health"] = result
            if note:
                metadata["xray_mgmt_health_note"] = note

        if detected.engine_health_path is not None:
            checks = _parse_health_checks_text(
                detected.engine_health_path.read_text(encoding="utf-8", errors="ignore")
            )
            result, note = _summarize_health_checks(checks)
            if result:
                metadata["xray_engine_health_result"] = result
                metadata["xray_engine_node_health"] = result
            if note:
                metadata["xray_engine_health_note"] = note

        if detected.resource_summary_path is not None:
            resource_text = detected.resource_summary_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            metadata.setdefault("xray_mgmt_cpu", _extract_project_resource_block(resource_text, "CPU"))
            metadata.setdefault("xray_mgmt_memory", _extract_project_resource_block(resource_text, "Memory"))
            metadata.setdefault("xray_mgmt_disk", _extract_project_resource_block(resource_text, "Disk"))

        if detected.manifest_path is not None:
            manifest_values = _parse_shell_key_values(
                detected.manifest_path.read_text(encoding="utf-8", errors="ignore")
            )
            _set_metadata_if_truthy(metadata, "xray_collected_at", manifest_values.get("collected_at"))

        return metadata

    def _enrich_container_metrics(
        self,
        unified_json: UnifiedJsonV1,
        detected: XrayCollectorInput,
    ) -> None:
        metrics_by_name = _build_project_container_metrics(detected.summary_json_path)
        if not metrics_by_name:
            return

        for container in unified_json.containers:
            metrics = metrics_by_name.get(container.name)
            if metrics is None:
                continue
            if metrics.get("cpu_percent") is not None:
                container.cpu_percent = metrics["cpu_percent"]
            if metrics.get("memory_percent") is not None:
                container.memory_percent = metrics["memory_percent"]

    def _build_config_metadata(
        self,
        detected: XrayCollectorInput,
    ) -> dict[str, str | int | float | bool | None]:
        metadata: dict[str, str | int | float | bool | None] = {}
        mgmt_config = _parse_simple_yaml(detected.mgmt_config_path)
        engine_config = _parse_simple_yaml(detected.engine_config_path)

        mgmt_id = mgmt_config.get("mgmt_id")
        if mgmt_id:
            metadata["xray_machine_id"] = mgmt_id

        mgmt_ip = _preferred_ip(
            mgmt_config.get("mgmt_ip"),
            engine_config.get("mgmt_openvpn_ip"),
            engine_config.get("mgmt_ip"),
        )
        engine_ip = _preferred_ip(
            engine_config.get("engine_openvpn_ip"),
            engine_config.get("engine_ip"),
        )
        if mgmt_ip:
            metadata["xray_mgmt_node_ip"] = mgmt_ip
        if engine_ip:
            metadata["xray_engine_node_ip"] = engine_ip

        return metadata

    def _has_host_data(self, detected: XrayCollectorInput) -> bool:
        return any(
            [
                detected.hostnamectl_path is not None,
                detected.timedatectl_path is not None,
                detected.uname_path is not None,
                detected.uptime_path is not None,
                detected.ip_addr_path is not None,
                detected.info_path is not None,
                detected.os_release_path is not None,
                detected.summary_json_path is not None,
            ]
        )


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _load_json_dict(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_value(data: dict[str, object], key: str) -> object | None:
    value = data.get(key)
    return value if value is not None else None


def _clean_project_value(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"unknown", "none", "null"} or text == "-":
        return None
    return text


def _set_if_truthy(values: dict[str, str], key: str, value: object | None) -> None:
    text = _clean_project_value(value)
    if text:
        values[key] = text


def _set_metadata_if_truthy(
    metadata: dict[str, str | int | float | bool | None],
    key: str,
    value: object | None,
) -> None:
    text = _clean_project_value(value)
    if text:
        metadata[key] = text


def _build_project_container_metrics(
    summary_json_path: Path | None,
) -> dict[str, dict[str, float | None]]:
    summary = _load_json_dict(summary_json_path)
    containers = summary.get("containers")
    if not isinstance(containers, list):
        return {}

    metrics_by_name: dict[str, dict[str, float | None]] = {}
    for item in containers:
        if not isinstance(item, dict):
            continue
        name = _clean_project_value(item.get("container"))
        if not name:
            continue
        metrics_by_name[name] = {
            "cpu_percent": _safe_float_value(item.get("cpu_percent")),
            "memory_percent": _safe_float_value(item.get("mem_percent")),
        }
    return metrics_by_name


def _safe_float_value(value: object | None) -> float | None:
    text = _clean_project_value(value)
    if text is None:
        return None
    try:
        return float(text.rstrip("%"))
    except ValueError:
        return None


def _format_project_cpu_summary(summary: dict[str, object]) -> str | None:
    host = summary.get("host")
    resources = summary.get("resources")
    if not isinstance(host, dict) or not isinstance(resources, dict):
        return None
    parts = []
    cpu_cores = _clean_project_value(host.get("cpu_cores"))
    cpu_model = _clean_project_value(host.get("cpu_model"))
    cpu_usage = _clean_project_value(resources.get("cpu_usage_percent"))
    if cpu_cores:
        parts.append(f"{cpu_cores} cores")
    if cpu_model:
        parts.append(cpu_model)
    if cpu_usage:
        parts.append(f"当前使用率 {cpu_usage}%")
    return " / ".join(parts) if parts else None


def _format_project_memory_summary(resources: dict[str, object]) -> str | None:
    total = _clean_project_value(resources.get("memory_total"))
    used = _clean_project_value(resources.get("memory_used"))
    percent = _clean_project_value(resources.get("memory_usage_percent"))
    if not any([total, used, percent]):
        return None
    if total and used and percent:
        return f"总量 {total}，已用 {used} ({percent}%)"
    return "，".join(value for value in [f"总量 {total}" if total else None, f"已用 {used}" if used else None, f"使用率 {percent}%" if percent else None] if value)


def _format_project_disk_summary(resources: dict[str, object]) -> str | None:
    mount = _clean_project_value(resources.get("disk_mount"))
    total = _clean_project_value(resources.get("disk_total"))
    used = _clean_project_value(resources.get("disk_used"))
    percent = _clean_project_value(resources.get("disk_usage"))
    if not any([mount, total, used, percent]):
        return None
    if mount and total and used and percent:
        return f"{mount}，{used} / {total}，使用率 {percent}"
    return "，".join(value for value in [mount, f"{used} / {total}" if used and total else used or total, f"使用率 {percent}" if percent else None] if value)


def _parse_health_checks_text(content: str) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    cleaned = _strip_ansi(content)
    for raw_line in cleaned.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        match = re.match(r"^(.*?)\s*:\s*(True|False)\s*$", stripped)
        if not match:
            continue
        key = " ".join(match.group(1).split())
        if key:
            checks[key] = match.group(2) == "True"

    if re.search(r"\[ERROR\]|Traceback|Error response|StatusCode\.", cleaned, re.IGNORECASE):
        checks.setdefault("HEALTH COMMAND ERROR", False)
    return checks


def _extract_project_resource_block(content: str, block_name: str) -> str | None:
    lines = content.splitlines()
    capture = False
    values: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            if capture and values:
                break
            continue
        if stripped.rstrip(":").lower() == block_name.lower():
            capture = True
            continue
        if capture and re.match(r"^[A-Za-z][A-Za-z ]+:$", stripped):
            break
        if capture and ":" in stripped:
            key, value = stripped.split(":", 1)
            normalized = _clean_project_value(value)
            if normalized:
                values.append(f"{key.strip()} {normalized}")
    return "，".join(values) if values else None


def _extract_field(content: str, pattern: str) -> str | None:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.search(pattern, line)
        if match:
            return match.group(1).strip()
    return None


def _first_non_comment_line(content: str) -> str | None:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def _parse_uptime_shell_line(line: str) -> int | None:
    normalized = " ".join(line.split())

    day_time_match = re.search(r"up (\d+) days?, (\d+):(\d+)", normalized)
    if day_time_match:
        days = int(day_time_match.group(1))
        hours = int(day_time_match.group(2))
        minutes = int(day_time_match.group(3))
        return days * 86400 + hours * 3600 + minutes * 60

    day_minute_match = re.search(r"up (\d+) days?, (\d+) min", normalized)
    if day_minute_match:
        days = int(day_minute_match.group(1))
        minutes = int(day_minute_match.group(2))
        return days * 86400 + minutes * 60

    time_match = re.search(r"up (\d+):(\d+)", normalized)
    if time_match:
        hours = int(time_match.group(1))
        minutes = int(time_match.group(2))
        return hours * 3600 + minutes * 60

    minute_match = re.search(r"up (\d+) min", normalized)
    if minute_match:
        return int(minute_match.group(1)) * 60

    return None


def _parse_duration_to_seconds(value: str | None) -> int | None:
    if not value:
        return None

    normalized = value.strip()
    hms_match = re.fullmatch(r"(\d+):(\d+):(\d+)", normalized)
    if hms_match:
        hours = int(hms_match.group(1))
        minutes = int(hms_match.group(2))
        seconds = int(hms_match.group(3))
        return hours * 3600 + minutes * 60 + seconds

    hm_match = re.fullmatch(r"(\d+):(\d+)", normalized)
    if hm_match:
        hours = int(hm_match.group(1))
        minutes = int(hm_match.group(2))
        return hours * 3600 + minutes * 60

    return None


def _extract_first_ipv4(content: str) -> str | None:
    for match in re.finditer(r"\binet\s+(\d+\.\d+\.\d+\.\d+)(?:/\d+)?\b", content):
        ip_value = match.group(1)
        if not ip_value.startswith("127."):
            return ip_value
    return None


def _extract_last_boot_at(content: str) -> str | None:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(
            r"^0\s+\S+\s+\w{3}\s+(\d{4}-\d{2}-\d{2})\s+"
            r"(\d{2}:\d{2}:\d{2})\s+(UTC)(?:—|--|-).*$",
            line,
        )
        if not match:
            continue

        date_part = match.group(1)
        time_part = match.group(2)
        timezone = match.group(3)
        if timezone != "UTC":
            return None
        return f"{date_part}T{time_part}Z"

    return None


def _extract_enabled_value(loaded_line: str) -> bool | None:
    match = re.search(r";\s*(enabled|disabled)\s*;", loaded_line)
    if not match:
        return None
    return match.group(1) == "enabled"


def _parse_info_sections(content: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    lines = content.splitlines()
    index = 0

    while index < len(lines):
        if set(lines[index].strip()) == {"#"} and index + 2 < len(lines):
            title = lines[index + 1].strip()
            if title and set(lines[index + 2].strip()) == {"#"}:
                index += 3
                body: list[str] = []
                while index < len(lines):
                    line = lines[index]
                    stripped = line.strip()
                    if (
                        set(stripped) == {"#"}
                        and index + 2 < len(lines)
                        and lines[index + 1].strip()
                        and set(lines[index + 2].strip()) == {"#"}
                    ):
                        break
                    body.append(line)
                    index += 1
                sections[title.lower()] = "\n".join(body).strip()
                continue
        index += 1

    return sections


def _parse_info_key_values(content: str) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in _strip_ansi(content).splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = re.match(r"^([^:]+):\s*(.+?)\s*$", stripped)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        if value:
            values[key] = value

    return values


def _parse_shell_key_values(content: str) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        if key and value:
            values[key] = value

    return values


def _compose_platform_version(platform: str | None, version: str | None) -> str | None:
    values = [value for value in [platform, version] if value]
    if not values:
        return None
    return " ".join(values)


def _extract_timezone_label(value: str) -> str | None:
    match = re.search(r"([+-]\d{2}:\d{2}|Z)$", value.strip())
    if not match:
        return None
    suffix = match.group(1)
    if suffix == "Z":
        return "UTC"
    return f"UTC{suffix}"


def _extract_vuln_db_version(content: str) -> str | None:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(r"\b(hyuna-[A-Za-z0-9_.-]+\.dump)\b", line)
        if match:
            return match.group(1)
    return None


def _extract_installer_version(content: str, *, installer_prefix: str) -> str | None:
    pattern = rf"\b{re.escape(installer_prefix)}-([0-9][A-Za-z0-9_.-]*?_r\d+)-"
    match = re.search(pattern, content)
    if match:
        return match.group(1)
    return None


def _normalize_docker_ps_table(content: str) -> str | None:
    kept_lines: list[str] = []
    started = False

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if started:
                kept_lines.append("")
            continue
        if stripped.startswith("#"):
            continue
        if not started:
            if "IMAGE" in stripped and "STATUS" in stripped and "NAMES" in stripped:
                started = True
                kept_lines.append(stripped)
            continue
        kept_lines.append(line)

    normalized_lines = [line for line in kept_lines if line.strip()]
    if not normalized_lines:
        return None
    docker_cli_lines = _normalize_docker_cli_ps_table(normalized_lines)
    if docker_cli_lines is not None:
        return "\n".join(docker_cli_lines)
    return "\n".join(normalized_lines)


def _normalize_docker_cli_ps_table(lines: list[str]) -> list[str] | None:
    header = lines[0].strip()
    if not all(column in header for column in ["CONTAINER ID", "IMAGE", "COMMAND", "STATUS", "NAMES"]):
        return None

    normalized = ["NAMES\tIMAGE\tSTATUS\tPORTS"]
    for raw_line in lines[1:]:
        columns = [column.strip() for column in re.split(r"\s{2,}", raw_line.strip()) if column.strip()]
        if len(columns) < 6:
            continue

        image = columns[1]
        status = columns[4]
        if len(columns) >= 7:
            ports = columns[5]
            name = columns[6]
        else:
            ports = ""
            name = columns[5]

        if not name or not image or not status:
            continue
        normalized.append("\t".join([name, image, status, ports]))

    if len(normalized) == 1:
        return None
    return normalized


def _extract_image_tag(section: str, *, repository_pattern: str) -> str | None:
    for raw_line in section.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("REPOSITORY"):
            continue
        parts = re.split(r"\s{2,}", stripped)
        if len(parts) < 2:
            continue
        repository, tag = parts[0], parts[1]
        if re.search(repository_pattern, repository) and tag.lower() != "latest":
            return tag
    return None


def _parse_minion_health_section(
    content: str,
) -> tuple[dict[str, bool], dict[str, bool]]:
    mgmt_checks: dict[str, bool] = {}
    engine_checks: dict[str, bool] = {}
    current_section: str | None = None

    for raw_line in _strip_ansi(content).splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered == "mgmt":
            current_section = "mgmt"
            continue
        if lowered == "engine":
            current_section = "engine"
            continue
        if current_section is None or stripped.startswith("["):
            continue
        match = re.match(r"^(.*?)\s*:\s*(True|False)\s*$", stripped)
        if not match:
            continue
        key = " ".join(match.group(1).split())
        value = match.group(2) == "True"
        if current_section == "mgmt":
            mgmt_checks[key] = value
        else:
            engine_checks[key] = value

    return mgmt_checks, engine_checks


def _summarize_health_checks(checks: dict[str, bool]) -> tuple[str | None, str | None]:
    if not checks:
        return None, None

    failed_items = [name for name, value in checks.items() if not value]
    if failed_items:
        return "告警", f"失败项：{', '.join(failed_items)}"

    return "正常", f"检查通过 {len(checks)} 项"


def _find_health_check(checks: dict[str, bool], needle: str) -> bool | None:
    for key, value in checks.items():
        if needle.lower() in key.lower():
            return value
    return None


def _summarize_cpu_section(section: str) -> str | None:
    cpu_count = 0
    model = None
    ghz = None

    for raw_line in section.splitlines():
        stripped = raw_line.strip()
        if re.fullmatch(r"CPU\d+", stripped):
            cpu_count += 1
            continue
        if model is None:
            match = re.match(r"^model:\s*(.+)$", stripped)
            if match:
                model = match.group(1).strip()
                continue
        if ghz is None:
            match = re.match(r"^GHz\s*:\s*(.+)$", stripped)
            if match:
                ghz = match.group(1).strip()

    if cpu_count == 0 and model is None and ghz is None:
        return None

    parts = []
    if cpu_count:
        parts.append(f"{cpu_count} cores")
    if model:
        parts.append(model)
    if ghz:
        parts.append(f"{ghz}GHz")
    return " / ".join(parts) if parts else None


def _summarize_memory_section(section: str) -> str | None:
    values = _parse_info_key_values(section)
    total = values.get("total")
    used = values.get("used")
    available = values.get("available")
    if not any([total, used, available]):
        return None

    parts = []
    if total:
        parts.append(f"总量 {total}")
    if used:
        parts.append(f"已用 {used}")
    if available:
        parts.append(f"可用 {available}")
    return "，".join(parts)


def _summarize_disk_section(section: str) -> str | None:
    current_device = None
    current_values: dict[str, str] = {}

    for raw_line in section.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("/dev/"):
            if current_values.get("mounted on") == "/":
                return _format_disk_summary(current_device, current_values)
            current_device = stripped
            current_values = {}
            continue
        match = re.match(r"^([^:]+):\s*(.+)$", stripped)
        if not match:
            continue
        current_values[match.group(1).strip().lower()] = match.group(2).strip()

    if current_values.get("mounted on") == "/":
        return _format_disk_summary(current_device, current_values)
    return None


def _format_disk_summary(device: str | None, values: dict[str, str]) -> str | None:
    total = values.get("total")
    used = values.get("used")
    mounted_on = values.get("mounted on")
    if not any([total, used, mounted_on]):
        return None

    parts = []
    if mounted_on:
        parts.append(mounted_on)
    if used and total:
        parts.append(f"{used} / {total}")
    elif total:
        parts.append(f"总量 {total}")
    elif used:
        parts.append(f"已用 {used}")
    if device:
        parts.append(device)
    return "，".join(parts)


def _parse_simple_yaml(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+):\s*(.+?)\s*$", stripped)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip().strip('"')
        if value:
            values[key] = value
    return values


def _preferred_ip(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        normalized = value.strip()
        if not normalized or normalized == "0.0.0.0":
            continue
        return normalized
    return None


def _strip_ansi(content: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", content)


def _parse_minion_systemd_status(content: str) -> str | None:
    last_status = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if "Started minion service." in line:
            last_status = "running"
        elif "Stopping minion service..." in line:
            last_status = "stopped"

    return last_status


def _parse_supervisord_runtime_statuses(content: str) -> dict[str, str]:
    statuses: dict[str, str] = {}

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        success_match = re.search(
            r"success:\s+([A-Za-z0-9_.:-]+)\s+entered RUNNING state",
            line,
        )
        if success_match:
            statuses[success_match.group(1)] = "running"
            continue

        stopped_match = re.search(
            r"stopped:\s+([A-Za-z0-9_.:-]+)\s+\(exit status\s+(\d+)\)",
            line,
        )
        if stopped_match:
            statuses[stopped_match.group(1)] = (
                "failed" if stopped_match.group(2) != "0" else "stopped"
            )
            continue

        terminated_match = re.search(
            r"stopped:\s+([A-Za-z0-9_.:-]+)\s+\(terminated by SIGTERM\)",
            line,
        )
        if terminated_match:
            statuses[terminated_match.group(1)] = "stopped"
            continue

        fatal_match = re.search(r"FATAL:\s+([A-Za-z0-9_.:-]+)\s+", line)
        if fatal_match:
            statuses[fatal_match.group(1)] = "failed"

    return statuses


def _runtime_status_to_systemctl_columns(status: str) -> tuple[str, str]:
    if status == "running":
        return "active", "running"
    if status == "failed":
        return "failed", "failed"
    if status == "stopped":
        return "inactive", "dead"
    return "inactive", "dead"
