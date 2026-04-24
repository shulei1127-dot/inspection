#!/usr/bin/env bash

set -euo pipefail

XRAY_HOME="${XRAY_HOME:-/data/x-ray}"
TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d%H%M%S)}"
OUTPUT_NAME="${OUTPUT_NAME:-xray-collector.${TIMESTAMP}}"
WORKDIR="${WORKDIR:-/tmp/${OUTPUT_NAME}}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)}"
HISTORY_WINDOW_DAYS="${HISTORY_WINDOW_DAYS:-30}"
HISTORY_BUCKET_HOURS="${HISTORY_BUCKET_HOURS:-12}"

CONTAINERS=(
  xray-nginx
  xray-deploy
  xray-web
  xray-image-tools
  xray-cpematch
  xray-link-mgmt
  xray-patcher-mgmt
  xray-wengine
  xray-skyeye-service
  xray-upgrader
  xray-rabbitmq
  xray-pgbouncer
  xray-gungnir
  xray-patcher-engine
  xray-data-warehouse
  xray-redis
  xray-link-engine
  xray-db
  xray-baseline
)

if [[ ! -x "${XRAY_HOME}/minion" ]]; then
  echo "ERROR: ${XRAY_HOME}/minion not found or not executable" >&2
  exit 1
fi

cleanup() {
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

BUNDLE_ROOT="${WORKDIR}/${OUTPUT_NAME}"
SYSTEM_DIR="${BUNDLE_ROOT}/system"
CONTAINERS_DIR="${BUNDLE_ROOT}/containers"
SYSTEM_LOG_DIR="${BUNDLE_ROOT}/system-logs"
RESOURCE_SNAPSHOT_DIR="${BUNDLE_ROOT}/resource-snapshots"
RESOURCE_DIR="${BUNDLE_ROOT}/resources"
RESOURCE_HISTORY_RAW_DIR="${RESOURCE_DIR}/history"
NETWORK_DIR="${BUNDLE_ROOT}/network"
XRAY_LOG_DIR="${BUNDLE_ROOT}/xray-logs"
MINION_LOG_DIR="${BUNDLE_ROOT}/minion-logs"
RAW_DIR="${BUNDLE_ROOT}/raw"
CONTAINER_LOG_DIR="${BUNDLE_ROOT}/container-logs"
METADATA_DIR="${BUNDLE_ROOT}/metadata"

mkdir -p \
  "${SYSTEM_DIR}" \
  "${CONTAINERS_DIR}" \
  "${SYSTEM_LOG_DIR}" \
  "${RESOURCE_SNAPSHOT_DIR}" \
  "${RESOURCE_DIR}" \
  "${RESOURCE_HISTORY_RAW_DIR}" \
  "${NETWORK_DIR}" \
  "${XRAY_LOG_DIR}" \
  "${MINION_LOG_DIR}" \
  "${RAW_DIR}" \
  "${CONTAINER_LOG_DIR}" \
  "${METADATA_DIR}"

run_capture() {
  local target="$1"
  shift
  {
    printf '# time: %s\n' "$(date '+%F %T %z')"
    printf '# cmd: %s\n\n' "$*"
  } >"${target}"
  if "$@" >>"${target}" 2>&1; then
    return 0
  fi
  {
    echo
    echo "[collector-note] command failed: $*"
  } >>"${target}"
}

run_shell_capture() {
  local target="$1"
  local shell_cmd="$2"
  {
    printf '# time: %s\n' "$(date '+%F %T %z')"
    printf '# cmd: %s\n\n' "${shell_cmd}"
  } >"${target}"
  if bash -lc "${shell_cmd}" >>"${target}" 2>&1; then
    return 0
  fi
  {
    echo
    echo "[collector-note] shell command failed: ${shell_cmd}"
  } >>"${target}"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

run_if_exists() {
  local target="$1"
  local cmd="$2"
  shift 2
  if command_exists "${cmd}"; then
    run_capture "${target}" "${cmd}" "$@"
  else
    {
      printf '# time: %s\n' "$(date '+%F %T %z')"
      printf '# cmd: %s %s\n\n' "${cmd}" "$*"
      printf 'command not found: %s\n' "${cmd}"
    } >"${target}"
  fi
}

choose_python() {
  if command_exists python3; then
    echo "python3"
    return 0
  fi
  if command_exists python; then
    echo "python"
    return 0
  fi
  return 1
}

first_ipv4() {
  ip -4 addr show scope global 2>/dev/null \
    | awk '/inet / {sub(/\/.*/, "", $2); if ($2 !~ /^127\./) {print $2; exit}}'
}

timezone_value() {
  timedatectl 2>/dev/null | awk -F': ' '/Time zone/ {print $2}' | awk '{print $1}'
}

last_boot_iso() {
  local started_at
  started_at="$(uptime -s 2>/dev/null || true)"
  if [[ -n "${started_at}" ]]; then
    date -u -d "${started_at}" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || true
  fi
}

machine_id_value() {
  "${XRAY_HOME}/minion" mgmt machineid 2>/dev/null \
    | awk -F': ' '/Machine ID:/ {print $2; exit}'
}

vuln_db_value() {
  local link_path="${XRAY_HOME}/container/media/gungnir/hyuna.dump"
  if [[ -L "${link_path}" || -e "${link_path}" ]]; then
    basename "$(readlink -f "${link_path}")"
  fi
}

collect_meta() {
  cat > "${BUNDLE_ROOT}/manifest.txt" <<EOF
collector=xray-report-bundle-v2
collected_at=$(date '+%F %T %z')
hostname=$(hostname 2>/dev/null || echo unknown)
xray_home=${XRAY_HOME}
output_name=${OUTPUT_NAME}
history_window_days=${HISTORY_WINDOW_DAYS}
history_bucket_hours=${HISTORY_BUCKET_HOURS}
EOF
}

collect_builtin_minion_report() {
  echo "[1/9] Running built-in minion collect..."
  pushd "${XRAY_HOME}" >/dev/null
  run_capture "${XRAY_LOG_DIR}/minion-collect-command.txt" ./minion collect
  local minion_report_path="${XRAY_HOME}/minion_report.gz"
  if [[ -f "${minion_report_path}" ]]; then
    cp "${minion_report_path}" "${RAW_DIR}/minion_report.gz"
    tar -xzf "${minion_report_path}" -C "${BUNDLE_ROOT}" || true
  else
    echo "[collector-note] minion collect did not produce ${minion_report_path}" >> "${XRAY_LOG_DIR}/minion-collect-command.txt"
  fi
  popd >/dev/null
}

collect_canonical_inputs() {
  echo "[2/9] Capturing canonical parser inputs..."
  local hostname_val ip_val timezone_val_local uptime_val last_boot_val os_pretty kernel_val
  hostname_val="$(hostname 2>/dev/null || true)"
  ip_val="$(first_ipv4 || true)"
  timezone_val_local="$(timezone_value || true)"
  uptime_val="$(awk '{print int($1)}' /proc/uptime 2>/dev/null || true)"
  last_boot_val="$(last_boot_iso || true)"
  os_pretty="$(hostnamectl 2>/dev/null | awk -F': ' '/Operating System/ {print $2; exit}' || true)"
  kernel_val="$(uname -r 2>/dev/null || true)"

  cat > "${SYSTEM_DIR}/system_info" <<EOF
hostname=${hostname_val}
ip=${ip_val}
timezone=${timezone_val_local}
uptime_seconds=${uptime_val}
last_boot_at=${last_boot_val}
pretty_name=${os_pretty}
kernel=${kernel_val}
EOF

  run_capture "${SYSTEM_DIR}/systemctl_status" systemctl list-units --type=service --all --no-pager
  run_capture "${CONTAINERS_DIR}/docker_ps" docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
}

collect_system_and_health() {
  echo "[3/9] Capturing system, health, and minion diagnostics..."
  run_if_exists "${SYSTEM_LOG_DIR}/hostnamectl.txt" hostnamectl
  run_if_exists "${SYSTEM_LOG_DIR}/timedatectl.txt" timedatectl
  run_if_exists "${SYSTEM_LOG_DIR}/uname.txt" uname -a
  run_if_exists "${SYSTEM_LOG_DIR}/uptime.txt" uptime
  run_if_exists "${SYSTEM_LOG_DIR}/list-boot.txt" journalctl --list-boot
  run_if_exists "${SYSTEM_LOG_DIR}/current-boot-300.log" journalctl -b 0 -n 300 --no-pager
  run_if_exists "${SYSTEM_LOG_DIR}/last-boot-300.log" journalctl -b -1 -n 300 --no-pager
  run_shell_capture "${SYSTEM_LOG_DIR}/dmesg-300.log" "dmesg -T 2>/dev/null | tail -n 300"
  run_if_exists "${SYSTEM_LOG_DIR}/systemctl-failed.txt" systemctl --failed --no-pager

  run_shell_capture "${XRAY_LOG_DIR}/minion-mgmt-health.txt" "cd '${XRAY_HOME}' && ./minion mgmt health"
  run_shell_capture "${XRAY_LOG_DIR}/minion-engine-health.txt" "cd '${XRAY_HOME}' && ./minion engine health"
  run_shell_capture "${XRAY_LOG_DIR}/minion-version.txt" "cd '${XRAY_HOME}' && ./minion version"

  run_if_exists "${MINION_LOG_DIR}/minion-systemd-300.log" journalctl -u minion -n 300 --no-pager
  run_if_exists "${MINION_LOG_DIR}/minion-service-status.txt" systemctl status minion --no-pager
}

collect_resource_snapshots() {
  echo "[4/9] Capturing current resource snapshots..."
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/lscpu.txt" lscpu
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/free-h.txt" free -h
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/df-hT.txt" df -hT
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/lsblk.txt" lsblk
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/mount.txt" mount
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/top.txt" top -b -n 1
  run_shell_capture "${RESOURCE_SNAPSHOT_DIR}/ps-cpu-top50.txt" "ps aux --sort=-%cpu | head -n 50"
  run_shell_capture "${RESOURCE_SNAPSHOT_DIR}/ps-mem-top50.txt" "ps aux --sort=-%mem | head -n 50"
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/vmstat.txt" vmstat 1 5
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/docker-stats.txt" docker stats --no-stream
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/docker-ps-a.txt" docker ps -a
}

collect_network_info() {
  echo "[5/9] Capturing network diagnostics..."
  run_if_exists "${NETWORK_DIR}/ip-addr.txt" ip -d addr
  run_if_exists "${NETWORK_DIR}/ip-route.txt" ip route
  run_if_exists "${NETWORK_DIR}/ss-tulpen.txt" ss -tulpen
  run_if_exists "${NETWORK_DIR}/netstat-ant.txt" netstat -ant
}

collect_container_logs() {
  echo "[6/9] Capturing per-container status and tail logs..."
  local container_name=""
  for container_name in "${CONTAINERS[@]}"; do
    run_shell_capture \
      "${CONTAINER_LOG_DIR}/${container_name}.status.txt" \
      "docker ps -a --filter 'name=^/${container_name}\$' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.RunningFor}}\t{{.Ports}}'"
    run_shell_capture \
      "${CONTAINER_LOG_DIR}/${container_name}.inspect.txt" \
      "docker inspect '${container_name}'"
    run_shell_capture \
      "${CONTAINER_LOG_DIR}/${container_name}.log" \
      "docker logs --tail 300 -t '${container_name}'"
  done
}

collect_xray_metadata() {
  echo "[7/9] Capturing xray-specific metadata..."
  local machine_id_val vuln_db_val
  machine_id_val="$(machine_id_value || true)"
  vuln_db_val="$(vuln_db_value || true)"

  {
    echo "machine_id=${machine_id_val}"
  } > "${XRAY_LOG_DIR}/machineid.txt"

  {
    echo "hyuna_dump=${vuln_db_val}"
  } > "${XRAY_LOG_DIR}/vuln-db-version.txt"

  cat > "${METADATA_DIR}/collection_info.txt" <<EOF
collector=xray-report-bundle-v2
collected_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
xray_home=${XRAY_HOME}
output_name=${OUTPUT_NAME}
machine_id=${machine_id_val}
hyuna_dump=${vuln_db_val}
history_window_days=${HISTORY_WINDOW_DAYS}
history_bucket_hours=${HISTORY_BUCKET_HOURS}
resource_history_csv=resources/resource_history.csv
resource_history_notes=resources/resource_history_notes.txt
EOF
}

collect_resource_history() {
  echo "[8/9] Extracting recent resource history for trend charts..."
  local cpu_raw="${RESOURCE_HISTORY_RAW_DIR}/sar-cpu.txt"
  local memory_raw="${RESOURCE_HISTORY_RAW_DIR}/sar-memory.txt"
  local disk_raw="${RESOURCE_HISTORY_RAW_DIR}/sar-disk.txt"
  local csv_path="${RESOURCE_DIR}/resource_history.csv"
  local notes_path="${RESOURCE_DIR}/resource_history_notes.txt"
  local python_bin

  printf 'timestamp,cpu,memory,disk\n' > "${csv_path}"
  : > "${notes_path}"

  if ! command_exists sar; then
    cat > "${notes_path}" <<EOF
history_source=unavailable
reason=sar_command_not_found
detail=未检测到 sysstat/sar，无法从主机导出最近 30 天资源历史，仅保留当前快照日志。
EOF
    return 0
  fi

  if ! ls /var/log/sa/sa[0-9][0-9] >/dev/null 2>&1 && ! ls /var/log/sysstat/sa[0-9][0-9] >/dev/null 2>&1; then
    cat > "${notes_path}" <<EOF
history_source=unavailable
reason=sa_files_not_found
detail=检测到 sar 命令，但未发现 /var/log/sa 或 /var/log/sysstat 下的历史采样文件。
EOF
    return 0
  fi

  run_shell_capture "${cpu_raw}" "LANG=C S_TIME_FORMAT=ISO sh -c 'for f in /var/log/sa/sa[0-9][0-9] /var/log/sysstat/sa[0-9][0-9]; do [ -r \"\$f\" ] || continue; echo \"### FILE: \$f\"; sar -u -f \"\$f\"; echo; done'"
  run_shell_capture "${memory_raw}" "LANG=C S_TIME_FORMAT=ISO sh -c 'for f in /var/log/sa/sa[0-9][0-9] /var/log/sysstat/sa[0-9][0-9]; do [ -r \"\$f\" ] || continue; echo \"### FILE: \$f\"; sar -r -f \"\$f\"; echo; done'"
  run_shell_capture "${disk_raw}" "LANG=C S_TIME_FORMAT=ISO sh -c 'for f in /var/log/sa/sa[0-9][0-9] /var/log/sysstat/sa[0-9][0-9]; do [ -r \"\$f\" ] || continue; echo \"### FILE: \$f\"; sar -F -f \"\$f\"; echo; done'"

  if ! python_bin="$(choose_python)"; then
    cat > "${notes_path}" <<EOF
history_source=raw_sar_only
reason=python_runtime_not_found
detail=已采集原始 sar 历史，但当前主机缺少 python/python3，未生成 canonical resources/resource_history.csv。
EOF
    return 0
  fi

  XRAY_HISTORY_CPU_RAW="${cpu_raw}" \
  XRAY_HISTORY_MEMORY_RAW="${memory_raw}" \
  XRAY_HISTORY_DISK_RAW="${disk_raw}" \
  XRAY_HISTORY_OUTPUT_CSV="${csv_path}" \
  XRAY_HISTORY_NOTES_PATH="${notes_path}" \
  XRAY_HISTORY_WINDOW_DAYS="${HISTORY_WINDOW_DAYS}" \
  XRAY_HISTORY_BUCKET_HOURS="${HISTORY_BUCKET_HOURS}" \
  "${python_bin}" - <<'PY'
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from pathlib import Path
import re


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
PREFERRED_MOUNTS = ("/data/x-ray", "/data", "/")


@dataclass(frozen=True)
class MetricPoint:
    timestamp: datetime
    value: float


def looks_like_datetime(tokens: list[str]) -> bool:
    return len(tokens) >= 2 and DATE_RE.match(tokens[0]) and TIME_RE.match(tokens[1])


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw or not NUMBER_RE.match(raw):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_timestamp(date_token: str, time_token: str, tzinfo) -> datetime | None:
    try:
        naive = datetime.strptime(f"{date_token} {time_token}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=tzinfo)


def bucket_timestamp(timestamp: datetime, bucket_hours: int) -> datetime:
    bucket_hour = (timestamp.hour // bucket_hours) * bucket_hours
    return timestamp.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)


def choose_mount(mount: str | None, used: float | None) -> tuple[int, float]:
    normalized = (mount or "").strip()
    for index, prefix in enumerate(PREFERRED_MOUNTS):
        if normalized == prefix:
            return (index, -(used or 0.0))
        if normalized.startswith(prefix + "/"):
            return (index + 10, -(used or 0.0))
    return (100, -(used or 0.0))


def parse_cpu_history(path: Path, reference_time: datetime, window_start: datetime) -> list[MetricPoint]:
    if not path.exists():
        return []
    header: list[str] | None = None
    points: list[MetricPoint] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Linux ") or line.startswith("Average:") or line.startswith("### FILE:"):
            continue
        tokens = re.split(r"\s+", line)
        if not looks_like_datetime(tokens):
            continue
        payload = tokens[2:]
        if "%idle" in payload:
            header = payload
            continue
        if header is None or len(payload) < len(header):
            continue
        row = dict(zip(header, payload))
        if str(row.get("CPU", "")).lower() != "all":
            continue
        idle = parse_float(row.get("%idle"))
        if idle is None:
            continue
        timestamp = parse_timestamp(tokens[0], tokens[1], reference_time.tzinfo)
        if timestamp is None or timestamp < window_start or timestamp > reference_time:
            continue
        points.append(MetricPoint(timestamp=timestamp, value=round(100.0 - idle, 1)))
    return points


def parse_memory_history(path: Path, reference_time: datetime, window_start: datetime) -> list[MetricPoint]:
    if not path.exists():
        return []
    header: list[str] | None = None
    points: list[MetricPoint] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Linux ") or line.startswith("Average:") or line.startswith("### FILE:"):
            continue
        tokens = re.split(r"\s+", line)
        if not looks_like_datetime(tokens):
            continue
        payload = tokens[2:]
        if "%memused" in payload:
            header = payload
            continue
        if header is None or len(payload) < len(header):
            continue
        row = dict(zip(header, payload))
        memused = parse_float(row.get("%memused"))
        if memused is None:
            continue
        timestamp = parse_timestamp(tokens[0], tokens[1], reference_time.tzinfo)
        if timestamp is None or timestamp < window_start or timestamp > reference_time:
            continue
        points.append(MetricPoint(timestamp=timestamp, value=round(memused, 1)))
    return points


def parse_disk_history(path: Path, reference_time: datetime, window_start: datetime) -> list[MetricPoint]:
    if not path.exists():
        return []
    header: list[str] | None = None
    by_timestamp: dict[datetime, tuple[tuple[int, float], float]] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Linux ") or line.startswith("Average:") or line.startswith("### FILE:"):
            continue
        tokens = re.split(r"\s+", line)
        if not looks_like_datetime(tokens):
            continue
        payload = tokens[2:]
        if "%fsused" in payload or "%ufsused" in payload:
            header = payload
            continue
        if header is None or len(payload) < len(header):
            continue
        row = dict(zip(header, payload))
        used = parse_float(row.get("%fsused") or row.get("%ufsused"))
        if used is None:
            continue
        mount = row.get("MOUNT") or row.get("FILESYSTEM") or row.get("MOUNTPOINT")
        timestamp = parse_timestamp(tokens[0], tokens[1], reference_time.tzinfo)
        if timestamp is None or timestamp < window_start or timestamp > reference_time:
            continue
        rank = choose_mount(mount, used)
        existing = by_timestamp.get(timestamp)
        if existing is None or rank < existing[0]:
            by_timestamp[timestamp] = (rank, round(used, 1))
    return [
        MetricPoint(timestamp=timestamp, value=value)
        for timestamp, (_, value) in sorted(by_timestamp.items(), key=lambda item: item[0])
    ]


def aggregate_rows(
    cpu_points: list[MetricPoint],
    memory_points: list[MetricPoint],
    disk_points: list[MetricPoint],
    bucket_hours: int,
) -> list[dict[str, str]]:
    buckets: dict[datetime, dict[str, list[float]]] = defaultdict(lambda: {"cpu": [], "memory": [], "disk": []})
    for metric_name, points in (
        ("cpu", cpu_points),
        ("memory", memory_points),
        ("disk", disk_points),
    ):
        for point in points:
            bucket = bucket_timestamp(point.timestamp, bucket_hours)
            buckets[bucket][metric_name].append(point.value)

    rows: list[dict[str, str]] = []
    for bucket in sorted(buckets):
        row = {"timestamp": bucket.isoformat(), "cpu": "", "memory": "", "disk": ""}
        for metric_name in ("cpu", "memory", "disk"):
            values = buckets[bucket][metric_name]
            if values:
                row[metric_name] = f"{sum(values) / len(values):.1f}"
        if any(row[name] for name in ("cpu", "memory", "disk")):
            rows.append(row)
    return rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as buffer:
        writer = csv.DictWriter(buffer, fieldnames=["timestamp", "cpu", "memory", "disk"])
        writer.writeheader()
        writer.writerows(rows)


def write_notes(
    notes_path: Path,
    *,
    rows: list[dict[str, str]],
    cpu_points: list[MetricPoint],
    memory_points: list[MetricPoint],
    disk_points: list[MetricPoint],
) -> None:
    history_source = "sysstat_sar" if any([cpu_points, memory_points, disk_points]) else "unavailable"
    reason = "ok" if rows else "no_usable_history_points"
    lines = [
        f"history_source={history_source}",
        f"reason={reason}",
        f"bucket_count={len(rows)}",
        f"cpu_points={len(cpu_points)}",
        f"memory_points={len(memory_points)}",
        f"disk_points={len(disk_points)}",
        "detail=最近 30 天历史点优先来自 sysstat/sar；若对应指标没有原始历史，则 CSV 中保留空列，不伪造数据。",
    ]
    notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


reference_time = datetime.now().astimezone()
window_days = int(os.environ.get("XRAY_HISTORY_WINDOW_DAYS", "30"))
bucket_hours = int(os.environ.get("XRAY_HISTORY_BUCKET_HOURS", "12"))
window_start = reference_time - timedelta(days=window_days)

cpu_raw = Path(os.environ["XRAY_HISTORY_CPU_RAW"])
memory_raw = Path(os.environ["XRAY_HISTORY_MEMORY_RAW"])
disk_raw = Path(os.environ["XRAY_HISTORY_DISK_RAW"])
output_csv = Path(os.environ["XRAY_HISTORY_OUTPUT_CSV"])
notes_path = Path(os.environ["XRAY_HISTORY_NOTES_PATH"])

cpu_points = parse_cpu_history(cpu_raw, reference_time, window_start)
memory_points = parse_memory_history(memory_raw, reference_time, window_start)
disk_points = parse_disk_history(disk_raw, reference_time, window_start)
rows = aggregate_rows(cpu_points, memory_points, disk_points, bucket_hours=bucket_hours)
write_csv(rows, output_csv)
write_notes(
    notes_path,
    rows=rows,
    cpu_points=cpu_points,
    memory_points=memory_points,
    disk_points=disk_points,
)
PY
}

package_archive() {
  echo "[9/9] Packing final archive..."
  mkdir -p "${OUTPUT_DIR}"
  local final_archive="${OUTPUT_DIR}/${OUTPUT_NAME}.tar.gz"
  tar -czf "${final_archive}" -C "${WORKDIR}" "${OUTPUT_NAME}"
  echo
  echo "Collection completed."
  echo "Final archive: ${final_archive}"
  echo "Bundle root inside archive: ${OUTPUT_NAME}/"
}

main() {
  collect_meta
  collect_builtin_minion_report
  collect_canonical_inputs
  collect_system_and_health
  collect_resource_snapshots
  collect_network_info
  collect_container_logs
  collect_xray_metadata
  collect_resource_history
  package_archive
}

main "$@"
