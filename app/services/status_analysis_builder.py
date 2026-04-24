from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from pathlib import Path

from app.schemas.status_analysis import (
    StatusAnalysisEvidenceV1,
    StatusAnalysisKeyFinding,
    StatusAnalysisMetadata,
    StatusAnalysisMetricSnapshot,
    StatusAnalysisResourceTimePoint,
    StatusAnalysisScanCoverage,
    StatusAnalysisScanFile,
    StatusAnalysisSource,
    StatusAnalysisStabilityCounts30D,
    StatusAnalysisStabilityEvent,
    StatusAnalysisSummaryV1,
)


LOG_SCAN_ROOTS = (
    Path("logs"),
    Path("container"),
    Path("safeline/logs"),
    Path("system"),
)
LARGE_FILE_MAJOR_ROOTS = (
    Path("safeline/logs/detector"),
    Path("safeline/logs/ripley/stats"),
)
CPU_SOURCE_PRIORITY = (
    Path("system/top.txt"),
    Path("resources/resource_summary.txt"),
)
MEMORY_SOURCE_PRIORITY = (
    Path("system/free.txt"),
    Path("resources/resource_summary.txt"),
    Path("system/top.txt"),
)
DISK_SOURCE_PRIORITY = (
    Path("system/df.txt"),
    Path("system/disk.txt"),
    Path("system/filesystem.txt"),
    Path("system/filesystems.txt"),
    Path("resources/resource_summary.txt"),
    Path("resources/disk_usage.txt"),
)
UPTIME_SOURCE_PRIORITY = (
    Path("system/uptime.txt"),
    Path("system/top.txt"),
    Path("metadata/collection_info.txt"),
)
RESOURCE_HISTORY_SOURCE_PRIORITY = (
    Path("resources/resource_history.csv"),
    Path("resources/resource_timeseries.csv"),
    Path("resources/resource_history.txt"),
    Path("system/resource_history.csv"),
    Path("system/resource_history.txt"),
)
RESOURCE_HISTORY_BUCKET_HOURS = 12
COLLECTION_TIME_SOURCE_PRIORITY = (
    Path("metadata/collection_info.txt"),
    Path("collection_info.txt"),
)
HOST_INFO_SOURCE_PRIORITY = (
    Path("system/system_info"),
    Path("system/system_info.txt"),
)
VERSION_SOURCE_PRIORITY = (
    Path("metadata/product_version.txt"),
    Path("product_version.txt"),
)

TIMESTAMP_PATTERN = re.compile(r"(20\d{2}[-/]\d{2}[-/]\d{2} \d{2}:\d{2}:\d{2})")
ISO_TIMESTAMP_PATTERN = re.compile(r"(20\d{2}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:[.,]\d+)?Z?")
COLLECT_TIME_PATTERN = re.compile(r"(?:采集时间|collected_at)\s*[:=]\s*(.+)$", re.IGNORECASE)
HOSTNAME_PATTERN = re.compile(r"hostname\s*[:=]\s*([^\s]+)", re.IGNORECASE)
PRODUCT_VERSION_PATTERN = re.compile(r"(?:version|版本)\s*[:=]\s*([^\n]+)", re.IGNORECASE)
CPU_TOP_PATTERN = re.compile(
    r"%?Cpu\(s\):\s*([0-9.]+)\s*us,\s*([0-9.]+)\s*sy,.*?([0-9.]+)\s*id",
    re.IGNORECASE,
)
FREE_MEM_PATTERN = re.compile(
    r"^Mem:\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(?:[0-9.]+\s+)?(?:[0-9.]+\s+)?([0-9.]+)",
    re.IGNORECASE | re.MULTILINE,
)
TOP_MEM_PATTERN = re.compile(
    r"MiB\s+Mem\s*:\s*([0-9.]+)\s+total,\s*([0-9.]+)\s+free,\s*([0-9.]+)\s+used,\s*([0-9.]+)\s+buff/cache",
    re.IGNORECASE,
)
FREE_SWAP_PATTERN = re.compile(r"^Swap:\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", re.IGNORECASE | re.MULTILINE)
DF_LINE_PATTERN = re.compile(
    r"^(?P<fs>\S+)\s+(?P<size>\S+)\s+(?P<used>\S+)\s+(?P<avail>\S+)\s+(?P<percent>\d+)%\s+(?P<mount>\S+)",
    re.MULTILINE,
)
RESOURCE_PERCENT_PATTERN = re.compile(r"(cpu|memory|disk)\s*[:=]\s*([0-9.]+)%", re.IGNORECASE)
RESOURCE_UPTIME_PATTERN = re.compile(r"uptime\s*[:=]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
UPTIME_DURATION_PATTERN = re.compile(r"up\s+(.+)$", re.IGNORECASE)


class StatusAnalysisBuildError(Exception):
    pass


@dataclass(frozen=True)
class BuildContext:
    analysis_root: Path
    run_id: str
    generated_at: str
    reference_time: datetime
    coverage: "ScanCoverageTracker"
    large_file_bytes: int
    max_excerpt_lines: int


class ScanCoverageTracker:
    def __init__(self, *, copied_source: bool, large_file_bytes: int) -> None:
        self.mode = "full_copy" if copied_source else "selective"
        self.copied_source = copied_source
        self.large_file_bytes = large_file_bytes
        self._scanned_files: dict[str, StatusAnalysisScanFile] = {}
        self._skipped_files: dict[str, StatusAnalysisScanFile] = {}

    def mark_scanned(
        self,
        relative_path: Path,
        *,
        strategy: str,
        size_bytes: int | None,
        evidence_category: str,
    ) -> None:
        key = relative_path.as_posix()
        existing = self._scanned_files.get(key)
        if existing is None:
            self._scanned_files[key] = StatusAnalysisScanFile(
                path=key,
                strategy=strategy,
                size_bytes=size_bytes,
                evidence_categories=[evidence_category],
            )
            return
        if evidence_category not in existing.evidence_categories:
            existing.evidence_categories.append(evidence_category)
        if existing.strategy != "bounded_line_scan" and strategy == "bounded_line_scan":
            existing.strategy = strategy

    def mark_skipped(
        self,
        relative_path: Path,
        *,
        size_bytes: int | None,
        reason: str,
        evidence_category: str,
    ) -> None:
        key = relative_path.as_posix()
        existing = self._skipped_files.get(key)
        if existing is None:
            self._skipped_files[key] = StatusAnalysisScanFile(
                path=key,
                strategy="skipped",
                size_bytes=size_bytes,
                evidence_categories=[evidence_category],
                reason=reason,
            )
            return
        if evidence_category not in existing.evidence_categories:
            existing.evidence_categories.append(evidence_category)

    def build(self) -> StatusAnalysisScanCoverage:
        skipped_files = sorted(self._skipped_files.values(), key=lambda item: item.path)
        scanned_files = sorted(self._scanned_files.values(), key=lambda item: item.path)
        warnings: list[str] = []
        if skipped_files:
            warnings.append("扫描覆盖度不完整：存在跳过或受限来源，详情见 scan_coverage。")
        if not scanned_files:
            coverage_level = "minimal"
        elif skipped_files:
            coverage_level = "partial"
        else:
            coverage_level = "full"
        return StatusAnalysisScanCoverage(
            mode=self.mode,
            copied_source=self.copied_source,
            coverage_level=coverage_level,
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            warnings=warnings,
        )


def build_status_analysis_from_directory(
    analysis_root: Path,
    *,
    run_id: str,
    generated_at: str,
    reference_time: datetime | None = None,
    generated_resource_history_path: Path | None = None,
    copied_source: bool = False,
    large_file_bytes: int = 50 * 1024 * 1024,
    max_excerpt_lines: int = 200,
) -> tuple[StatusAnalysisEvidenceV1, StatusAnalysisSummaryV1]:
    if not analysis_root.exists():
        raise StatusAnalysisBuildError("Analysis directory does not exist.")
    if not analysis_root.is_dir():
        raise StatusAnalysisBuildError("Analysis source path must be a directory.")

    coverage = ScanCoverageTracker(copied_source=copied_source, large_file_bytes=large_file_bytes)
    collect_time_raw = _extract_collection_time_raw(analysis_root, coverage)
    collect_time = _normalize_timestamp(collect_time_raw) if collect_time_raw else None
    resolved_reference_time = (
        _parse_iso_or_local_timestamp(collect_time_raw)
        if collect_time_raw is not None
        else reference_time
    ) or datetime.now(UTC)
    window_start = resolved_reference_time - timedelta(days=30)

    context = BuildContext(
        analysis_root=analysis_root.resolve(),
        run_id=run_id,
        generated_at=generated_at,
        reference_time=resolved_reference_time,
        coverage=coverage,
        large_file_bytes=large_file_bytes,
        max_excerpt_lines=max_excerpt_lines,
    )

    metadata = StatusAnalysisMetadata(
        collect_time=collect_time,
        collect_time_raw=collect_time_raw,
        reference_time=_to_iso(resolved_reference_time),
        window_start=_to_iso(window_start),
        window_end=_to_iso(resolved_reference_time),
        host_hostname=_extract_hostname(context),
        product_version=_extract_product_version(context),
    )

    cpu_snapshot, cpu_warning = _extract_cpu_snapshot(context)
    memory_snapshot, memory_warning = _extract_memory_snapshot(context)
    disk_snapshot, disk_warning = _extract_disk_snapshot(context)
    uptime_snapshot, uptime_warning = _extract_uptime_snapshot(context)
    resource_time_series = _extract_resource_time_series(
        context,
        window_start=window_start,
        generated_resource_history_path=generated_resource_history_path,
    )
    warnings = [warning for warning in [cpu_warning, memory_warning, disk_warning, uptime_warning] if warning]

    recent_events, historical_events, key_findings = _extract_log_evidence(
        context,
        window_start=window_start,
    )
    summary_key_findings = _aggregate_key_findings(key_findings)
    scan_coverage = coverage.build()
    scan_limitations, major_skipped_sources, coverage_warnings = _summarize_scan_limitations(scan_coverage)

    evidence = StatusAnalysisEvidenceV1(
        run_id=run_id,
        generated_at=generated_at,
        source=StatusAnalysisSource(path=analysis_root.resolve().as_posix()),
        metadata=metadata,
        resource_snapshots=[snapshot for snapshot in [cpu_snapshot, memory_snapshot, disk_snapshot, uptime_snapshot] if snapshot],
        resource_time_series=resource_time_series,
        stability_events=recent_events,
        key_findings=key_findings,
        historical_associations=historical_events,
        scan_coverage=scan_coverage,
        warnings=warnings,
    )

    summary = StatusAnalysisSummaryV1(
        run_id=run_id,
        generated_at=generated_at,
        source=StatusAnalysisSource(path=analysis_root.resolve().as_posix()),
        metadata=metadata,
        cpu_snapshot=cpu_snapshot,
        memory_snapshot=memory_snapshot,
        disk_snapshot=disk_snapshot,
        uptime_snapshot=uptime_snapshot,
        resource_time_series=resource_time_series,
        stability_counts_30d=_summarize_recent_counts(recent_events),
        recent_stability_events=recent_events,
        historical_associations=historical_events,
        service_findings=[finding for finding in summary_key_findings if finding.category == "service"],
        container_findings=[finding for finding in summary_key_findings if finding.category == "container"],
        system_findings=[finding for finding in summary_key_findings if finding.category == "system"],
        coverage_level=scan_coverage.coverage_level,
        scan_limitations=scan_limitations,
        major_skipped_sources=major_skipped_sources,
        coverage_warnings=coverage_warnings,
        warnings=warnings,
    )

    return evidence, summary


def _extract_collection_time_raw(analysis_root: Path, coverage: ScanCoverageTracker) -> str | None:
    for relative_path in COLLECTION_TIME_SOURCE_PRIORITY:
        candidate = analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_text(candidate, analysis_root=analysis_root, relative_path=relative_path, coverage=coverage, evidence_category="metadata")
        for line in text.splitlines():
            if match := COLLECT_TIME_PATTERN.search(line.strip()):
                return match.group(1).strip()
    if match := re.search(r"-(\d{10})(?:\D*)$", analysis_root.name):
        return datetime.fromtimestamp(int(match.group(1)), UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return None


def _extract_hostname(context: BuildContext) -> str | None:
    for relative_path in HOST_INFO_SOURCE_PRIORITY:
        candidate = context.analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_context_text(context, relative_path, evidence_category="metadata")
        for line in text.splitlines():
            if match := HOSTNAME_PATTERN.search(line.strip()):
                return match.group(1).strip()
    return None


def _extract_product_version(context: BuildContext) -> str | None:
    for relative_path in VERSION_SOURCE_PRIORITY:
        candidate = context.analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_context_text(context, relative_path, evidence_category="metadata")
        if match := PRODUCT_VERSION_PATTERN.search(text):
            return match.group(1).strip()
        stripped = text.strip()
        if stripped:
            return stripped
    return None


def _extract_cpu_snapshot(context: BuildContext) -> tuple[StatusAnalysisMetricSnapshot | None, str | None]:
    for relative_path in CPU_SOURCE_PRIORITY:
        candidate = context.analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_context_text(context, relative_path, evidence_category="resource")
        if match := CPU_TOP_PATTERN.search(text):
            cpu_value = round(float(match.group(1)) + float(match.group(2)), 2)
            return (
                StatusAnalysisMetricSnapshot(
                    metric="cpu",
                    current_value=cpu_value,
                    unit="percent",
                    source_ref=relative_path.as_posix(),
                    source_excerpt=f"us={match.group(1)} sy={match.group(2)} id={match.group(3)}",
                    note="Round1 CPU current snapshot from top summary.",
                ),
                None,
            )
        if relative_path.name == "resource_summary.txt":
            if resource_value := _extract_resource_summary_metric(text, metric_name="cpu"):
                return (
                    StatusAnalysisMetricSnapshot(
                        metric="cpu",
                        current_value=resource_value,
                        unit="percent",
                        source_ref=relative_path.as_posix(),
                        source_excerpt="resource_summary cpu",
                        note="Round1 CPU current snapshot from resource summary fallback.",
                    ),
                    None,
                )
    return None, "未从约定优先级来源中提取到 CPU 当前快照。"


def _extract_memory_snapshot(context: BuildContext) -> tuple[StatusAnalysisMetricSnapshot | None, str | None]:
    for relative_path in MEMORY_SOURCE_PRIORITY:
        candidate = context.analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_context_text(context, relative_path, evidence_category="resource")
        if relative_path.name == "free.txt":
            if match := FREE_MEM_PATTERN.search(text):
                total = float(match.group(1))
                used = float(match.group(2))
                available = float(match.group(4))
                used_percent = round((used / total) * 100, 1) if total else None
                if used_percent is not None:
                    return (
                        StatusAnalysisMetricSnapshot(
                            metric="memory",
                            current_value=used_percent,
                            unit="percent",
                            source_ref=relative_path.as_posix(),
                            source_excerpt=f"used={used}MiB available={available}MiB total={total}MiB",
                            note="Round1 memory current snapshot from free output. Swap lines are ignored in memory snapshot.",
                        ),
                        None,
                    )
        if relative_path.name == "resource_summary.txt":
            if resource_value := _extract_resource_summary_metric(text, metric_name="memory"):
                return (
                    StatusAnalysisMetricSnapshot(
                        metric="memory",
                        current_value=resource_value,
                        unit="percent",
                        source_ref=relative_path.as_posix(),
                        source_excerpt="resource_summary memory",
                        note="Round1 memory current snapshot from resource summary fallback.",
                    ),
                    None,
                )
        if relative_path.name == "top.txt":
            if match := TOP_MEM_PATTERN.search(text):
                total = float(match.group(1))
                used = float(match.group(3))
                used_percent = round((used / total) * 100, 1) if total else None
                if used_percent is not None:
                    return (
                        StatusAnalysisMetricSnapshot(
                            metric="memory",
                            current_value=used_percent,
                            unit="percent",
                            source_ref=relative_path.as_posix(),
                            source_excerpt=f"used={used}MiB total={total}MiB buff/cache={match.group(4)}MiB",
                            note="Round1 memory current snapshot from top Mem summary fallback.",
                        ),
                        None,
                    )
    return None, "未从约定优先级来源中提取到内存当前快照。"


def _extract_disk_snapshot(context: BuildContext) -> tuple[StatusAnalysisMetricSnapshot | None, str | None]:
    for relative_path in DISK_SOURCE_PRIORITY:
        candidate = context.analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_context_text(context, relative_path, evidence_category="resource")
        if relative_path.name in {"df.txt", "disk.txt", "filesystem.txt", "filesystems.txt"}:
            preferred_match = None
            for match in DF_LINE_PATTERN.finditer(text):
                filesystem = match.group("fs")
                mount = match.group("mount")
                if filesystem.startswith("tmpfs") or filesystem.startswith("devtmpfs"):
                    continue
                preferred_match = match
                if "elasticsearch" in mount or "data" in mount:
                    break
            if preferred_match is not None:
                return (
                    StatusAnalysisMetricSnapshot(
                        metric="disk",
                        current_value=float(preferred_match.group("percent")),
                        unit="percent",
                        source_ref=relative_path.as_posix(),
                        source_excerpt=" ".join(preferred_match.group(0).split()),
                        note="Round2 disk current snapshot from df-like output using the first stable non-tmpfs line, preferring Elasticsearch/data mounts.",
                    ),
                    None,
                )
        if relative_path.name in {"resource_summary.txt", "disk_usage.txt"}:
            if resource_value := _extract_resource_summary_metric(text, metric_name="disk"):
                return (
                    StatusAnalysisMetricSnapshot(
                        metric="disk",
                        current_value=resource_value,
                        unit="percent",
                        source_ref=relative_path.as_posix(),
                        source_excerpt=f"{relative_path.name} disk",
                        note="Round2 disk current snapshot from explicit disk percent fallback.",
                    ),
                    None,
                )
    return None, "未从约定优先级来源中提取到磁盘当前快照。"


def _extract_uptime_snapshot(context: BuildContext) -> tuple[StatusAnalysisMetricSnapshot | None, str | None]:
    for relative_path in UPTIME_SOURCE_PRIORITY:
        candidate = context.analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_context_text(context, relative_path, evidence_category="uptime")
        if relative_path.name == "uptime.txt":
            if seconds := _parse_uptime_seconds_from_text(text):
                return (
                    StatusAnalysisMetricSnapshot(
                        metric="uptime",
                        current_value=float(seconds),
                        unit="seconds",
                        source_ref=relative_path.as_posix(),
                        source_excerpt=" ".join(text.split()),
                        note="Round1 uptime current snapshot from uptime output.",
                    ),
                    None,
                )
        if relative_path.name in {"uptime.txt", "top.txt"}:
            if seconds := _parse_uptime_seconds_from_text(text):
                return (
                    StatusAnalysisMetricSnapshot(
                        metric="uptime",
                        current_value=float(seconds),
                        unit="seconds",
                        source_ref=relative_path.as_posix(),
                        source_excerpt=_first_line_excerpt(text),
                        note=f"Round1 uptime current snapshot from {relative_path.name} output.",
                    ),
                    None,
                )
        if relative_path.name == "collection_info.txt":
            if RESOURCE_UPTIME_PATTERN.search(text):
                seconds = _parse_uptime_seconds_from_text(RESOURCE_UPTIME_PATTERN.search(text).group(1))
                if seconds:
                    return (
                        StatusAnalysisMetricSnapshot(
                            metric="uptime",
                            current_value=float(seconds),
                            unit="seconds",
                            source_ref=relative_path.as_posix(),
                            source_excerpt="collection_info uptime",
                            note="Round1 uptime current snapshot from collection metadata fallback.",
                        ),
                        None,
                    )
    return None, "未从约定优先级来源中提取到 uptime 当前快照。"


def _extract_resource_time_series(
    context: BuildContext,
    *,
    window_start: datetime,
    generated_resource_history_path: Path | None = None,
) -> list[StatusAnalysisResourceTimePoint]:
    generated_relative_path = Path("resources/resource_history.csv")
    if generated_resource_history_path is not None and generated_resource_history_path.exists():
        text = _read_generated_resource_history_text(
            generated_resource_history_path,
            context=context,
            relative_path=generated_relative_path,
        )
        points = _parse_resource_history_text(
            text,
            relative_path=generated_relative_path,
            window_start=_floor_datetime_to_bucket(window_start, bucket_hours=RESOURCE_HISTORY_BUCKET_HOURS),
            window_end=context.reference_time,
        )
        if points:
            return points

    for relative_path in RESOURCE_HISTORY_SOURCE_PRIORITY:
        candidate = context.analysis_root / relative_path
        if not candidate.exists():
            continue
        text = _read_context_text(context, relative_path, evidence_category="resource_history")
        points = _parse_resource_history_text(
            text,
            relative_path=relative_path,
            window_start=window_start,
            window_end=context.reference_time,
        )
        if points:
            return points
    return []


def _read_generated_resource_history_text(
    file_path: Path,
    *,
    context: BuildContext,
    relative_path: Path,
) -> str:
    size_bytes = _file_size(file_path)
    context.coverage.mark_scanned(
        relative_path,
        strategy="full_read",
        size_bytes=size_bytes,
        evidence_category="resource_history",
    )
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _parse_resource_history_text(
    text: str,
    *,
    relative_path: Path,
    window_start: datetime,
    window_end: datetime,
) -> list[StatusAnalysisResourceTimePoint]:
    rows = _split_resource_history_rows(text)
    if len(rows) < 2:
        return []

    header = [cell.strip() for cell in rows[0]]
    timestamp_index = _find_resource_timestamp_column(header)
    cpu_index = _find_resource_metric_column(header, ("cpu", "处理器"))
    memory_index = _find_resource_metric_column(header, ("memory", "mem", "内存"))
    disk_index = _find_resource_metric_column(header, ("disk", "磁盘", "root", "根分区", "系统盘"))
    if timestamp_index is None:
        return []

    raw_points: list[StatusAnalysisResourceTimePoint] = []
    seen: set[tuple[str, float | None, float | None, float | None]] = set()
    for row in rows[1:]:
        if not row or _is_resource_separator_row(row) or timestamp_index >= len(row):
            continue
        parsed_timestamp = _parse_resource_history_timestamp(row[timestamp_index])
        if parsed_timestamp is None:
            continue
        if parsed_timestamp < window_start or parsed_timestamp > window_end:
            continue

        cpu_percent = _parse_resource_percent_cell(row, cpu_index)
        memory_percent = _parse_resource_percent_cell(row, memory_index)
        disk_percent = _parse_resource_percent_cell(row, disk_index)
        if cpu_percent is None and memory_percent is None and disk_percent is None:
            continue

        timestamp = _to_iso(parsed_timestamp)
        key = (timestamp, cpu_percent, memory_percent, disk_percent)
        if key in seen:
            continue
        seen.add(key)
        raw_points.append(
            StatusAnalysisResourceTimePoint(
                timestamp=timestamp,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_percent=disk_percent,
                source_ref=relative_path.as_posix(),
                source_excerpt=" | ".join(cell.strip() for cell in row if cell.strip())[:300],
            )
        )

    return _bucket_resource_time_series(raw_points, bucket_hours=RESOURCE_HISTORY_BUCKET_HOURS)


def _bucket_resource_time_series(
    points: list[StatusAnalysisResourceTimePoint],
    *,
    bucket_hours: int,
) -> list[StatusAnalysisResourceTimePoint]:
    if not points:
        return []

    buckets: dict[datetime, list[StatusAnalysisResourceTimePoint]] = {}
    for point in points:
        parsed_timestamp = _parse_resource_history_timestamp(point.timestamp)
        if parsed_timestamp is None:
            continue
        bucket_start = _floor_datetime_to_bucket(parsed_timestamp, bucket_hours=bucket_hours)
        buckets.setdefault(bucket_start, []).append(point)

    bucketed: list[StatusAnalysisResourceTimePoint] = []
    for bucket_start, bucket_points in sorted(buckets.items(), key=lambda item: item[0]):
        source_refs = sorted({point.source_ref for point in bucket_points})
        bucketed.append(
            StatusAnalysisResourceTimePoint(
                timestamp=_to_iso(bucket_start),
                cpu_percent=_average_optional_percent(point.cpu_percent for point in bucket_points),
                memory_percent=_average_optional_percent(point.memory_percent for point in bucket_points),
                disk_percent=_average_optional_percent(point.disk_percent for point in bucket_points),
                source_ref=", ".join(source_refs),
                source_excerpt=f"12h_average sample_count={len(bucket_points)}",
                sample_count=len(bucket_points),
                aggregation="12h_average",
            )
        )
    return bucketed


def _floor_datetime_to_bucket(value: datetime, *, bucket_hours: int) -> datetime:
    normalized = value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    bucket_hour = (normalized.hour // bucket_hours) * bucket_hours
    return normalized.replace(hour=bucket_hour)


def _average_optional_percent(values) -> float | None:
    available = [value for value in values if value is not None]
    if not available:
        return None
    return round(sum(available) / len(available), 1)


def _split_resource_history_rows(text: str) -> list[list[str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return []

    header_line = lines[0]
    if header_line.startswith("|") and header_line.count("|") >= 2:
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]

    delimiter = ","
    if "\t" in header_line:
        delimiter = "\t"
    elif ";" in header_line and "," not in header_line:
        delimiter = ";"
    elif "|" in header_line and "," not in header_line:
        delimiter = "|"

    return [[cell.strip() for cell in row] for row in csv.reader(lines, delimiter=delimiter)]


def _is_resource_separator_row(row: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in row)


def _find_resource_timestamp_column(header: list[str]) -> int | None:
    for index, cell in enumerate(header):
        normalized = cell.strip().lower()
        if any(token in normalized for token in ("timestamp", "datetime", "采集时间", "时间", "日期")):
            return index
        if normalized in {"time", "date"}:
            return index
    return None


def _find_resource_metric_column(header: list[str], keywords: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(header):
        normalized = cell.strip().lower()
        if any(keyword.lower() in normalized for keyword in keywords):
            return index
    return None


def _parse_resource_percent_cell(row: list[str], index: int | None) -> float | None:
    if index is None or index >= len(row):
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%?", row[index].strip())
    if match is None:
        return None
    value = round(float(match.group(1)), 1)
    if value < 0 or value > 100:
        return None
    return value


def _parse_resource_history_timestamp(raw_value: str) -> datetime | None:
    raw_candidate = raw_value.strip()
    try:
        parsed = datetime.fromisoformat(raw_candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        pass
    candidate = raw_candidate.replace("T", " ").replace("Z", "")
    candidate = re.sub(r"[.,]\d+(?=\s|$)", "", candidate)
    return _parse_iso_or_local_timestamp(candidate)


def _extract_log_evidence(
    context: BuildContext,
    *,
    window_start: datetime,
) -> tuple[list[StatusAnalysisStabilityEvent], list[StatusAnalysisStabilityEvent], list[StatusAnalysisKeyFinding]]:
    recent: list[StatusAnalysisStabilityEvent] = []
    historical: list[StatusAnalysisStabilityEvent] = []
    findings: list[StatusAnalysisKeyFinding] = []
    for file_path in _iter_log_scan_files(context):
        component = file_path.stem
        retained_lines = 0
        for raw_line in _iter_context_lines(context, file_path, evidence_category="log"):
            timestamp = _extract_timestamp(raw_line)
            if timestamp is None:
                continue
            matched = False
            event_type = _detect_event_type(raw_line)
            if event_type is not None:
                event = StatusAnalysisStabilityEvent(
                    timestamp=_to_iso(timestamp),
                    component=component,
                    event_type=event_type,
                    summary=" ".join(raw_line.split()),
                    severity="high" if event_type in {"panic", "abnormal_exit"} else "medium",
                    source_ref=file_path.relative_to(context.analysis_root).as_posix(),
                    in_recent_window=timestamp >= window_start,
                )
                if timestamp >= window_start:
                    recent.append(event)
                else:
                    historical.append(event)
                matched = True
            normalized = raw_line.lower()
            if timestamp >= window_start and any(token in normalized for token in ("error", "failed", "unhealthy")):
                findings.append(
                    StatusAnalysisKeyFinding(
                        category="service" if "mgt" in component or "service" in component else "system",
                        component=component,
                        severity="high" if "failed" in normalized else "medium",
                        summary=" ".join(raw_line.split()),
                        source_ref=file_path.relative_to(context.analysis_root).as_posix(),
                        timestamp=_to_iso(timestamp),
                    )
                )
                matched = True
            if matched:
                retained_lines += 1
                if retained_lines >= context.max_excerpt_lines:
                    break
    return recent, historical, findings[:10]


def _summarize_recent_counts(events: list[StatusAnalysisStabilityEvent]) -> StatusAnalysisStabilityCounts30D:
    counts = StatusAnalysisStabilityCounts30D()
    for event in events:
        if event.event_type == "restart":
            counts.restart_count_30d += 1
        elif event.event_type == "panic":
            counts.panic_count_30d += 1
        elif event.event_type == "abnormal_exit":
            counts.abnormal_exit_count_30d += 1
        elif event.event_type == "unclean_shutdown":
            counts.unclean_shutdown_count_30d += 1
    return counts


def _aggregate_key_findings(findings: list[StatusAnalysisKeyFinding]) -> list[StatusAnalysisKeyFinding]:
    groups: dict[tuple[str, str, str, str], list[StatusAnalysisKeyFinding]] = {}
    passthrough: list[StatusAnalysisKeyFinding] = []
    for finding in findings:
        if finding.category != "service" or finding.timestamp is None:
            passthrough.append(finding)
            continue
        key = (
            finding.category,
            finding.component or "-",
            _finding_time_bucket(finding.timestamp),
            _finding_reason_family(finding.summary),
        )
        groups.setdefault(key, []).append(finding)

    aggregated: list[StatusAnalysisKeyFinding] = []
    for group in groups.values():
        if len(group) == 1:
            aggregated.append(group[0])
        else:
            aggregated.append(_build_aggregated_finding(group))

    combined = aggregated + passthrough
    return sorted(combined, key=lambda item: item.timestamp or "")[:10]


def _build_aggregated_finding(group: list[StatusAnalysisKeyFinding]) -> StatusAnalysisKeyFinding:
    ordered = sorted(group, key=lambda item: item.timestamp or "")
    first = ordered[0]
    last = ordered[-1]
    count = len(ordered)
    severity = "high" if any(item.severity == "high" for item in ordered) else "medium"
    family = _finding_reason_family(first.summary)
    family_label = _finding_reason_label(family)
    evidence_fragments = _representative_evidence_fragments(ordered)
    start_text = _format_timestamp_for_summary(first.timestamp)
    end_text = _format_timestamp_for_summary(last.timestamp)
    time_text = start_text if start_text == end_text else f"{start_text} ~ {end_text}"
    summary = (
        f"{time_text}，{first.component or 'service'} 出现{family_label}事件链，"
        f"已合并 {count} 条相关证据摘录；代表证据：{' / '.join(evidence_fragments)}。"
    )
    return StatusAnalysisKeyFinding(
        category=first.category,
        component=first.component,
        severity=severity,
        summary=summary,
        source_ref=first.source_ref,
        timestamp=first.timestamp,
    )


def _finding_time_bucket(timestamp: str) -> str:
    parsed = _parse_iso_or_local_timestamp(timestamp.replace("T", " ").replace("Z", ""))
    if parsed is None:
        return timestamp[:16]
    bucket_minute = (parsed.minute // 5) * 5
    bucketed = parsed.replace(minute=bucket_minute, second=0, microsecond=0)
    return _to_iso(bucketed)


def _finding_reason_family(summary: str) -> str:
    lowered = summary.lower()
    if "queryphaseexecutionexception" in lowered or "failed to execute [searchrequest" in lowered or "query failed" in lowered:
        return "elasticsearch_query_failed"
    if "unhealthy" in lowered:
        return "unhealthy"
    if "failed" in lowered:
        return "failed"
    if "error" in lowered or "exception" in lowered:
        return "error"
    return "generic"


def _finding_reason_label(family: str) -> str:
    labels = {
        "elasticsearch_query_failed": " Elasticsearch 查询执行失败",
        "unhealthy": "健康检查异常",
        "failed": "执行失败",
        "error": "错误",
        "generic": "异常",
    }
    return labels.get(family, "异常")


def _representative_evidence_fragments(group: list[StatusAnalysisKeyFinding]) -> list[str]:
    fragments: list[str] = []
    for finding in group:
        fragment = _compact_evidence_fragment(finding.summary)
        if fragment and fragment not in fragments:
            fragments.append(fragment)
        if len(fragments) >= 3:
            break
    return fragments or ["见原始日志摘要"]


def _compact_evidence_fragment(summary: str) -> str:
    lowered = summary.lower()
    candidates = [
        ("QueryPhaseExecutionException", "queryphaseexecutionexception"),
        ("Failed to execute SearchRequest", "failed to execute [searchrequest"),
        ("Query Failed", "query failed"),
        ("unhealthy", "unhealthy"),
        ("failed", "failed"),
        ("error", "error"),
    ]
    for label, token in candidates:
        if token in lowered:
            return label
    compacted = " ".join(summary.split())
    if len(compacted) > 80:
        compacted = f"{compacted[:77]}..."
    return compacted


def _format_timestamp_for_summary(timestamp: str | None) -> str:
    if not timestamp:
        return "未标注时间"
    return timestamp[:19].replace("T", " ")


def _extract_resource_summary_metric(text: str, *, metric_name: str) -> float | None:
    for metric, value in RESOURCE_PERCENT_PATTERN.findall(text):
        if metric.lower() == metric_name:
            return float(value)
    return None


def _extract_timestamp(text: str) -> datetime | None:
    if match := ISO_TIMESTAMP_PATTERN.search(text):
        return _parse_iso_or_local_timestamp(f"{match.group(1)} {match.group(2)}")
    match = TIMESTAMP_PATTERN.search(text)
    if match is None:
        return None
    return _parse_iso_or_local_timestamp(match.group(1))


def _detect_event_type(text: str) -> str | None:
    lowered = text.lower()
    if "panic hook is enabled" in lowered:
        return None
    if "panic" in lowered:
        return "panic"
    if "abnormal exit" in lowered or "异常退出" in lowered:
        return "abnormal_exit"
    if "unclean shutdown" in lowered or "非正常关机" in lowered or "recovery complete" in lowered:
        return "unclean_shutdown"
    if " restart" in lowered or "重启" in text or "restarted" in lowered:
        return "restart"
    return None


def _parse_iso_or_local_timestamp(raw_value: str) -> datetime | None:
    candidate = raw_value.strip().replace("/", "-")
    candidate = re.sub(r"\s+(?:UTC|GMT|CST|UTC[+-]\d{1,2}(?::\d{2})?)$", "", candidate, flags=re.IGNORECASE)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(candidate, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _normalize_timestamp(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    parsed = _parse_iso_or_local_timestamp(raw_value)
    if parsed is None:
        return None
    return _to_iso(parsed)


def _to_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_uptime_seconds_from_text(text: str) -> int | None:
    normalized = " ".join(text.split())
    if match := UPTIME_DURATION_PATTERN.search(normalized):
        normalized = match.group(1)
        normalized = re.split(r",\s*\d+\s+users?\b|,\s*load average:", normalized, maxsplit=1)[0]

    total = 0
    matches = re.findall(r"(\d+)\s*(天|days?|小时|hours?|分钟|mins?)", normalized, re.IGNORECASE)
    if matches:
        for raw_value, raw_unit in matches:
            value = int(raw_value)
            unit = raw_unit.lower()
            if unit in {"天", "day", "days"}:
                total += value * 24 * 3600
            elif unit in {"小时", "hour", "hours"}:
                total += value * 3600
            else:
                total += value * 60
        if clock_match := re.search(r"\b(\d{1,2}):(\d{2})\b", normalized):
            total += int(clock_match.group(1)) * 3600
            total += int(clock_match.group(2)) * 60
        return total
    return None


def _read_context_text(context: BuildContext, relative_path: Path, *, evidence_category: str) -> str:
    return _read_text(
        context.analysis_root / relative_path,
        analysis_root=context.analysis_root,
        relative_path=relative_path,
        coverage=context.coverage,
        evidence_category=evidence_category,
    )


def _read_text(
    file_path: Path,
    *,
    analysis_root: Path,
    relative_path: Path,
    coverage: ScanCoverageTracker,
    evidence_category: str,
) -> str:
    size_bytes = _file_size(file_path)
    strategy = "bounded_line_scan" if size_bytes is not None and size_bytes > coverage.large_file_bytes else "full_read"
    coverage.mark_scanned(
        relative_path,
        strategy=strategy,
        size_bytes=size_bytes,
        evidence_category=evidence_category,
    )
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _iter_context_lines(context: BuildContext, file_path: Path, *, evidence_category: str):
    relative_path = file_path.relative_to(context.analysis_root)
    size_bytes = _file_size(file_path)
    strategy = "bounded_line_scan" if size_bytes is not None and size_bytes > context.large_file_bytes else "full_read"
    context.coverage.mark_scanned(
        relative_path,
        strategy=strategy,
        size_bytes=size_bytes,
        evidence_category=evidence_category,
    )
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        yield from handle


def _iter_log_scan_files(context: BuildContext) -> list[Path]:
    files: list[Path] = []
    for relative_root in LOG_SCAN_ROOTS:
        root = context.analysis_root / relative_root
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(context.analysis_root)
            size_bytes = _file_size(path)
            if _is_log_scan_priority(relative_path):
                files.append(path)
                continue
            if _is_major_skipped_source(relative_path, size_bytes, context.large_file_bytes):
                context.coverage.mark_skipped(
                    relative_path,
                    size_bytes=size_bytes,
                    reason="large_non_priority_source_skipped_in_selective_scan_v1",
                    evidence_category="log",
                )
    return files


def _first_line_excerpt(text: str) -> str:
    for line in text.splitlines():
        stripped = " ".join(line.split())
        if stripped:
            return stripped
    return ""


def _is_log_scan_priority(relative_path: Path) -> bool:
    parts = relative_path.parts
    if relative_path in {Path("system/current-boot.log"), Path("system/dmesg.log"), Path("system/last-boot.log")}:
        return True
    if len(parts) == 2 and parts[0] == "container" and relative_path.suffix == ".log":
        return True
    if len(parts) == 4 and parts[:3] == ("safeline", "logs", "minion") and relative_path.suffix == ".log":
        return True
    if len(parts) == 4 and parts[:3] == ("safeline", "logs", "management") and relative_path.suffix == ".log":
        return True
    if len(parts) == 2 and parts[0] == "logs" and relative_path.suffix == ".log":
        return True
    return False


def _is_major_skipped_source(relative_path: Path, size_bytes: int | None, large_file_bytes: int) -> bool:
    if size_bytes is None or size_bytes <= large_file_bytes:
        return False
    return any(_is_relative_to(relative_path, root) for root in LARGE_FILE_MAJOR_ROOTS)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _summarize_scan_limitations(
    scan_coverage: StatusAnalysisScanCoverage,
) -> tuple[list[str], list[str], list[str]]:
    scan_limitations: list[str] = []
    major_skipped_sources: list[str] = [item.path for item in scan_coverage.skipped_files[:20]]
    coverage_warnings: list[str] = list(scan_coverage.warnings)
    if scan_coverage.coverage_level != "full":
        scan_limitations.append("部分大文件或非优先级来源未在 selective scan v1 中展开扫描。")
        if "扫描覆盖度不完整，趋势结论保持保守。" not in coverage_warnings:
            coverage_warnings.append("扫描覆盖度不完整，趋势结论保持保守。")
    return scan_limitations, major_skipped_sources, coverage_warnings
