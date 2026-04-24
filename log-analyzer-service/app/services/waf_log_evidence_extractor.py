from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re

from app.core.config import get_settings
from app.parsers.linux_default_parser import LinuxDefaultParser
from app.schemas.waf_evidence import (
    DerivedSummary,
    LogEvidenceV1,
    LogFinding,
    ResourceSignal,
    RuntimeComponentEvidence,
    WafEvidenceInputSummary,
    WafEvidenceRequestV1,
    WafEvidenceResponseV1,
)


SYSTEM_INFO_NAMES = {"system_info", "system_info.txt", "system_info.log"}
RESOURCE_SUMMARY_NAMES = {
    "resource_summary",
    "resource_summary.txt",
    "resource_summary.log",
}
LOG_SUFFIXES = {".log", ".txt"}
SERVICE_PROFILE_RELATIVE_PATH = Path("safeline/service_profile.yml")
MINION_VERSION_RELATIVE_PATH = Path("safeline/minion-version.txt")
DOCKER_STATS_RELATIVE_PATH = Path("container/docker_stats.txt")
TOP_RELATIVE_PATH = Path("system/top.txt")
KERNEL_VERSION_RELATIVE_PATH = Path("system/kernel_version.txt")
IP_ADDR_RELATIVE_PATH = Path("network/ip-addr.txt")

RESOURCE_THRESHOLDS = {
    "cpu": (85.0, 95.0),
    "memory": (85.0, 95.0),
    "disk": (85.0, 95.0),
}

FINDING_PATTERNS = [
    ("oom", re.compile(r"out of memory|\boom\b", re.IGNORECASE), "high"),
    ("disk_high", re.compile(r"no space left|disk.+(?:full|high)", re.IGNORECASE), "high"),
    ("port_bind_fail", re.compile(r"address already in use|bind.+failed", re.IGNORECASE), "high"),
    (
        "dependency_fail",
        re.compile(
            r"no elasticsearch node available|failed to connect to elasticsearch|connection refused|dial tcp|connect.+failed",
            re.IGNORECASE,
        ),
        "high",
    ),
    ("health_fail", re.compile(r"health check failed|unhealthy", re.IGNORECASE), "high"),
    ("restart", re.compile(r"restarting|restart loop", re.IGNORECASE), "high"),
    (
        "error_log",
        re.compile(r"invalid-license|license does not exist|failed to report plugin state", re.IGNORECASE),
        "medium",
    ),
]
HIGH_VALUE_LOG_STEMS = {
    "traffic-learning",
    "mario",
    "mgt-api",
    "detector-srv",
    "mgt-es",
    "mgt-redis",
    "mgt-postgres",
    "ripley-work",
}

COMPONENT_ALIASES = {
    "postgres": "mgt-postgres",
    "redis": "mgt-redis",
    "es": "mgt-es",
    "management": "mgt-api",
    "detector": "detector-srv",
    "ripley": "ripley-work",
}
IGNORED_IP_INTERFACES = {"lo", "docker0", "safeline"}
IGNORED_IP_PREFIXES = ("127.",)


class WafEvidenceExtractorError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class RuntimeComponentSeed:
    component_name: str
    image_or_version: str | None = None
    source_refs: list[str] | None = None
    evidence_text: str | None = None
    status: str = "unknown"
    health: str = "unknown"
    restart_signal: bool = False
    source_type: str = "container"


@dataclass(frozen=True)
class DockerStatsRow:
    container_name: str
    cpu_percent: float | None
    memory_percent: float | None
    raw_line: str


@dataclass(frozen=True)
class ServiceProfileComponent:
    service_name: str
    component_name: str
    image_or_version: str | None
    source_ref: str


@dataclass(frozen=True)
class WafLogEvidenceExtractor:
    analyzer_version: str
    allow_directory_source: bool
    linux_parser: LinuxDefaultParser = LinuxDefaultParser()

    def extract(self, request: WafEvidenceRequestV1) -> WafEvidenceResponseV1:
        extraction_started_at = _utc_now_iso()
        analysis_root = self._resolve_analysis_root(request)
        file_count, directory_count = _scan_analysis_root(analysis_root)

        try:
            unified_json = self.linux_parser.parse(
                task_id=request.task_id,
                analysis_root=analysis_root,
                archive_name=request.archive_name,
                archive_size_bytes=request.archive_size_bytes,
            )
            evidence = _build_log_evidence(
                request.task_id,
                analysis_root,
                unified_json,
            )
        except WafEvidenceExtractorError:
            raise
        except Exception as exc:
            raise WafEvidenceExtractorError(
                status_code=500,
                code="waf_evidence_internal_error",
                message="WAF evidence extraction failed.",
                details={"task_id": request.task_id},
            ) from exc

        extraction_finished_at = _utc_now_iso()
        return WafEvidenceResponseV1(
            analyzer_version=self.analyzer_version,
            extraction_started_at=extraction_started_at,
            extraction_finished_at=extraction_finished_at,
            input_summary=WafEvidenceInputSummary(
                path=analysis_root.as_posix(),
                file_count=file_count,
                directory_count=directory_count,
            ),
            result=evidence,
        )

    def _resolve_analysis_root(self, request: WafEvidenceRequestV1) -> Path:
        if request.source.type != "directory":
            raise WafEvidenceExtractorError(
                status_code=400,
                code="unsupported_source_type",
                message="Only directory source is supported in waf-evidence-request/v1.",
                details={"source_type": request.source.type},
            )
        if not self.allow_directory_source:
            raise WafEvidenceExtractorError(
                status_code=400,
                code="unsupported_source_type",
                message="Directory source is disabled by analyzer configuration.",
                details={"source_type": request.source.type},
            )

        source_path = request.source.path.strip()
        if not source_path:
            raise WafEvidenceExtractorError(
                status_code=400,
                code="invalid_source_path",
                message="Directory source path is required.",
            )

        analysis_root = Path(source_path)
        if not analysis_root.exists():
            raise WafEvidenceExtractorError(
                status_code=404,
                code="source_not_found",
                message="Requested source directory does not exist.",
                details={"path": source_path},
            )
        if not analysis_root.is_dir():
            raise WafEvidenceExtractorError(
                status_code=400,
                code="source_not_directory",
                message="Requested source path is not a directory.",
                details={"path": source_path},
            )
        return analysis_root.resolve()


def build_waf_log_evidence_extractor() -> WafLogEvidenceExtractor:
    settings = get_settings()
    return WafLogEvidenceExtractor(
        analyzer_version=settings.analyzer_version,
        allow_directory_source=settings.allow_directory_source,
    )


def _build_log_evidence(task_id: str, analysis_root: Path, unified_json) -> LogEvidenceV1:
    runtime_components = _build_runtime_components(unified_json, analysis_root)
    resource_signals = _build_resource_signals(analysis_root)
    log_findings = _build_log_findings(analysis_root, runtime_components=runtime_components)
    derived_summary = _build_derived_summary(runtime_components, resource_signals, log_findings)

    return LogEvidenceV1(
        task_id=task_id,
        product_version=_detect_product_version(analysis_root),
        host_hostname=_detect_host_hostname(analysis_root) or unified_json.host_info.hostname,
        host_ip_list=_detect_host_ips(analysis_root) or _split_ip_values(unified_json.host_info.ip),
        host_os_name=_detect_host_os_name(analysis_root) or unified_json.host_info.os_name,
        host_kernel_version=_detect_host_kernel_version(analysis_root) or unified_json.host_info.kernel_version,
        runtime_components=runtime_components,
        resource_signals=resource_signals,
        log_findings=log_findings,
        derived_summary=derived_summary,
    )


def _build_runtime_components(unified_json, analysis_root: Path) -> list[RuntimeComponentEvidence]:
    components: dict[str, RuntimeComponentEvidence] = {}

    for service in unified_json.services:
        components[service.name] = RuntimeComponentEvidence(
            component_name=service.name,
            source_type="service",
            status=service.status,
            health="unknown",
            image_or_version=service.version,
            restart_signal="restart" in (service.notes or "").lower(),
            evidence_text=service.notes or "-",
            source_refs=["system/systemctl_status"],
        )

    for container in unified_json.containers:
        note = container.notes or "-"
        lowered_note = note.lower()
        status = "restarting" if "restarting" in lowered_note else container.status
        health = (
            "unhealthy"
            if "unhealthy" in lowered_note
            else ("healthy" if "healthy" in lowered_note else "unknown")
        )
        components[container.name] = RuntimeComponentEvidence(
            component_name=container.name,
            source_type="container",
            status=status,
            health=health,
            image_or_version=container.image,
            restart_signal="restarting" in lowered_note,
            evidence_text=note,
            source_refs=["containers/docker_ps"],
        )

    docker_stats = _parse_docker_stats(analysis_root)
    for profile_component in _parse_service_profile_components(analysis_root):
        stats_row = docker_stats.get(profile_component.component_name)
        refs = [profile_component.source_ref]
        evidence_parts = [f"service={profile_component.service_name}"]
        status = "unknown"
        if profile_component.component_name in docker_stats:
            refs.append(_to_source_ref(analysis_root, analysis_root / DOCKER_STATS_RELATIVE_PATH))
            evidence_parts.append("docker_stats_detected=true")
            status = "running"
        if profile_component.image_or_version:
            evidence_parts.append(f"image={profile_component.image_or_version}")
        if stats_row is not None and stats_row.memory_percent is not None:
            evidence_parts.append(f"memory={stats_row.memory_percent:.2f}%")

        components.setdefault(
            profile_component.component_name,
            RuntimeComponentEvidence(
                component_name=profile_component.component_name,
                source_type="container",
                status=status,
                health="unknown",
                image_or_version=profile_component.image_or_version,
                restart_signal=False,
                evidence_text="; ".join(evidence_parts),
                source_refs=refs,
            ),
        )

    for stats_row in docker_stats.values():
        components.setdefault(
            stats_row.container_name,
            RuntimeComponentEvidence(
                component_name=stats_row.container_name,
                source_type="container",
                status="running",
                health="unknown",
                image_or_version=None,
                restart_signal=False,
                evidence_text=stats_row.raw_line,
                source_refs=[_to_source_ref(analysis_root, analysis_root / DOCKER_STATS_RELATIVE_PATH)],
            ),
        )

    return list(components.values())


def _build_resource_signals(analysis_root: Path) -> list[ResourceSignal]:
    summary_signals = _build_resource_signals_from_summary(analysis_root)
    if summary_signals:
        return summary_signals

    signals: list[ResourceSignal] = []
    top_path = _locate_relative_path(analysis_root, TOP_RELATIVE_PATH)
    if top_path.is_file():
        content = top_path.read_text(encoding="utf-8", errors="ignore")
        cpu_percent = _parse_top_cpu_percent(content)
        if cpu_percent is not None:
            signals.append(
                _build_signal(
                    subject="host",
                    metric="cpu",
                    observed_value=cpu_percent,
                    raw_text=f"top cpu used={cpu_percent:.2f}%",
                    source_ref=_to_source_ref(analysis_root, top_path),
                )
            )

        memory_percent = _parse_top_memory_percent(content)
        if memory_percent is not None:
            signals.append(
                _build_signal(
                    subject="host",
                    metric="memory",
                    observed_value=memory_percent,
                    raw_text=f"top memory used={memory_percent:.2f}%",
                    source_ref=_to_source_ref(analysis_root, top_path),
                )
            )

    docker_stats_path = _locate_relative_path(analysis_root, DOCKER_STATS_RELATIVE_PATH)
    if docker_stats_path is not None:
        for stats_row in _parse_docker_stats(analysis_root).values():
            if stats_row.memory_percent is None:
                continue
            if stats_row.memory_percent < RESOURCE_THRESHOLDS["memory"][0]:
                continue
            signals.append(
                _build_signal(
                    subject=stats_row.container_name,
                    metric="memory",
                    observed_value=stats_row.memory_percent,
                    raw_text=stats_row.raw_line,
                    source_ref=_to_source_ref(analysis_root, docker_stats_path),
                    scope="container",
                )
            )

    return signals


def _build_resource_signals_from_summary(analysis_root: Path) -> list[ResourceSignal]:
    resource_path = _find_input_file(
        analysis_root,
        preferred_relative_path=Path("resources/resource_summary"),
        names=RESOURCE_SUMMARY_NAMES,
    )
    if resource_path is None:
        return []

    signals: list[ResourceSignal] = []
    content = resource_path.read_text(encoding="utf-8", errors="ignore")
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parsed = _parse_resource_line(line)
        if parsed is None:
            continue
        metric, observed_value = parsed
        signals.append(
            _build_signal(
                subject="host",
                metric=metric,
                observed_value=observed_value,
                raw_text=line,
                source_ref=_to_source_ref(analysis_root, resource_path),
            )
        )

    return signals


def _build_signal(
    *,
    subject: str,
    metric: str,
    observed_value: float,
    raw_text: str,
    source_ref: str,
    scope: str = "host",
) -> ResourceSignal:
    high_threshold, critical_threshold = RESOURCE_THRESHOLDS[metric]
    if observed_value >= critical_threshold:
        level = "critical"
    elif observed_value >= high_threshold:
        level = "high"
    else:
        level = "normal"

    return ResourceSignal(
        scope=scope,
        subject=subject,
        metric=metric,
        observed_value=observed_value,
        unit="percent",
        level=level,
        threshold_hit=level in {"high", "critical"},
        raw_text=raw_text,
        source_refs=[source_ref],
    )


def _build_log_findings(
    analysis_root: Path,
    *,
    runtime_components: list[RuntimeComponentEvidence],
) -> list[LogFinding]:
    findings: list[LogFinding] = []
    finding_index = 1
    seen_keys: set[tuple[str, str, str]] = set()

    for component in runtime_components:
        if component.status in {"failed", "restarting"}:
            finding_type = "restart" if component.status == "restarting" else "health_fail"
            key = (finding_type, component.component_name, "|".join(component.source_refs))
            if key in seen_keys:
                continue
            findings.append(
                LogFinding(
                    finding_id=f"fdg_{finding_index:03d}",
                    finding_type=finding_type,
                    subject=component.component_name,
                    severity="high",
                    summary=f"{component.component_name} status is {component.status}",
                    evidence_text=component.evidence_text,
                    source_refs=list(component.source_refs),
                )
            )
            finding_index += 1
            seen_keys.add(key)
        elif component.health == "unhealthy":
            key = ("health_fail", component.component_name, "|".join(component.source_refs))
            if key in seen_keys:
                continue
            findings.append(
                LogFinding(
                    finding_id=f"fdg_{finding_index:03d}",
                    finding_type="health_fail",
                    subject=component.component_name,
                    severity="high",
                    summary=f"{component.component_name} health check failed",
                    evidence_text=component.evidence_text,
                    source_refs=list(component.source_refs),
                )
            )
            finding_index += 1
            seen_keys.add(key)

    for path in _candidate_log_paths(analysis_root):
        source_ref = _to_source_ref(analysis_root, path)
        content = path.read_text(encoding="utf-8", errors="ignore")
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            matched = _match_finding(line)
            if matched is None:
                continue
            finding_type, severity = matched
            subject = _guess_subject(line, runtime_components, fallback_subject=_fallback_subject_from_path(path))
            key = (finding_type, subject, source_ref)
            if key in seen_keys:
                continue
            findings.append(
                LogFinding(
                    finding_id=f"fdg_{finding_index:03d}",
                    finding_type=finding_type,
                    subject=subject,
                    severity=severity,
                    summary=_normalize_summary(finding_type, subject, line),
                    evidence_text=line[:500],
                    source_refs=[source_ref],
                )
            )
            finding_index += 1
            seen_keys.add(key)
            if len(findings) >= 12:
                return findings

    return findings


def _build_derived_summary(
    runtime_components: list[RuntimeComponentEvidence],
    resource_signals: list[ResourceSignal],
    log_findings: list[LogFinding],
) -> DerivedSummary:
    abnormal_components = [
        component
        for component in runtime_components
        if component.status in {"failed", "restarting", "stopped"}
        or component.health == "unhealthy"
    ]
    high_resource_items = [
        f"{signal.subject}:{signal.metric}:{signal.level}"
        for signal in resource_signals
        if signal.level in {"high", "critical"}
    ]
    key_risks = [finding.summary for finding in log_findings[:5]]

    if abnormal_components or any(signal.level == "critical" for signal in resource_signals):
        overall_runtime_state = "abnormal"
    elif high_resource_items or log_findings:
        overall_runtime_state = "warning"
    elif runtime_components or resource_signals:
        overall_runtime_state = "healthy"
    else:
        overall_runtime_state = "unknown"

    return DerivedSummary(
        overall_runtime_state=overall_runtime_state,
        abnormal_component_count=len(abnormal_components),
        high_resource_items=high_resource_items,
        key_risks=key_risks,
    )


def _detect_product_version(analysis_root: Path) -> str | None:
    service_profile_path = _locate_relative_path(analysis_root, SERVICE_PROFILE_RELATIVE_PATH)
    if service_profile_path is not None:
        content = service_profile_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"PRODUCT_VERSION=([^\s\"']+)", content)
        if match is not None:
            return match.group(1).strip()

    minion_version_path = _locate_relative_path(analysis_root, MINION_VERSION_RELATIVE_PATH)
    if minion_version_path is not None:
        content = minion_version_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"^\s*Version:\s*(.+?)\s*$", content, re.MULTILINE)
        if match is not None:
            return match.group(1).strip()

    for relative_path in [
        Path("meta/product_version.txt"),
        Path("meta/version.txt"),
        Path("version.txt"),
    ]:
        candidate = analysis_root / relative_path
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                return text.splitlines()[0].strip()

    version_candidate = _find_input_file(
        analysis_root,
        preferred_relative_path=Path("system/system_info"),
        names=SYSTEM_INFO_NAMES,
    )
    if version_candidate is None:
        return None
    content = version_candidate.read_text(encoding="utf-8", errors="ignore")
    for line in content.splitlines():
        match = re.match(r"^\s*(product_version|version)\s*[:=]\s*(.+?)\s*$", line, re.IGNORECASE)
        if match:
            return match.group(2).strip()
    return None


def _detect_host_os_name(analysis_root: Path) -> str | None:
    kernel_version_path = _locate_relative_path(analysis_root, KERNEL_VERSION_RELATIVE_PATH)
    if kernel_version_path is None:
        return None

    content = kernel_version_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r'^PRETTY_NAME="(.+?)"$', content, re.MULTILINE)
    if match is not None:
        return match.group(1).strip()
    return None


def _detect_host_kernel_version(analysis_root: Path) -> str | None:
    kernel_version_path = _locate_relative_path(analysis_root, KERNEL_VERSION_RELATIVE_PATH)
    if kernel_version_path is None:
        return None

    content = kernel_version_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"^Linux\s+\S+\s+([^\s]+)", content, re.MULTILINE)
    if match is not None:
        return match.group(1).strip()
    return None


def _detect_host_hostname(analysis_root: Path) -> str | None:
    kernel_version_path = _locate_relative_path(analysis_root, KERNEL_VERSION_RELATIVE_PATH)
    if kernel_version_path is not None:
        content = kernel_version_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"^Linux\s+([^\s]+)", content, re.MULTILINE)
        if match is not None:
            return match.group(1).strip()
    return None


def _detect_host_ips(analysis_root: Path) -> list[str]:
    ip_addr_path = _locate_relative_path(analysis_root, IP_ADDR_RELATIVE_PATH)
    if ip_addr_path is None:
        return []

    ips: list[str] = []
    current_interface: str | None = None
    content = ip_addr_path.read_text(encoding="utf-8", errors="ignore")
    for raw_line in content.splitlines():
        interface_match = re.match(r"^\d+:\s*([^:]+):", raw_line)
        if interface_match is not None:
            current_interface = interface_match.group(1).strip()
            continue

        ip_match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)/\d+", raw_line)
        if ip_match is None:
            continue
        ip = ip_match.group(1)
        if current_interface in IGNORED_IP_INTERFACES:
            continue
        if any(ip.startswith(prefix) for prefix in IGNORED_IP_PREFIXES):
            continue
        ips.append(ip)

    return list(dict.fromkeys(ips))


def _split_ip_values(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [part.strip() for part in re.split(r"[,/ ]+", raw_value) if part.strip()]


def _parse_resource_line(line: str) -> tuple[str, float] | None:
    lowered = line.lower()
    for metric in RESOURCE_THRESHOLDS:
        if metric not in lowered:
            continue
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
        if match is None:
            continue
        return metric, float(match.group(1))
    return None


def _parse_service_profile_components(analysis_root: Path) -> list[ServiceProfileComponent]:
    service_profile_path = _locate_relative_path(analysis_root, SERVICE_PROFILE_RELATIVE_PATH)
    if service_profile_path is None:
        return []

    components: list[ServiceProfileComponent] = []
    current_service: str | None = None
    current_container_name: str | None = None
    current_image: str | None = None

    def flush() -> None:
        nonlocal current_service, current_container_name, current_image
        if current_service is None:
            return
        if current_container_name is not None or current_image is not None:
            component_name = COMPONENT_ALIASES.get(current_service, current_container_name or current_service)
            components.append(
                ServiceProfileComponent(
                    service_name=current_service,
                    component_name=component_name,
                    image_or_version=current_image,
                    source_ref=_to_source_ref(analysis_root, service_profile_path),
                )
            )
        current_service = None
        current_container_name = None
        current_image = None

    for raw_line in service_profile_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        service_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", raw_line)
        if service_match is not None:
            flush()
            current_service = service_match.group(1)
            continue

        if current_service is None:
            continue

        container_match = re.match(r"^\s{4}container_name:\s*(.+?)\s*$", raw_line)
        if container_match is not None:
            current_container_name = container_match.group(1).strip().strip("\"'")
            continue

        image_match = re.match(r"^\s{4}image:\s*(.+?)\s*$", raw_line)
        if image_match is not None:
            current_image = image_match.group(1).strip().strip("\"'")

    flush()
    return components


def _parse_docker_stats(analysis_root: Path) -> dict[str, DockerStatsRow]:
    docker_stats_path = _locate_relative_path(analysis_root, DOCKER_STATS_RELATIVE_PATH)
    if docker_stats_path is None:
        return {}

    rows: dict[str, DockerStatsRow] = {}
    for raw_line in docker_stats_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("CONTAINER ID"):
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            continue

        container_name = parts[1].strip()
        cpu_percent = _safe_float(parts[2].rstrip("%"))
        memory_percent = _safe_float(parts[4].rstrip("%"))
        rows[container_name] = DockerStatsRow(
            container_name=container_name,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            raw_line=line,
        )

    return rows


def _parse_top_cpu_percent(content: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s+id", content)
    if match is None:
        return None
    idle = float(match.group(1))
    used = max(0.0, 100.0 - idle)
    return round(used, 2)


def _parse_top_memory_percent(content: str) -> float | None:
    match = re.search(
        r"MiB Mem\s*:\s*(\d+(?:\.\d+)?)\s+total,\s*(\d+(?:\.\d+)?)\s+free,\s*(\d+(?:\.\d+)?)\s+used",
        content,
    )
    if match is None:
        return None

    total = float(match.group(1))
    used = float(match.group(3))
    if total <= 0:
        return None
    return round((used / total) * 100.0, 2)


def _candidate_log_paths(analysis_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for relative_dir in [
        Path("container"),
        Path("safeline/logs"),
    ]:
        for directory in _locate_relative_directories(analysis_root, relative_dir):
            candidates.extend(
                path
                for path in sorted(directory.rglob("*"))
                if path.is_file() and path.suffix.lower() in LOG_SUFFIXES and _is_high_value_log_path(path)
            )
    return candidates


def _match_finding(line: str) -> tuple[str, str] | None:
    for finding_type, pattern, severity in FINDING_PATTERNS:
        if pattern.search(line):
            return finding_type, severity
    return None


def _guess_subject(
    line: str,
    runtime_components: list[RuntimeComponentEvidence],
    *,
    fallback_subject: str,
) -> str:
    if fallback_subject != "host":
        return fallback_subject
    lowered_line = line.lower()
    for component in runtime_components:
        if component.component_name.lower() in lowered_line:
            return component.component_name
    return fallback_subject


def _fallback_subject_from_path(path: Path) -> str:
    stem = path.stem
    if stem in {"snserver", "mario"} and path.parent.name in {"detector", "mario"}:
        return path.parent.name
    return stem


def _is_high_value_log_path(path: Path) -> bool:
    return path.stem in HIGH_VALUE_LOG_STEMS


def _normalize_summary(finding_type: str, subject: str, line: str) -> str:
    if finding_type == "dependency_fail":
        return f"{subject} 存在依赖连接失败线索"
    if finding_type == "error_log":
        return f"{subject} 存在许可证或上报异常线索"
    if finding_type == "health_fail":
        return f"{subject} 存在健康检查异常线索"
    if finding_type == "restart":
        return f"{subject} 存在重启线索"
    return line[:160]


def _find_input_file(
    analysis_root: Path,
    *,
    preferred_relative_path: Path,
    names: set[str],
) -> Path | None:
    preferred_path = analysis_root / preferred_relative_path
    if preferred_path.is_file():
        return preferred_path

    for path in sorted(analysis_root.rglob("*")):
        if path.is_file() and path.name.lower() in names:
            return path
    return None


def _locate_relative_path(analysis_root: Path, relative_path: Path) -> Path | None:
    direct_path = analysis_root / relative_path
    if direct_path.is_file():
        return direct_path

    suffix = relative_path.as_posix()
    for path in sorted(analysis_root.rglob(relative_path.name)):
        if path.is_file() and path.as_posix().endswith(suffix):
            return path
    return None


def _locate_relative_directories(analysis_root: Path, relative_dir: Path) -> list[Path]:
    direct_dir = analysis_root / relative_dir
    if direct_dir.is_dir():
        return [direct_dir]

    suffix = relative_dir.as_posix()
    return [
        path
        for path in sorted(analysis_root.rglob(relative_dir.name))
        if path.is_dir() and path.as_posix().endswith(suffix)
    ]


def _to_source_ref(analysis_root: Path, path: Path) -> str:
    return path.relative_to(analysis_root).as_posix()


def _scan_analysis_root(analysis_root: Path) -> tuple[int, int]:
    file_count = 0
    directory_count = 0
    for path in analysis_root.rglob("*"):
        if path.is_file():
            file_count += 1
        elif path.is_dir():
            directory_count += 1
    return file_count, directory_count


def _safe_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
