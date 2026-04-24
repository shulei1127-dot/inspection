from __future__ import annotations

from datetime import UTC, datetime
import re
from pathlib import Path

from app.schemas.trend_assessment import (
    TrendFaultChain,
    TrendInputMetrics,
    TrendInputSource,
    TrendInputV1,
    TrendMetricSample,
    TrendMetricSeries,
    TrendParseSummary,
    TrendRestartEvent,
    TrendStabilityEventCounts,
    TrendStabilityInput,
    TrendUptimeSample,
)


REPORT_TIMESTAMP_PATTERN = re.compile(r"^\s*>?\s*\*\*采集时间\*\*:\s*(.+)$")
REPORT_UPTIME_PATTERN = re.compile(r"^\s*>?\s*\*\*系统运行时长\*\*:\s*(.+)$")
HEADING_PATTERN = re.compile(r"^(#{2,6})\s+(.+?)\s*$")

TIMESTAMP_PATTERN = re.compile(
    r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?)"
)
SEPARATOR_CELL_PATTERN = re.compile(r"^:?-{3,}:?$")

CPU_KEYWORDS = ("cpu", "处理器")
MEMORY_KEYWORDS = ("内存", "memory", "mem")
DISK_KEYWORDS = ("磁盘", "disk", "根分区", "系统盘", "rootfs")

CPU_VALUE_PATTERN = re.compile(r"(?:CPU|cpu|处理器)[^%\n]{0,20}?(\d+(?:\.\d+)?)%")
MEMORY_VALUE_PATTERN = re.compile(r"(?:内存|memory|MEM|mem)[^%\n]{0,20}?(\d+(?:\.\d+)?)%")
DISK_VALUE_PATTERN = re.compile(r"(?:磁盘|disk|根分区|系统盘|rootfs)[^%\n]{0,20}?(\d+(?:\.\d+)?)%")
UPTIME_PATTERN = re.compile(
    r"(?:uptime|连续运行|运行时长)[^0-9]{0,10}(\d+(?:\.\d+)?)\s*(天|小时|分钟|分|d|day|days|h|hour|hours|m|min|mins)?",
    re.IGNORECASE,
)
RAW_DURATION_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(天|小时|分钟|分|d|day|days|h|hour|hours|m|min|mins)$",
    re.IGNORECASE,
)
COMPOSITE_DURATION_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(天|小时|分钟|分|d|day|days|h|hour|hours|m|min|mins)",
    re.IGNORECASE,
)
RESTART_SUBJECT_PATTERN = re.compile(
    r"([A-Za-z0-9_.-]+(?:\.service|\.container)?)\s*(?:发生|出现|近[一两三四五六七八九十0-9]+天)?\s*(?:重启|restarting|unhealthy|异常退出|宕机|reboot)",
    re.IGNORECASE,
)
PANIC_SUBJECT_PATTERN = re.compile(
    r"(?:^|[ ,|:])([A-Za-z0-9_.-]+)(?:\([^)]*\))?\s+panic\b",
    re.IGNORECASE,
)
COUNT_PATTERN = re.compile(r"(\d+)\s*(?:次|times?|restarts?)", re.IGNORECASE)
CPU_COMPOSITE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)%\s*(?:us|user)\s*\+\s*(\d+(?:\.\d+)?)%\s*(?:sy|sys)", re.IGNORECASE)
SKIP_EVENT_TOKENS = ("风险", "概率", "建议", "趋势", "说明", "含义", "根因", "影响", "修复", "排查", "关注项")
IGNORED_SECTION_TOKENS = ("趋势预测", "建议措施", "历史关联")
ABNORMAL_EXIT_KEYWORDS = ("异常退出", "abnormal exit", "fatal", "exit code", "panic崩溃")
UNCLEAN_SHUTDOWN_KEYWORDS = ("非正常恢复", "非正常关机", "unclean shutdown", "无graceful shutdown", "未正常关闭")
NEGATED_EVENT_PATTERNS = (
    "未发现重启",
    "未发现 panic",
    "未发现panic",
    "未发现异常退出",
    "未发现非正常关闭",
    "未见重启",
    "未见 panic",
    "未见panic",
    "未发生重启",
    "无 oom / panic",
    "无 oom/panic",
    "无主动看门狗触发记录",
)


class TrendInputBuildError(Exception):
    pass


def build_trend_input_from_markdown(
    report_path: Path,
    *,
    run_id: str,
    generated_at: str,
) -> TrendInputV1:
    if not report_path.exists():
        raise TrendInputBuildError("Trend source markdown does not exist.")
    if report_path.suffix.lower() != ".md":
        raise TrendInputBuildError("Only cleaned status-analysis markdown reports are supported.")

    text = report_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    report_timestamp = _extract_report_timestamp(lines)
    table_blocks, table_line_numbers = _collect_markdown_tables(lines)

    cpu_samples: list[TrendMetricSample] = []
    memory_samples: list[TrendMetricSample] = []
    disk_samples: list[TrendMetricSample] = []
    uptime_samples: list[TrendUptimeSample] = []
    restart_events: list[TrendRestartEvent] = []
    warnings: list[str] = []
    time_points: set[str] = set()

    for block in table_blocks:
        extracted = _extract_samples_from_table(
            block["lines"],
            section_name=block["section_name"],
            report_timestamp=report_timestamp,
        )
        cpu_samples.extend(extracted["cpu"])
        memory_samples.extend(extracted["memory"])
        disk_samples.extend(extracted["disk"])
        uptime_samples.extend(extracted["uptime"])
        restart_events.extend(extracted["events"])

    if report_timestamp is not None:
        report_uptime_seconds = _extract_report_uptime_seconds(lines)
        if report_uptime_seconds is not None:
            uptime_samples.append(
                TrendUptimeSample(
                    timestamp=report_timestamp,
                    uptime_seconds=report_uptime_seconds,
                    source_excerpt="系统运行时长元数据",
                )
            )

    current_section: str | None = None
    in_code_block = False
    for index, raw_line in enumerate(lines, start=1):
        if raw_line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if index in table_line_numbers:
            continue
        line = raw_line.strip()
        if not line or line.startswith("#"):
            if heading_match := HEADING_PATTERN.match(line):
                current_section = heading_match.group(2).strip()
            continue

        if _should_ignore_section(current_section):
            continue

        timestamp = _extract_timestamp(line)
        if timestamp is not None:
            time_points.add(timestamp)
            if cpu_sample := _extract_metric_sample(line, timestamp=timestamp, pattern=CPU_VALUE_PATTERN):
                cpu_samples.append(cpu_sample)
            if memory_sample := _extract_metric_sample(line, timestamp=timestamp, pattern=MEMORY_VALUE_PATTERN):
                memory_samples.append(memory_sample)
            if disk_sample := _extract_metric_sample(line, timestamp=timestamp, pattern=DISK_VALUE_PATTERN):
                disk_samples.append(disk_sample)
            if uptime_sample := _extract_uptime_sample(line, timestamp=timestamp):
                uptime_samples.append(uptime_sample)

        restart_events.extend(
            _extract_stability_events(
                line,
                timestamp=timestamp,
                section_name=current_section,
            )
        )

    cpu_samples = _dedupe_metric_samples(cpu_samples)
    memory_samples = _dedupe_metric_samples(memory_samples)
    disk_samples = _dedupe_metric_samples(disk_samples)
    uptime_samples = _dedupe_uptime_samples(uptime_samples)
    restart_events = _dedupe_restart_events(restart_events)
    fault_chains = _build_fault_chains(restart_events)
    event_counts = _summarize_event_counts(fault_chains)
    time_points.update(sample.timestamp for sample in cpu_samples)
    time_points.update(sample.timestamp for sample in memory_samples)
    time_points.update(sample.timestamp for sample in disk_samples)
    time_points.update(sample.timestamp for sample in uptime_samples)

    if not any([cpu_samples, memory_samples, disk_samples, uptime_samples, restart_events]):
        raise TrendInputBuildError(
            "The markdown does not contain parsable cleaned status-analysis time points or events."
        )

    if len(cpu_samples) < 2:
        warnings.append("CPU 历史点少于 2 个，第一阶段不会生成 CPU 趋势图。")
    if len(memory_samples) < 2:
        warnings.append("内存历史点少于 2 个，第一阶段不会生成内存趋势图。")
    if len(disk_samples) < 2:
        warnings.append("磁盘历史点少于 2 个，第一阶段不会生成磁盘趋势图。")

    data_quality = _resolve_data_quality(
        cpu_count=len(cpu_samples),
        memory_count=len(memory_samples),
        disk_count=len(disk_samples),
        stability_count=len(uptime_samples) + len(restart_events),
    )

    return TrendInputV1(
        run_id=run_id,
        generated_at=generated_at,
        source=TrendInputSource(path=report_path.as_posix()),
        parse_summary=TrendParseSummary(
            warnings=warnings,
            time_points_detected=len(time_points),
            data_quality=data_quality,
        ),
        metrics=TrendInputMetrics(
            cpu=TrendMetricSeries(samples=sorted(cpu_samples, key=lambda sample: sample.timestamp)),
            memory=TrendMetricSeries(samples=sorted(memory_samples, key=lambda sample: sample.timestamp)),
            disk=TrendMetricSeries(samples=sorted(disk_samples, key=lambda sample: sample.timestamp)),
        ),
        stability=TrendStabilityInput(
            uptime_samples=sorted(uptime_samples, key=lambda sample: sample.timestamp),
            restart_events=restart_events,
            event_counts=event_counts,
            fault_chains=fault_chains,
        ),
    )


def persist_trend_input(trend_input: TrendInputV1, target_path: Path) -> None:
    target_path.write_text(trend_input.model_dump_json(indent=2), encoding="utf-8")


def _collect_markdown_tables(lines: list[str]) -> tuple[list[dict[str, object]], set[int]]:
    blocks: list[dict[str, object]] = []
    table_line_numbers: set[int] = set()
    current_block: list[str] = []
    current_line_numbers: list[int] = []
    current_section: str | None = None
    for index, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if heading_match := HEADING_PATTERN.match(line):
            current_section = heading_match.group(2).strip()
        if line.count("|") >= 2:
            current_block.append(line)
            current_line_numbers.append(index)
            continue
        if current_block:
            blocks.append({"lines": current_block, "section_name": current_section})
            table_line_numbers.update(current_line_numbers)
            current_block = []
            current_line_numbers = []
    if current_block:
        blocks.append({"lines": current_block, "section_name": current_section})
        table_line_numbers.update(current_line_numbers)
    return blocks, table_line_numbers


def _extract_samples_from_table(
    block: list[str],
    *,
    section_name: str | None,
    report_timestamp: str | None,
) -> dict[str, list]:
    rows = [_split_table_row(line) for line in block]
    rows = [row for row in rows if row]
    if len(rows) < 2:
        return {"cpu": [], "memory": [], "disk": [], "uptime": [], "events": []}

    header = rows[0]
    data_rows = [row for row in rows[1:] if not _is_separator_row(row)]

    if _looks_like_snapshot_metric_table(header, section_name=section_name):
        return _extract_snapshot_samples_from_table(
            data_rows,
            report_timestamp=report_timestamp,
            section_name=section_name,
        )

    if _looks_like_uptime_snapshot_table(header, section_name=section_name):
        return _extract_uptime_snapshot_from_table(
            data_rows,
            report_timestamp=report_timestamp,
        )

    if _looks_like_event_timeline_table(header):
        return _extract_event_samples_from_table(data_rows)

    if _looks_like_incident_table(header):
        return _extract_incident_samples_from_table(header, data_rows)

    timestamp_index = _find_timestamp_column(header)
    if timestamp_index is None:
        return {"cpu": [], "memory": [], "disk": [], "uptime": [], "events": []}

    metric_indices = {
        "cpu": _find_metric_column(header, CPU_KEYWORDS),
        "memory": _find_metric_column(header, MEMORY_KEYWORDS),
        "disk": _find_metric_column(header, DISK_KEYWORDS),
        "uptime": _find_uptime_column(header),
    }
    event_index = _find_event_column(header)

    extracted = {"cpu": [], "memory": [], "disk": [], "uptime": [], "events": []}
    for row in data_rows:
        if timestamp_index >= len(row):
            continue
        timestamp = _normalize_timestamp(row[timestamp_index])
        if timestamp is None:
            continue
        for metric_name in ("cpu", "memory", "disk"):
            metric_index = metric_indices[metric_name]
            if metric_index is None or metric_index >= len(row):
                continue
            percentage = _extract_percentage(row[metric_index])
            if percentage is None:
                continue
            extracted[metric_name].append(
                TrendMetricSample(
                    timestamp=timestamp,
                    value=percentage,
                    source_excerpt=" | ".join(cell for cell in row if cell),
                )
            )
        uptime_index = metric_indices["uptime"]
        if uptime_index is not None and uptime_index < len(row):
            uptime_seconds = _parse_uptime_to_seconds(row[uptime_index])
            if uptime_seconds is not None:
                extracted["uptime"].append(
                    TrendUptimeSample(
                        timestamp=timestamp,
                        uptime_seconds=uptime_seconds,
                        source_excerpt=" | ".join(cell for cell in row if cell),
                    )
                )
        if event_index is not None and event_index < len(row):
            if event := _extract_restart_event(
                row[event_index],
                timestamp=timestamp,
                section_name=None,
            ):
                extracted["events"].append(event)
    return extracted


def _extract_snapshot_samples_from_table(
    rows: list[list[str]],
    *,
    report_timestamp: str | None,
    section_name: str | None,
) -> dict[str, list]:
    extracted = {"cpu": [], "memory": [], "disk": [], "uptime": [], "events": []}
    if report_timestamp is None:
        return extracted

    section_lower = (section_name or "").lower()
    if any(token in section_lower for token in ["cpu", "处理器"]):
        cpu_user = None
        cpu_system = None
        for row in rows:
            if len(row) < 2:
                continue
            metric_name = row[0]
            value_text = " | ".join(cell for cell in row[1:] if cell)
            if any(token in metric_name.lower() for token in ["用户态", "(us)", " us"]):
                cpu_user = _extract_percentage(value_text)
            elif any(token in metric_name.lower() for token in ["系统态", "(sy)", " sy"]):
                cpu_system = _extract_percentage(value_text)
            else:
                metric_value = _extract_snapshot_metric_value(metric_name, value_text)
                if metric_value is not None:
                    extracted["cpu"].append(
                        TrendMetricSample(
                            timestamp=report_timestamp,
                            value=metric_value,
                            source_excerpt=" | ".join(cell for cell in row if cell),
                        )
                    )
        if cpu_user is not None or cpu_system is not None:
            extracted["cpu"] = [
                TrendMetricSample(
                    timestamp=report_timestamp,
                    value=round((cpu_user or 0.0) + (cpu_system or 0.0), 2),
                    source_excerpt="CPU snapshot table aggregate (us + sy)",
                )
            ]
        return extracted

    for row in rows:
        if len(row) < 2:
            continue
        metric_name = row[0]
        value_text = " | ".join(cell for cell in row[1:] if cell)
        if "swap" in metric_name.lower():
            continue
        metric_value = _extract_snapshot_metric_value(metric_name, value_text)
        if metric_value is None:
            continue
        sample = TrendMetricSample(
            timestamp=report_timestamp,
            value=metric_value,
            source_excerpt=" | ".join(cell for cell in row if cell),
        )
        normalized_metric_name = metric_name.lower()
        if any(token in normalized_metric_name for token in ["cpu", "处理器"]):
            extracted["cpu"].append(sample)
        elif any(token in normalized_metric_name for token in ["已用", "使用率", "used"]) and any(
            token in section_lower for token in ["内存", "memory", "mem"]
        ):
            extracted["memory"].append(sample)
        elif any(token in normalized_metric_name for token in ["使用率", "used"]) and any(
            token in section_lower for token in ["磁盘", "disk", "系统盘", "数据盘"]
        ):
            extracted["disk"].append(sample)
        elif any(token in normalized_metric_name for token in ["内存", "memory", "mem"]):
            extracted["memory"].append(sample)
        elif any(token in normalized_metric_name for token in ["磁盘", "disk", "根分区", "系统盘", "rootfs"]):
            extracted["disk"].append(sample)
    return extracted


def _extract_uptime_snapshot_from_table(
    rows: list[list[str]],
    *,
    report_timestamp: str | None,
) -> dict[str, list]:
    extracted = {"cpu": [], "memory": [], "disk": [], "uptime": [], "events": []}
    if report_timestamp is None:
        return extracted

    for row in rows:
        if len(row) < 2:
            continue
        metric_name = row[0].lower()
        value_text = " | ".join(cell for cell in row[1:] if cell)
        if "uptime" in metric_name or "运行时长" in metric_name:
            uptime_seconds = _parse_uptime_to_seconds(value_text)
            if uptime_seconds is not None:
                extracted["uptime"].append(
                    TrendUptimeSample(
                        timestamp=report_timestamp,
                        uptime_seconds=uptime_seconds,
                        source_excerpt=" | ".join(cell for cell in row if cell),
                    )
                )
    return extracted


def _extract_event_samples_from_table(rows: list[list[str]]) -> dict[str, list]:
    extracted = {"cpu": [], "memory": [], "disk": [], "uptime": [], "events": []}
    for row in rows:
        if len(row) < 2:
            continue
        timestamp = _normalize_timestamp(row[0])
        if timestamp is None:
            continue
        event_text = " | ".join(cell for cell in row[1:] if cell)
        extracted["events"].extend(
            _extract_stability_events(
                event_text,
                timestamp=timestamp,
                section_name="timeline-table",
            )
        )
    return extracted


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    if not stripped:
        return []
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator_row(row: list[str]) -> bool:
    return all(SEPARATOR_CELL_PATTERN.match(cell) for cell in row)


def _find_timestamp_column(header: list[str]) -> int | None:
    for index, cell in enumerate(header):
        normalized = cell.strip().lower()
        if any(token in normalized for token in ["时间", "日期", "timestamp", "time", "采样"]):
            return index
    return None


def _looks_like_snapshot_metric_table(header: list[str], *, section_name: str | None) -> bool:
    if section_name is None:
        return False
    section_lower = section_name.lower()
    if not any(token in section_lower for token in ["系统资源状态", "资源快照", "资源状态", "cpu", "内存", "磁盘", "处理器"]):
        return False
    normalized_header = [cell.strip().lower() for cell in header]
    return (
        len(normalized_header) >= 2
        and normalized_header[0] in {"指标", "metric"}
        and normalized_header[1] in {"数值", "值", "value", "采集快照值"}
    )


def _looks_like_uptime_snapshot_table(header: list[str], *, section_name: str | None) -> bool:
    if section_name is None:
        return False
    if not any(token in section_name.lower() for token in ["uptime", "运行时长"]):
        return False
    normalized_header = [cell.strip().lower() for cell in header]
    return (
        len(normalized_header) >= 2
        and normalized_header[0] in {"指标", "metric"}
        and normalized_header[1] in {"值", "数值", "value"}
    )


def _looks_like_event_timeline_table(header: list[str]) -> bool:
    normalized_header = [cell.strip().lower() for cell in header]
    return len(normalized_header) >= 2 and normalized_header[0] in {"日期", "时间", "date", "time"} and any(
        token in normalized_header[1] for token in ["事件", "event"]
    )


def _looks_like_incident_table(header: list[str]) -> bool:
    normalized_header = [cell.strip().lower() for cell in header]
    has_time = any(cell in {"时间", "日期", "time", "date"} for cell in normalized_header)
    has_detail = any(
        any(token in cell for token in ["详情", "detail", "事件", "类型", "组件", "component"])
        for cell in normalized_header
    )
    return has_time and has_detail


def _extract_incident_samples_from_table(header: list[str], rows: list[list[str]]) -> dict[str, list]:
    extracted = {"cpu": [], "memory": [], "disk": [], "uptime": [], "events": []}
    timestamp_index = _find_timestamp_column(header)
    if timestamp_index is None:
        return extracted
    normalized_header = [cell.strip().lower() for cell in header]

    for row in rows:
        if timestamp_index >= len(row):
            continue
        timestamp = _normalize_timestamp(row[timestamp_index])
        if timestamp is None:
            continue
        event_text = " | ".join(
            cell
            for index, cell in enumerate(row)
            if cell
            and index != timestamp_index
            and normalized_header[index] not in {"编号", "id", "序号"}
        )
        extracted["events"].extend(
            _extract_stability_events(
                event_text,
                timestamp=timestamp,
                section_name="incident-table",
            )
        )
    return extracted


def _find_metric_column(header: list[str], keywords: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(header):
        normalized = cell.strip().lower()
        if any(keyword in normalized for keyword in keywords):
            return index
    return None


def _find_uptime_column(header: list[str]) -> int | None:
    for index, cell in enumerate(header):
        normalized = cell.strip().lower()
        if "uptime" in normalized or "运行时长" in normalized or "连续运行" in normalized:
            return index
    return None


def _find_event_column(header: list[str]) -> int | None:
    for index, cell in enumerate(header):
        normalized = cell.strip().lower()
        if any(token in normalized for token in ["事件", "异常", "稳定", "重启", "告警"]):
            return index
    return None


def _extract_timestamp(text: str) -> str | None:
    match = TIMESTAMP_PATTERN.search(text)
    if match is None:
        return None
    return _normalize_timestamp(match.group(1))


def _normalize_timestamp(raw_value: str) -> str | None:
    candidate = raw_value.strip().replace("/", "-")
    candidate = re.sub(r"\s+(?:UTC|GMT|CST|UTC[+-]\d{1,2}(?::\d{2})?)$", "", candidate, flags=re.IGNORECASE)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(candidate, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
        return parsed.isoformat().replace("+00:00", "Z")
    return None


def _extract_metric_sample(text: str, *, timestamp: str, pattern: re.Pattern[str]) -> TrendMetricSample | None:
    match = pattern.search(text)
    if match is None:
        return None
    return TrendMetricSample(
        timestamp=timestamp,
        value=float(match.group(1)),
        source_excerpt=" ".join(text.split()),
    )


def _extract_uptime_sample(text: str, *, timestamp: str) -> TrendUptimeSample | None:
    uptime_seconds = _parse_uptime_to_seconds(text)
    if uptime_seconds is None:
        return None
    return TrendUptimeSample(
        timestamp=timestamp,
        uptime_seconds=uptime_seconds,
        source_excerpt=" ".join(text.split()),
    )


def _parse_uptime_to_seconds(text: str) -> int | None:
    composite_matches = COMPOSITE_DURATION_PATTERN.findall(text)
    if len(composite_matches) >= 2:
        total_seconds = 0
        for raw_value, raw_unit in composite_matches:
            total_seconds += _duration_part_to_seconds(float(raw_value), raw_unit)
        return total_seconds

    match = UPTIME_PATTERN.search(text)
    if match is None:
        match = RAW_DURATION_PATTERN.search(text.strip())
    if match is None:
        return None
    return _duration_part_to_seconds(float(match.group(1)), match.group(2) or "天")


def _duration_part_to_seconds(value: float, raw_unit: str) -> int:
    unit = raw_unit.lower()
    multiplier = 24 * 3600
    if unit in {"小时", "h", "hour", "hours"}:
        multiplier = 3600
    elif unit in {"分钟", "分", "m", "min", "mins"}:
        multiplier = 60
    return int(value * multiplier)


def _extract_stability_events(
    text: str,
    *,
    timestamp: str | None,
    section_name: str | None,
) -> list[TrendRestartEvent]:
    normalized = " ".join(text.split())
    lowered = normalized.lower()
    if timestamp is None and any(token in normalized for token in SKIP_EVENT_TOKENS):
        return []
    if section_name is not None and _should_ignore_section(section_name):
        return []
    if any(pattern in lowered for pattern in NEGATED_EVENT_PATTERNS):
        return []
    if timestamp is None and re.match(r"^\d+\.\s", normalized):
        return []
    if timestamp is None and "重启历史" in normalized:
        return []

    subject = _extract_event_subject(normalized)
    count_match = COUNT_PATTERN.search(normalized)
    count = int(count_match.group(1)) if count_match else 1

    event_types: list[str] = []
    if "panic" in lowered:
        event_types.append("panic")
    if any(keyword in lowered for keyword in ("restarting", "反复重启")):
        event_types.append("restarting")
    elif "unhealthy" in lowered or "健康检查失败" in normalized:
        event_types.append("unhealthy")
    elif "宕机" in normalized or "reboot" in lowered:
        event_types.append("reboot")
    elif "重启" in normalized:
        event_types.append("restart")

    if any(keyword in lowered for keyword in ABNORMAL_EXIT_KEYWORDS):
        event_types.append("abnormal_exit")
    if any(keyword in lowered for keyword in UNCLEAN_SHUTDOWN_KEYWORDS):
        event_types.append("unclean_shutdown")

    if not event_types:
        return []
    if timestamp is None and count_match is None:
        event_types = [
            event_type
            for event_type in event_types
            if event_type not in {"restart", "reboot", "restarting"}
        ]
        if not event_types:
            return []
    if timestamp is None and count_match is None and subject is None:
        return []

    results: list[TrendRestartEvent] = []
    for event_type in dict.fromkeys(event_types):
        results.append(
            TrendRestartEvent(
                timestamp=timestamp,
                subject=subject,
                event_type=event_type,
                count=count,
                source_excerpt=normalized,
            )
        )
    return results


def _extract_event_subject(text: str) -> str | None:
    if panic_match := PANIC_SUBJECT_PATTERN.search(text):
        return _sanitize_event_subject(panic_match.group(1))
    if restart_match := RESTART_SUBJECT_PATTERN.search(text):
        return _sanitize_event_subject(restart_match.group(1))
    return None


def _sanitize_event_subject(subject: str | None) -> str | None:
    if subject is None:
        return None
    candidate = subject.strip().strip("-").strip()
    if not candidate:
        return None
    if re.fullmatch(r"\d+\.", candidate):
        return None
    if re.fullmatch(r"[A-Z]-?\d+", candidate):
        return None
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", candidate):
        return None
    if candidate in {"-", "—"}:
        return None
    if candidate.upper() in {"PG"}:
        return None
    return candidate


def _extract_percentage(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)%", text)
    if match is None:
        return None
    return float(match.group(1))


def _extract_snapshot_metric_value(metric_name: str, value_text: str) -> float | None:
    normalized_metric_name = metric_name.lower()
    if any(token in normalized_metric_name for token in ["cpu", "处理器"]):
        if composite_match := CPU_COMPOSITE_PATTERN.search(value_text):
            return round(float(composite_match.group(1)) + float(composite_match.group(2)), 2)
    return _extract_percentage(value_text)


def _extract_report_timestamp(lines: list[str]) -> str | None:
    for line in lines:
        if match := REPORT_TIMESTAMP_PATTERN.search(line.strip()):
            return _normalize_timestamp(match.group(1).strip())
    return None


def _extract_report_uptime_seconds(lines: list[str]) -> int | None:
    for line in lines:
        if match := REPORT_UPTIME_PATTERN.search(line.strip()):
            return _parse_uptime_to_seconds(match.group(1).strip())
    return None


def _should_ignore_section(section_name: str | None) -> bool:
    if section_name is None:
        return False
    return any(token in section_name for token in IGNORED_SECTION_TOKENS)


def _dedupe_metric_samples(samples: list[TrendMetricSample]) -> list[TrendMetricSample]:
    exact_seen: set[tuple[str, float, str]] = set()
    exact_result: list[TrendMetricSample] = []
    for sample in samples:
        key = (sample.timestamp, sample.value, sample.source_excerpt)
        if key in exact_seen:
            continue
        exact_seen.add(key)
        exact_result.append(sample)

    by_bucket: dict[tuple[str, float], TrendMetricSample] = {}
    result: list[TrendMetricSample] = []
    for sample in exact_result:
        bucket = _metric_sample_bucket(sample.timestamp)
        if bucket is None:
            result.append(sample)
            continue
        key = (bucket, sample.value)
        existing = by_bucket.get(key)
        if existing is None:
            by_bucket[key] = sample
            result.append(sample)
            continue
        if not _should_collapse_same_bucket_metric_sample(existing, sample):
            result.append(sample)
            continue
        preferred = _prefer_canonical_resource_history_sample(existing, sample)
        if preferred is existing:
            continue
        by_bucket[key] = preferred
        result[result.index(existing)] = preferred
    return result


def _metric_sample_bucket(timestamp: str) -> str | None:
    parsed = _parse_trend_timestamp(timestamp)
    if parsed is None:
        return None
    bucket_hour = (parsed.hour // 12) * 12
    return parsed.replace(hour=bucket_hour, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_trend_timestamp(timestamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _should_collapse_same_bucket_metric_sample(
    first: TrendMetricSample,
    second: TrendMetricSample,
) -> bool:
    return _is_canonical_resource_history_sample(first) or _is_canonical_resource_history_sample(second)


def _prefer_canonical_resource_history_sample(
    first: TrendMetricSample,
    second: TrendMetricSample,
) -> TrendMetricSample:
    if _is_canonical_resource_history_sample(first):
        return first
    if _is_canonical_resource_history_sample(second):
        return second
    return first


def _is_canonical_resource_history_sample(sample: TrendMetricSample) -> bool:
    return "resources/resource_history.csv" in sample.source_excerpt


def _dedupe_uptime_samples(samples: list[TrendUptimeSample]) -> list[TrendUptimeSample]:
    seen: set[tuple[str, int, str]] = set()
    result: list[TrendUptimeSample] = []
    for sample in samples:
        key = (sample.timestamp, sample.uptime_seconds, sample.source_excerpt)
        if key in seen:
            continue
        seen.add(key)
        result.append(sample)
    return result


def _dedupe_restart_events(events: list[TrendRestartEvent]) -> list[TrendRestartEvent]:
    seen: set[tuple[str | None, str | None, str, int, str]] = set()
    result: list[TrendRestartEvent] = []
    for event in events:
        key = (event.timestamp, event.subject, event.event_type, event.count, event.source_excerpt)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def _build_fault_chains(events: list[TrendRestartEvent]) -> list[TrendFaultChain]:
    grouped: dict[tuple[str | None, str | None], list[TrendRestartEvent]] = {}
    for event in events:
        window = event.timestamp[:10] if event.timestamp else None
        subject = event.subject or "system"
        grouped.setdefault((window, subject), []).append(event)

    fault_chains: list[TrendFaultChain] = []
    for (_, subject), chain_events in sorted(
        grouped.items(),
        key=lambda item: ((item[0][0] or "9999-99-99"), item[0][1] or "system"),
    ):
        ordered = sorted(
            chain_events,
            key=lambda event: (event.timestamp or "9999-99-99T99:99:99Z", event.event_type),
        )
        counts = _summarize_event_counts_from_events(ordered)
        window_start = ordered[0].timestamp
        window_end = ordered[-1].timestamp
        event_types = list(dict.fromkeys(event.event_type for event in ordered))
        evidence = list(dict.fromkeys(event.source_excerpt for event in ordered))[:3]
        fault_chains.append(
            TrendFaultChain(
                subject=None if subject == "system" else subject,
                window_start=window_start,
                window_end=window_end,
                event_types=event_types,
                event_counts=counts,
                event_count=sum(counts.model_dump().values()),
                summary=_build_fault_chain_summary(
                    subject=None if subject == "system" else subject,
                    counts=counts,
                    window_start=window_start,
                ),
                evidence=evidence,
            )
        )
    return fault_chains


def _summarize_event_counts(fault_chains: list[TrendFaultChain]) -> TrendStabilityEventCounts:
    counts = TrendStabilityEventCounts()
    for chain in fault_chains:
        counts.restart_count += chain.event_counts.restart_count
        counts.panic_count += chain.event_counts.panic_count
        counts.abnormal_exit_count += chain.event_counts.abnormal_exit_count
        counts.unclean_shutdown_count += chain.event_counts.unclean_shutdown_count
    return counts


def _summarize_event_counts_from_events(events: list[TrendRestartEvent]) -> TrendStabilityEventCounts:
    restart_values = [
        event.count
        for event in events
        if event.event_type in {"restart", "reboot", "restarting"}
    ]
    panic_values = [event.count for event in events if event.event_type == "panic"]
    abnormal_exit_values = [event.count for event in events if event.event_type == "abnormal_exit"]
    unclean_shutdown_values = [event.count for event in events if event.event_type == "unclean_shutdown"]

    return TrendStabilityEventCounts(
        restart_count=max(restart_values, default=0),
        panic_count=max(panic_values, default=0),
        abnormal_exit_count=max(abnormal_exit_values, default=0),
        unclean_shutdown_count=max(unclean_shutdown_values, default=0),
    )


def _build_fault_chain_summary(
    *,
    subject: str | None,
    counts: TrendStabilityEventCounts,
    window_start: str | None,
) -> str:
    prefix = window_start[:10] if window_start else "未标注时间窗口"
    target = subject or "系统"
    parts: list[str] = []
    if counts.restart_count:
        parts.append(f"重启 {counts.restart_count} 次")
    if counts.panic_count:
        parts.append(f"panic {counts.panic_count} 次")
    if counts.abnormal_exit_count:
        parts.append(f"异常退出 {counts.abnormal_exit_count} 次")
    if counts.unclean_shutdown_count:
        parts.append(f"非正常关闭/恢复 {counts.unclean_shutdown_count} 次")
    return f"{prefix} {target} 故障链：{'，'.join(parts)}"


def _resolve_data_quality(*, cpu_count: int, memory_count: int, disk_count: int, stability_count: int) -> str:
    complete_metric_count = sum(1 for count in [cpu_count, memory_count, disk_count] if count >= 2)
    if complete_metric_count >= 2 and stability_count > 0:
        return "sufficient"
    if any(count > 0 for count in [cpu_count, memory_count, disk_count]) or stability_count > 0:
        return "partial"
    return "insufficient"
