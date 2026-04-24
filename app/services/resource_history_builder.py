from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from pathlib import Path
from typing import Literal


ResourceHistorySourceKind = Literal["explicit_history", "current_snapshot", "empty"]

RESOURCE_HISTORY_SOURCE_PRIORITY = (
    Path("resources/resource_history.csv"),
    Path("resources/resource_timeseries.csv"),
    Path("resources/resource_history.txt"),
    Path("system/resource_history.csv"),
    Path("system/resource_history.txt"),
)
COLLECTION_TIME_SOURCE_PRIORITY = (
    Path("metadata/collection_info.txt"),
    Path("collection_info.txt"),
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
RESOURCE_HISTORY_BUCKET_HOURS = 12

COLLECT_TIME_PATTERN = re.compile(r"(?:采集时间|collected_at)\s*[:=]\s*(.+)$", re.IGNORECASE)
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
DF_LINE_PATTERN = re.compile(
    r"^(?P<fs>\S+)\s+(?P<size>\S+)\s+(?P<used>\S+)\s+(?P<avail>\S+)\s+(?P<percent>\d+)%\s+(?P<mount>\S+)",
    re.MULTILINE,
)
RESOURCE_PERCENT_PATTERN = re.compile(r"(cpu|memory|disk)\s*[:=]\s*([0-9.]+)%", re.IGNORECASE)


@dataclass(frozen=True)
class ResourceHistoryBuildResult:
    path: Path
    point_count: int
    source_kind: ResourceHistorySourceKind
    source_ref: str | None = None


@dataclass(frozen=True)
class ResourceHistoryPoint:
    timestamp: datetime
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None


def materialize_resource_history_csv(
    analysis_root: Path,
    target_path: Path,
    *,
    reference_time: datetime | None = None,
) -> ResourceHistoryBuildResult:
    """Write a canonical resource history CSV for preprocessing consumers.

    The generator is intentionally conservative: explicit history is bucketed to
    a 12-hour cadence, while snapshot-only inputs produce at most one point.
    """

    resolved_root = analysis_root.resolve()
    resolved_reference_time = _resolve_reference_time(resolved_root, reference_time)

    explicit_points, explicit_source_ref = _extract_explicit_history_points(
        resolved_root,
        window_start=resolved_reference_time - timedelta(days=30),
        window_end=resolved_reference_time,
    )
    if explicit_points:
        points = _bucket_points(explicit_points, bucket_hours=RESOURCE_HISTORY_BUCKET_HOURS)
        _write_resource_history_csv(points, target_path)
        return ResourceHistoryBuildResult(
            path=target_path,
            point_count=len(points),
            source_kind="explicit_history",
            source_ref=explicit_source_ref,
        )

    snapshot_point = _extract_current_snapshot_point(resolved_root, resolved_reference_time)
    if snapshot_point is not None:
        points = _bucket_points([snapshot_point], bucket_hours=RESOURCE_HISTORY_BUCKET_HOURS)
        _write_resource_history_csv(points, target_path)
        return ResourceHistoryBuildResult(
            path=target_path,
            point_count=len(points),
            source_kind="current_snapshot",
            source_ref="snapshot_sources",
        )

    _write_resource_history_csv([], target_path)
    return ResourceHistoryBuildResult(path=target_path, point_count=0, source_kind="empty")


def _extract_explicit_history_points(
    analysis_root: Path,
    *,
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[ResourceHistoryPoint], str | None]:
    for relative_path in RESOURCE_HISTORY_SOURCE_PRIORITY:
        candidate = analysis_root / relative_path
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        points = _parse_resource_history_text(
            text,
            window_start=window_start,
            window_end=window_end,
        )
        if points:
            return points, relative_path.as_posix()
    return [], None


def _parse_resource_history_text(
    text: str,
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[ResourceHistoryPoint]:
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

    raw_points: list[ResourceHistoryPoint] = []
    seen: set[tuple[datetime, float | None, float | None, float | None]] = set()
    for row in rows[1:]:
        if not row or _is_separator_row(row) or timestamp_index >= len(row):
            continue
        parsed_timestamp = _parse_timestamp(row[timestamp_index])
        if parsed_timestamp is None or parsed_timestamp < window_start or parsed_timestamp > window_end:
            continue

        cpu_percent = _parse_percent_cell(row, cpu_index)
        memory_percent = _parse_percent_cell(row, memory_index)
        disk_percent = _parse_percent_cell(row, disk_index)
        if cpu_percent is None and memory_percent is None and disk_percent is None:
            continue

        key = (parsed_timestamp, cpu_percent, memory_percent, disk_percent)
        if key in seen:
            continue
        seen.add(key)
        raw_points.append(
            ResourceHistoryPoint(
                timestamp=parsed_timestamp,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_percent=disk_percent,
            )
        )
    return raw_points


def _extract_current_snapshot_point(analysis_root: Path, timestamp: datetime) -> ResourceHistoryPoint | None:
    cpu_percent = _extract_cpu_snapshot(analysis_root)
    memory_percent = _extract_memory_snapshot(analysis_root)
    disk_percent = _extract_disk_snapshot(analysis_root)
    if cpu_percent is None and memory_percent is None and disk_percent is None:
        return None
    return ResourceHistoryPoint(
        timestamp=timestamp,
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        disk_percent=disk_percent,
    )


def _extract_cpu_snapshot(analysis_root: Path) -> float | None:
    for relative_path in CPU_SOURCE_PRIORITY:
        text = _read_optional_text(analysis_root / relative_path)
        if text is None:
            continue
        if match := CPU_TOP_PATTERN.search(text):
            return round(float(match.group(1)) + float(match.group(2)), 1)
        if relative_path.name == "resource_summary.txt":
            return _extract_resource_summary_metric(text, metric_name="cpu")
    return None


def _extract_memory_snapshot(analysis_root: Path) -> float | None:
    for relative_path in MEMORY_SOURCE_PRIORITY:
        text = _read_optional_text(analysis_root / relative_path)
        if text is None:
            continue
        if relative_path.name == "free.txt":
            if match := FREE_MEM_PATTERN.search(text):
                total = float(match.group(1))
                used = float(match.group(2))
                return round((used / total) * 100, 1) if total else None
        if relative_path.name == "resource_summary.txt":
            return _extract_resource_summary_metric(text, metric_name="memory")
        if relative_path.name == "top.txt":
            if match := TOP_MEM_PATTERN.search(text):
                total = float(match.group(1))
                used = float(match.group(3))
                return round((used / total) * 100, 1) if total else None
    return None


def _extract_disk_snapshot(analysis_root: Path) -> float | None:
    for relative_path in DISK_SOURCE_PRIORITY:
        text = _read_optional_text(analysis_root / relative_path)
        if text is None:
            continue
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
                return float(preferred_match.group("percent"))
        if relative_path.name in {"resource_summary.txt", "disk_usage.txt"}:
            return _extract_resource_summary_metric(text, metric_name="disk")
    return None


def _resolve_reference_time(analysis_root: Path, reference_time: datetime | None) -> datetime:
    collection_time_raw = _extract_collection_time_raw(analysis_root)
    if collection_time_raw:
        parsed_collection_time = _parse_timestamp(collection_time_raw)
        if parsed_collection_time is not None:
            return parsed_collection_time
    if reference_time is not None:
        if reference_time.tzinfo is None:
            return reference_time.replace(tzinfo=UTC)
        return reference_time.astimezone(UTC)
    return datetime.now(UTC)


def _extract_collection_time_raw(analysis_root: Path) -> str | None:
    for relative_path in COLLECTION_TIME_SOURCE_PRIORITY:
        text = _read_optional_text(analysis_root / relative_path)
        if text is None:
            continue
        for line in text.splitlines():
            if match := COLLECT_TIME_PATTERN.search(line.strip()):
                return match.group(1).strip()
    if match := re.search(r"-(\d{10})(?:\D*)$", analysis_root.name):
        return datetime.fromtimestamp(int(match.group(1)), UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return None


def _bucket_points(points: list[ResourceHistoryPoint], *, bucket_hours: int) -> list[ResourceHistoryPoint]:
    buckets: dict[datetime, list[ResourceHistoryPoint]] = {}
    for point in points:
        bucket_start = _floor_datetime_to_bucket(point.timestamp, bucket_hours=bucket_hours)
        buckets.setdefault(bucket_start, []).append(point)

    bucketed: list[ResourceHistoryPoint] = []
    for bucket_start, bucket_points in sorted(buckets.items(), key=lambda item: item[0]):
        bucketed.append(
            ResourceHistoryPoint(
                timestamp=bucket_start,
                cpu_percent=_average_optional_percent(point.cpu_percent for point in bucket_points),
                memory_percent=_average_optional_percent(point.memory_percent for point in bucket_points),
                disk_percent=_average_optional_percent(point.disk_percent for point in bucket_points),
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


def _write_resource_history_csv(points: list[ResourceHistoryPoint], target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["timestamp", "cpu", "memory", "disk"])
        for point in points:
            writer.writerow(
                [
                    _to_iso(point.timestamp),
                    _format_percent(point.cpu_percent),
                    _format_percent(point.memory_percent),
                    _format_percent(point.disk_percent),
                ]
            )


def _format_percent(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}"


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


def _is_separator_row(row: list[str]) -> bool:
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


def _parse_percent_cell(row: list[str], index: int | None) -> float | None:
    if index is None or index >= len(row):
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%?", row[index].strip())
    if match is None:
        return None
    value = round(float(match.group(1)), 1)
    if value < 0 or value > 100:
        return None
    return value


def _parse_timestamp(raw_value: str) -> datetime | None:
    raw_candidate = raw_value.strip()
    try:
        parsed = datetime.fromisoformat(raw_candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        pass
    candidate = re.sub(r"(?<=\d)T(?=\d)", " ", raw_candidate).replace("Z", "")
    candidate = re.sub(r"[.,]\d+(?=\s|$)", "", candidate)
    candidate = re.sub(r"\s+(?:UTC|GMT|CST|UTC[+-]\d{1,2}(?::\d{2})?)$", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(candidate, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _to_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_resource_summary_metric(text: str, *, metric_name: str) -> float | None:
    for metric, value in RESOURCE_PERCENT_PATTERN.findall(text):
        if metric.lower() == metric_name:
            parsed = float(value)
            if 0 <= parsed <= 100:
                return round(parsed, 1)
    return None


def _read_optional_text(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="ignore")
