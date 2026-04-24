#!/usr/bin/env bash

set -u
set -o pipefail

# XRay report-oriented collector for inspection-report-platform.
#
# Goals:
# - produce a package that the current xray analyzer can already consume
# - keep report-friendly structured evidence for future parser improvements
# - avoid installing anything or requiring outbound network access

VERSION="4.1-project-compatible"
DEFAULT_XRAY_HOME="/data/x-ray"
XRAY_HOME="${XRAY_HOME:-${DEFAULT_XRAY_HOME}}"
ALLOW_FULL_SCAN="${ALLOW_FULL_SCAN:-true}"
INCLUDE_MINION_COLLECT="${INCLUDE_MINION_COLLECT:-true}"
CONTAINER_LOG_TAIL="${CONTAINER_LOG_TAIL:-300}"
DOCKER_EVENTS_SINCE="${DOCKER_EVENTS_SINCE:-7d}"
TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d%H%M%S)}"
OUTPUT_NAME="${OUTPUT_NAME:-xray-collector.${TIMESTAMP}}"
WORKDIR="${WORKDIR:-/tmp/${OUTPUT_NAME}}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp}"
ARCHIVE_PATH="${OUTPUT_DIR}/${OUTPUT_NAME}.tar.gz"

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

CORE_CONTAINERS=(xray-nginx xray-deploy xray-db xray-redis xray-wengine)
STORAGE_CONTAINERS=(xray-data-warehouse xray-rabbitmq xray-pgbouncer)
TASK_CONTAINERS=(xray-patcher-engine xray-link-engine xray-image-tools)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
  printf "%b[INFO]%b %s\n" "${GREEN}" "${NC}" "$*"
}

log_warn() {
  printf "%b[WARN]%b %s\n" "${YELLOW}" "${NC}" "$*" >&2
}

log_error() {
  printf "%b[ERROR]%b %s\n" "${RED}" "${NC}" "$*"
}

log_step() {
  printf "%b[STEP]%b %s\n" "${BLUE}" "${NC}" "$*"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

safe_mkdirs() {
  mkdir -p \
    "${BUNDLE_ROOT}" \
    "${SUMMARY_DIR}" \
    "${SYSTEM_DIR}" \
    "${CONTAINERS_DIR}" \
    "${SYSTEM_LOG_DIR}" \
    "${RESOURCE_SNAPSHOT_DIR}" \
    "${HEALTH_CHECKS_DIR}" \
    "${MINION_LOG_DIR}" \
    "${CONTAINER_LOG_DIR}" \
    "${NETWORK_DIR}" \
    "${XRAY_LOG_DIR}" \
    "${NODE_INFO_DIR}" \
    "${HEALTH_CHECK_DIR}" \
    "${RESOURCE_USAGE_DIR}" \
    "${CONTAINER_STATUS_DIR}" \
    "${CONTAINER_HISTORY_DIR}" \
    "${ANOMALY_DIR}" \
    "${MINION_COLLECT_DIR}" \
    "${METADATA_DIR}"
}

run_capture() {
  local target="$1"
  shift
  {
    printf '# time: %s\n' "$(date '+%F %T %z')"
    printf '# cmd: %s\n\n' "$*"
  } >"${target}"
  "$@" >>"${target}" 2>&1 || {
    {
      echo
      echo "[collector-note] command failed: $*"
    } >>"${target}"
    return 0
  }
}

run_shell_capture() {
  local target="$1"
  local shell_cmd="$2"
  {
    printf '# time: %s\n' "$(date '+%F %T %z')"
    printf '# cmd: %s\n\n' "${shell_cmd}"
  } >"${target}"
  bash -lc "${shell_cmd}" >>"${target}" 2>&1 || {
    {
      echo
      echo "[collector-note] shell command failed: ${shell_cmd}"
    } >>"${target}"
    return 0
  }
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

detect_xray_home() {
  if [[ -x "${XRAY_HOME}/minion" && -d "${XRAY_HOME}/container" ]]; then
    printf '%s\n' "${XRAY_HOME}"
    return 0
  fi

  for candidate in \
    /data/x-ray \
    /opt/x-ray \
    /usr/local/x-ray \
    /chaitin/x-ray \
    /home/x-ray \
    /root/x-ray
  do
    if [[ -x "${candidate}/minion" && -d "${candidate}/container" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  local found=""
  found="$(find /data /opt /usr/local /chaitin /home /root \
    -path '*/x-ray/container' \
    -type d \
    2>/dev/null \
    | head -n 1 \
    | xargs -r dirname 2>/dev/null || true)"
  if [[ -n "${found}" && -x "${found}/minion" ]]; then
    printf '%s\n' "${found}"
    return 0
  fi

  if [[ "${ALLOW_FULL_SCAN}" == "true" ]]; then
    log_warn "Common paths not found, falling back to full filesystem scan..."
    found="$(find / \
      -path '*/x-ray/container' \
      -type d \
      2>/dev/null \
      | head -n 1 \
      | xargs -r dirname 2>/dev/null || true)"
    if [[ -n "${found}" && -x "${found}/minion" ]]; then
      printf '%s\n' "${found}"
      return 0
    fi
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

cpu_model() {
  lscpu 2>/dev/null | awk -F': *' '/Model name/ {print $2; exit}'
}

cpu_cores() {
  nproc 2>/dev/null || lscpu 2>/dev/null | awk -F': *' '/^CPU\(s\)/ {print $2; exit}'
}

cpu_usage_percent() {
  local idle=""
  idle="$(top -bn1 2>/dev/null | awk '/Cpu\\(s\\)|%Cpu/ {gsub(/,/, " "); gsub(/%/, " "); for (i=1;i<=NF;i++) if ($i == "id") {print $(i-1); exit}}' | head -n 1)"
  if [[ -n "${idle}" ]]; then
    awk "BEGIN {printf \"%.1f\", 100 - ${idle}}"
    return 0
  fi
  echo ""
}

memory_info() {
  free -m 2>/dev/null | awk '/^Mem:/ {
    if ($2 > 0) {
      printf "%sM|%sM|%.1f", $3, $2, ($3 * 100 / $2)
    }
  }'
}

disk_info() {
  local target="/data"
  if [[ ! -d "${target}" ]]; then
    target="/"
  fi
  df -hP "${target}" 2>/dev/null | awk 'NR==2 {print $2"|"$3"|"$5"|"$6}'
}

machine_id_value() {
  "${INSTALL_DIR}/minion" mgmt machineid 2>/dev/null \
    | awk -F': *' '/Machine ID/ {print $2; exit}' \
    | tr -d ' '
}

vuln_db_value() {
  local link_path="${INSTALL_DIR}/container/media/gungnir/hyuna.dump"
  if [[ -L "${link_path}" || -e "${link_path}" ]]; then
    basename "$(readlink -f "${link_path}" 2>/dev/null || printf '%s' "${link_path}")"
  fi
}

docker_image_tag_like() {
  local pattern="$1"
  docker images --format '{{.Repository}} {{.Tag}}' 2>/dev/null \
    | awk -v pattern="${pattern}" '$1 ~ pattern {print $2; exit}'
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().rstrip("\n"), ensure_ascii=False))' 2>/dev/null \
    || sed 's/\\/\\\\/g; s/"/\\"/g; s/^/"/; s/$/"/'
}

priority_for_container() {
  local name="$1"
  for item in "${CORE_CONTAINERS[@]}"; do
    [[ "${item}" == "${name}" ]] && { echo "core"; return; }
  done
  for item in "${STORAGE_CONTAINERS[@]}"; do
    [[ "${item}" == "${name}" ]] && { echo "storage"; return; }
  done
  for item in "${TASK_CONTAINERS[@]}"; do
    [[ "${item}" == "${name}" ]] && { echo "task"; return; }
  done
  echo "auxiliary"
}

collect_manifest() {
  cat >"${BUNDLE_ROOT}/manifest.txt" <<EOF
collector=xray-collector-${VERSION}
collected_at=$(date '+%F %T %z')
hostname=$(hostname 2>/dev/null || echo unknown)
install_dir=${INSTALL_DIR}
archive_path=${ARCHIVE_PATH}
include_minion_collect=${INCLUDE_MINION_COLLECT}
docker_events_since=${DOCKER_EVENTS_SINCE}
container_log_tail=${CONTAINER_LOG_TAIL}
EOF

  cp "${BUNDLE_ROOT}/manifest.txt" "${METADATA_DIR}/collection_info.txt"
}

collect_node_info() {
  log_step "[1/8] Collecting node information..."

  HOSTNAME_VAL="$(hostname 2>/dev/null || true)"
  IP_VAL="$(first_ipv4 || true)"
  TIMEZONE_VAL="$(timezone_value || true)"
  UPTIME_VAL="$(awk '{print int($1)}' /proc/uptime 2>/dev/null || true)"
  LAST_BOOT_VAL="$(last_boot_iso || true)"
  OS_PRETTY="$(hostnamectl 2>/dev/null | awk -F': *' '/Operating System/ {print $2; exit}' || true)"
  if [[ -z "${OS_PRETTY}" && -f /etc/os-release ]]; then
    OS_PRETTY="$(awk -F= '/^PRETTY_NAME=/ {gsub(/"/, "", $2); print $2; exit}' /etc/os-release)"
  fi
  KERNEL_VAL="$(uname -r 2>/dev/null || true)"
  CPU_MODEL_VAL="$(cpu_model || true)"
  CPU_CORES_VAL="$(cpu_cores || true)"

  cat >"${SYSTEM_DIR}/system_info" <<EOF
hostname=${HOSTNAME_VAL}
ip=${IP_VAL}
timezone=${TIMEZONE_VAL}
uptime_seconds=${UPTIME_VAL}
last_boot_at=${LAST_BOOT_VAL}
pretty_name=${OS_PRETTY}
kernel=${KERNEL_VAL}
EOF

  cat >"${NODE_INFO_DIR}/system-info.txt" <<EOF
hostname=${HOSTNAME_VAL}
ip=${IP_VAL}
os=${OS_PRETTY}
kernel=${KERNEL_VAL}
timezone=${TIMEZONE_VAL}
uptime_seconds=${UPTIME_VAL}
last_boot_at=${LAST_BOOT_VAL}
cpu_model=${CPU_MODEL_VAL}
cpu_cores=${CPU_CORES_VAL}
EOF

  run_if_exists "${SYSTEM_LOG_DIR}/hostnamectl.txt" hostnamectl
  run_if_exists "${SYSTEM_LOG_DIR}/timedatectl.txt" timedatectl
  run_if_exists "${SYSTEM_LOG_DIR}/uname.txt" uname -a
  run_if_exists "${SYSTEM_LOG_DIR}/uptime.txt" uptime
  run_if_exists "${SYSTEM_LOG_DIR}/list-boot.txt" journalctl --list-boot
  run_if_exists "${SYSTEM_LOG_DIR}/systemctl-failed.txt" systemctl --failed --no-pager
  run_if_exists "${NODE_INFO_DIR}/hostnamectl.txt" hostnamectl
  run_if_exists "${NODE_INFO_DIR}/uname.txt" uname -a
}

collect_versions() {
  log_step "[2/8] Collecting version information..."

  PRODUCT_VERSION="$(docker_image_tag_like 'balisong' || true)"
  ENGINE_VERSION="$(docker_image_tag_like 'gungnir' || true)"
  SYSTEM_VERSION="$("${INSTALL_DIR}/minion" version 2>/dev/null | grep -iE 'version|版本' | head -n 1 | awk '{print $NF}' || true)"
  MACHINE_ID="$(machine_id_value || true)"
  VULN_DB="$(vuln_db_value || true)"

  PRODUCT_VERSION="${PRODUCT_VERSION:-unknown}"
  ENGINE_VERSION="${ENGINE_VERSION:-unknown}"
  SYSTEM_VERSION="${SYSTEM_VERSION:-unknown}"
  MACHINE_ID="${MACHINE_ID:-unknown}"
  VULN_DB="${VULN_DB:-unknown}"

  cat >"${NODE_INFO_DIR}/versions.txt" <<EOF
product_version=${PRODUCT_VERSION}
engine_version=${ENGINE_VERSION}
system_version=${SYSTEM_VERSION}
vuln_db=${VULN_DB}
machine_id=${MACHINE_ID}
EOF

  echo "machine_id=${MACHINE_ID}" >"${NODE_INFO_DIR}/machine-id.txt"
  echo "machine_id=${MACHINE_ID}" >"${XRAY_LOG_DIR}/machineid.txt"
  echo "hyuna_dump=${VULN_DB}" >"${XRAY_LOG_DIR}/vuln-db-version.txt"
  run_shell_capture "${NODE_INFO_DIR}/minion-version.txt" "cd '${INSTALL_DIR}' && ./minion version"
  cp "${NODE_INFO_DIR}/minion-version.txt" "${HEALTH_CHECKS_DIR}/minion-version.txt"
}

collect_health() {
  log_step "[3/8] Running health checks..."

  run_shell_capture "${HEALTH_CHECK_DIR}/mgmt-health.txt" "cd '${INSTALL_DIR}' && ./minion mgmt health"
  run_shell_capture "${HEALTH_CHECK_DIR}/engine-health.txt" "cd '${INSTALL_DIR}' && ./minion engine health"
  cp "${HEALTH_CHECK_DIR}/mgmt-health.txt" "${HEALTH_CHECKS_DIR}/minion-mgmt-health.txt"
  cp "${HEALTH_CHECK_DIR}/engine-health.txt" "${HEALTH_CHECKS_DIR}/minion-engine-health.txt"

  run_if_exists "${MINION_LOG_DIR}/minion-systemd-300.log" journalctl -u minion -n 300 --no-pager
  run_if_exists "${MINION_LOG_DIR}/minion-service-status.txt" systemctl status minion --no-pager
}

collect_resource_usage() {
  log_step "[4/8] Collecting resource usage..."

  CPU_USAGE="$(cpu_usage_percent || true)"
  MEM_INFO="$(memory_info || true)"
  DISK_INFO="$(disk_info || true)"

  MEM_USED="$(echo "${MEM_INFO}" | cut -d'|' -f1)"
  MEM_TOTAL="$(echo "${MEM_INFO}" | cut -d'|' -f2)"
  MEM_PERCENT="$(echo "${MEM_INFO}" | cut -d'|' -f3)"
  DISK_TOTAL="$(echo "${DISK_INFO}" | cut -d'|' -f1)"
  DISK_USED="$(echo "${DISK_INFO}" | cut -d'|' -f2)"
  DISK_PERCENT="$(echo "${DISK_INFO}" | cut -d'|' -f3)"
  DISK_MOUNT="$(echo "${DISK_INFO}" | cut -d'|' -f4)"

  cat >"${RESOURCE_USAGE_DIR}/cpu.txt" <<EOF
cpu_model=${CPU_MODEL_VAL}
cpu_cores=${CPU_CORES_VAL}
cpu_usage=${CPU_USAGE}%
cpu_usage_percent=${CPU_USAGE}
EOF

  cat >"${RESOURCE_USAGE_DIR}/memory.txt" <<EOF
memory_total=${MEM_TOTAL}
memory_used=${MEM_USED}
memory_usage=${MEM_PERCENT}%
memory_usage_percent=${MEM_PERCENT}
EOF

  cat >"${RESOURCE_USAGE_DIR}/disk.txt" <<EOF
disk_mount=${DISK_MOUNT}
disk_total=${DISK_TOTAL}
disk_used=${DISK_USED}
disk_usage=${DISK_PERCENT}
EOF

  cat >"${RESOURCE_USAGE_DIR}/resource-summary.txt" <<EOF
=== Resource Summary ===
Collected at: $(date '+%F %T %z')

CPU:
  Model   : ${CPU_MODEL_VAL}
  Cores   : ${CPU_CORES_VAL}
  Usage   : ${CPU_USAGE}%

Memory:
  Total   : ${MEM_TOTAL}
  Used    : ${MEM_USED}
  Usage   : ${MEM_PERCENT}%

Disk:
  Mount   : ${DISK_MOUNT}
  Total   : ${DISK_TOTAL}
  Used    : ${DISK_USED}
  Usage   : ${DISK_PERCENT}
EOF

  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/lscpu.txt" lscpu
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/free-h.txt" free -h
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/df-hT.txt" df -hT
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/lsblk.txt" lsblk
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/mount.txt" mount
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/top.txt" top -b -n 1
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/vmstat.txt" vmstat 1 5
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/docker-stats.txt" docker stats --no-stream
  run_if_exists "${RESOURCE_SNAPSHOT_DIR}/docker-ps-a.txt" docker ps -a
  run_shell_capture "${RESOURCE_SNAPSHOT_DIR}/ps-cpu-top50.txt" "ps aux --sort=-%cpu | head -n 50"
  run_shell_capture "${RESOURCE_SNAPSHOT_DIR}/ps-mem-top50.txt" "ps aux --sort=-%mem | head -n 50"

  cp "${RESOURCE_SNAPSHOT_DIR}/lscpu.txt" "${RESOURCE_USAGE_DIR}/lscpu.txt" 2>/dev/null || true
  cp "${RESOURCE_SNAPSHOT_DIR}/free-h.txt" "${RESOURCE_USAGE_DIR}/free-h.txt" 2>/dev/null || true
  cp "${RESOURCE_SNAPSHOT_DIR}/df-hT.txt" "${RESOURCE_USAGE_DIR}/df-hT.txt" 2>/dev/null || true
  cp "${RESOURCE_SNAPSHOT_DIR}/top.txt" "${RESOURCE_USAGE_DIR}/top.txt" 2>/dev/null || true
}

collect_container_status() {
  log_step "[5/8] Collecting container status..."

  local overview_file="${CONTAINER_STATUS_DIR}/overview.txt"
  local stats_snapshot="${CONTAINER_STATUS_DIR}/stats_snapshot.csv"
  local stats_alias="${CONTAINER_STATUS_DIR}/stats.csv"
  local state_history="${CONTAINER_HISTORY_DIR}/container-state-history.txt"
  local exit_codes="${CONTAINER_HISTORY_DIR}/container-exit-codes.txt"
  local analysis="${CONTAINER_HISTORY_DIR}/container-history-analysis.txt"

  echo "timestamp,container,priority,status,cpu_percent,mem_usage,mem_percent,restarts,health,exit_code,oom_killed,pids" >"${stats_snapshot}"

  {
    echo "=== Container Status Overview ==="
    echo "Collected at: $(date '+%F %T %z')"
    echo
    printf "%-24s %-10s %-10s %8s %18s %8s %10s %-10s\n" "CONTAINER" "PRIORITY" "STATUS" "CPU%" "MEM" "MEM%" "RESTARTS" "HEALTH"
    echo "----------------------------------------------------------------------------------------------------------------"
  } >"${overview_file}"

  {
    echo "=== Container State History Summary ==="
    echo "Collected at: $(date '+%F %T %z')"
    echo
    printf "%-24s %-10s %-10s %-12s %-24s %-24s\n" "CONTAINER" "STATUS" "RESTARTS" "OOM_KILLED" "STARTED_AT" "FINISHED_AT"
    echo "----------------------------------------------------------------------------------------------------------"
  } >"${state_history}"

  {
    echo "=== Container Exit Code History ==="
    echo "Collected at: $(date '+%F %T %z')"
    echo
    printf "%-24s %-10s %-24s %s\n" "CONTAINER" "EXIT_CODE" "FINISHED_AT" "ERROR_MSG"
    echo "----------------------------------------------------------------------------------------------------------"
  } >"${exit_codes}"

  local restart_lines="" oom_lines="" exit_lines="" unhealthy_lines="" not_running_lines=""
  for container_name in "${CONTAINERS[@]}"; do
    local priority status restarts health exit_code oom_killed started_at finished_at error_msg pids stats_line cpu mem_usage mem_percent
    priority="$(priority_for_container "${container_name}")"
    status="$(docker inspect --format '{{.State.Status}}' "${container_name}" 2>/dev/null || echo "not_found")"
    restarts="$(docker inspect --format '{{.RestartCount}}' "${container_name}" 2>/dev/null || echo "0")"
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_name}" 2>/dev/null || echo "none")"
    exit_code="$(docker inspect --format '{{.State.ExitCode}}' "${container_name}" 2>/dev/null || echo "-")"
    oom_killed="$(docker inspect --format '{{.State.OOMKilled}}' "${container_name}" 2>/dev/null || echo "false")"
    started_at="$(docker inspect --format '{{.State.StartedAt}}' "${container_name}" 2>/dev/null || echo "-")"
    finished_at="$(docker inspect --format '{{.State.FinishedAt}}' "${container_name}" 2>/dev/null || echo "-")"
    error_msg="$(docker inspect --format '{{.State.Error}}' "${container_name}" 2>/dev/null || echo "")"
    pids="$(docker inspect --format '{{.State.Pid}}' "${container_name}" 2>/dev/null || echo "0")"

    stats_line="$(docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}' "${container_name}" 2>/dev/null || true)"
    if [[ -n "${stats_line}" ]]; then
      cpu="$(echo "${stats_line}" | cut -d',' -f1 | tr -d '%')"
      mem_usage="$(echo "${stats_line}" | cut -d',' -f2)"
      mem_percent="$(echo "${stats_line}" | cut -d',' -f3 | tr -d '%')"
    else
      cpu=""
      mem_usage=""
      mem_percent=""
    fi

    printf "%-24s %-10s %-10s %8s %18s %8s %10s %-10s\n" \
      "${container_name}" "${priority}" "${status}" "${cpu:-"-"}%" "${mem_usage:-"-"}" "${mem_percent:-"-"}%" "${restarts}" "${health}" >>"${overview_file}"
    echo "${TIMESTAMP},${container_name},${priority},${status},${cpu},${mem_usage},${mem_percent},${restarts},${health},${exit_code},${oom_killed},${pids}" >>"${stats_snapshot}"
    printf "%-24s %-10s %-10s %-12s %-24s %-24s\n" "${container_name}" "${status}" "${restarts}" "${oom_killed}" "${started_at}" "${finished_at}" >>"${state_history}"
    printf "%-24s %-10s %-24s %s\n" "${container_name}" "${exit_code}" "${finished_at}" "${error_msg}" >>"${exit_codes}"

    if [[ "${restarts}" =~ ^[0-9]+$ && "${restarts}" -gt 0 ]]; then
      restart_lines="${restart_lines}  ${container_name}: ${restarts} restarts (priority=${priority})\n"
    fi
    if [[ "${oom_killed}" == "true" ]]; then
      oom_lines="${oom_lines}  ${container_name}: OOM killed\n"
    fi
    if [[ "${exit_code}" =~ ^[0-9]+$ && "${exit_code}" -ne 0 ]]; then
      exit_lines="${exit_lines}  ${container_name}: exit code ${exit_code} (status: ${status})\n"
    fi
    if [[ "${health}" == "unhealthy" ]]; then
      unhealthy_lines="${unhealthy_lines}  ${container_name}: unhealthy\n"
    fi
    if [[ "${status}" != "running" && "${status}" != "not_found" ]]; then
      not_running_lines="${not_running_lines}  ${container_name}: ${status}\n"
    fi

    run_shell_capture "${CONTAINER_LOG_DIR}/${container_name}.status.txt" "docker ps -a --filter 'name=^/${container_name}\$' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.RunningFor}}\t{{.Ports}}'"
    run_shell_capture "${CONTAINER_LOG_DIR}/${container_name}.inspect.txt" "docker inspect '${container_name}'"
    run_shell_capture "${CONTAINER_LOG_DIR}/${container_name}.log" "docker logs --tail ${CONTAINER_LOG_TAIL} -t '${container_name}'"
    run_shell_capture "${CONTAINER_HISTORY_DIR}/${container_name}-health-history.txt" "docker inspect --format '{{json .State.Health}}' '${container_name}' 2>/dev/null | python3 -m json.tool 2>/dev/null || docker inspect --format '{{json .State.Health}}' '${container_name}' 2>/dev/null"
  done

  cp "${stats_snapshot}" "${stats_alias}"
  run_capture "${CONTAINERS_DIR}/docker_ps" docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
  cp "${CONTAINERS_DIR}/docker_ps" "${CONTAINER_STATUS_DIR}/docker-ps-a.txt" 2>/dev/null || true

  {
    echo "=== Container History Analysis ==="
    echo "Collected at: $(date '+%F %T %z')"
    echo
    echo "--- Containers with restarts > 0 ---"
    printf "%b" "${restart_lines:-}"
    echo
    echo "--- Containers with OOM killed ---"
    printf "%b" "${oom_lines:-}"
    echo
    echo "--- Containers with non-zero exit codes ---"
    printf "%b" "${exit_lines:-}"
    echo
    echo "--- Containers with failed health checks ---"
    printf "%b" "${unhealthy_lines:-}"
    echo
    echo "--- Containers not running ---"
    printf "%b" "${not_running_lines:-}"
  } >"${analysis}"
}

collect_anomalies() {
  log_step "[6/8] Collecting anomaly evidence..."

  run_shell_capture "${CONTAINER_HISTORY_DIR}/docker-events-7d.txt" "docker events --since '${DOCKER_EVENTS_SINCE}' --filter 'type=container' --filter 'event=start' --filter 'event=stop' --filter 'event=restart' --filter 'event=die' --filter 'event=oom' --filter 'event=kill' 2>/dev/null | tail -n 500"
  run_shell_capture "${CONTAINER_HISTORY_DIR}/docker-daemon-errors.txt" "journalctl -u docker --since '7 days ago' --no-pager 2>/dev/null | grep -i 'error\\|fail\\|fatal\\|restart\\|oom\\|kill' | tail -n 300"
  run_shell_capture "${CONTAINER_HISTORY_DIR}/oom-events.txt" "journalctl --since '7 days ago' --no-pager 2>/dev/null | grep -i 'oom\\|out of memory\\|killed process' | tail -n 100; dmesg -T 2>/dev/null | grep -i 'oom\\|out of memory\\|killed process' | tail -n 100"

  cp "${CONTAINER_HISTORY_DIR}/oom-events.txt" "${ANOMALY_DIR}/oom-events.txt" 2>/dev/null || true
  cp "${CONTAINER_HISTORY_DIR}/container-history-analysis.txt" "${ANOMALY_DIR}/container-restarts.txt" 2>/dev/null || true
  run_shell_capture "${ANOMALY_DIR}/dmesg-errors.txt" "dmesg -T 2>/dev/null | grep -iE 'error|fail|crit|emerg|panic|warn|hardware|mce|machine check|memory|ecc|corrected|uncorrected' | tail -n 200"
  run_shell_capture "${ANOMALY_DIR}/panic-events.txt" "journalctl --since '7 days ago' --no-pager 2>/dev/null | grep -i panic | tail -n 100; dmesg -T 2>/dev/null | grep -i panic | tail -n 100"
}

collect_minion_collect() {
  log_step "[7/8] Running minion collect..."

  if [[ "${INCLUDE_MINION_COLLECT}" != "true" ]]; then
    echo "INCLUDE_MINION_COLLECT=false, skipped." >"${MINION_COLLECT_DIR}/skipped.txt"
    return 0
  fi

  local target="${MINION_COLLECT_DIR}/minion-collect.tar.gz"
  pushd "${INSTALL_DIR}" >/dev/null || return 0
  ./minion collect -f "${target}" >"${MINION_COLLECT_DIR}/minion-collect-command.txt" 2>&1 || true
  if [[ ! -f "${target}" ]]; then
    {
      echo
      echo "[collector-note] -f output was not created, retrying plain ./minion collect"
    } >>"${MINION_COLLECT_DIR}/minion-collect-command.txt"
    ./minion collect >>"${MINION_COLLECT_DIR}/minion-collect-command.txt" 2>&1 || true
  fi
  if [[ ! -f "${target}" && -f "${INSTALL_DIR}/minion_report.gz" ]]; then
    cp "${INSTALL_DIR}/minion_report.gz" "${target}"
  fi
  popd >/dev/null || true

  if [[ -f "${target}" ]]; then
    tar -tf "${target}" >"${MINION_COLLECT_DIR}/minion-collect-file-list.txt" 2>/dev/null || true
  else
    echo "minion collect did not produce ${target}" >>"${MINION_COLLECT_DIR}/minion-collect-command.txt"
  fi
}

write_summary_json() {
  log_step "[8/8] Writing summary and packaging..."

  local running_count abnormal_count total_count
  total_count="${#CONTAINERS[@]}"
  running_count="$(awk -F, 'NR>1 && $4=="running" {count++} END {print count+0}' "${CONTAINER_STATUS_DIR}/stats_snapshot.csv" 2>/dev/null || echo 0)"
  abnormal_count="$(awk -F, 'NR>1 && ($4!="running" || $8+0>0 || $9=="unhealthy" || $10+0!=0 || $11=="true") {count++} END {print count+0}' "${CONTAINER_STATUS_DIR}/stats_snapshot.csv" 2>/dev/null || echo 0)"

  if command_exists python3; then
    SUMMARY_PATH="${SUMMARY_DIR}/xray_collection_summary.json" \
    python3 - <<PY
import csv
import json
import os
from pathlib import Path

stats_path = Path("${CONTAINER_STATUS_DIR}/stats_snapshot.csv")
containers = []
if stats_path.exists():
    with stats_path.open(encoding="utf-8", newline="") as buffer:
        containers = list(csv.DictReader(buffer))

summary = {
    "collector": "xray-collector-${VERSION}",
    "collected_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "install_dir": "${INSTALL_DIR}",
    "host": {
        "hostname": "${HOSTNAME_VAL}",
        "ip": "${IP_VAL}",
        "os": "${OS_PRETTY}",
        "kernel": "${KERNEL_VAL}",
        "timezone": "${TIMEZONE_VAL}",
        "uptime_seconds": "${UPTIME_VAL}",
        "last_boot_at": "${LAST_BOOT_VAL}",
        "cpu_model": "${CPU_MODEL_VAL}",
        "cpu_cores": "${CPU_CORES_VAL}",
    },
    "versions": {
        "product_version": "${PRODUCT_VERSION}",
        "engine_version": "${ENGINE_VERSION}",
        "system_version": "${SYSTEM_VERSION}",
        "vuln_db": "${VULN_DB}",
        "machine_id": "${MACHINE_ID}",
    },
    "resources": {
        "cpu_usage_percent": "${CPU_USAGE}",
        "memory_used": "${MEM_USED}",
        "memory_total": "${MEM_TOTAL}",
        "memory_usage_percent": "${MEM_PERCENT}",
        "disk_mount": "${DISK_MOUNT}",
        "disk_used": "${DISK_USED}",
        "disk_total": "${DISK_TOTAL}",
        "disk_usage": "${DISK_PERCENT}",
    },
    "container_summary": {
        "total_count": int("${total_count}"),
        "running_count": int("${running_count}"),
        "abnormal_count": int("${abnormal_count}"),
    },
    "containers": containers,
    "artifact_paths": {
        "system_info": "system/system_info",
        "docker_ps": "containers/docker_ps",
        "container_state_history": "container-history/container-state-history.txt",
        "container_analysis": "container-history/container-history-analysis.txt",
        "minion_collect": "minion-collect/minion-collect.tar.gz",
    },
}

Path(os.environ["SUMMARY_PATH"]).write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY
  else
    cat >"${SUMMARY_DIR}/xray_collection_summary.json" <<EOF
{
  "collector": "xray-collector-${VERSION}",
  "collected_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "install_dir": "$(printf '%s' "${INSTALL_DIR}" | json_escape)",
  "summary_note": "python3 not found, wrote minimal JSON only"
}
EOF
  fi
}

package_logs() {
  mkdir -p "${OUTPUT_DIR}"
  tar -czf "${ARCHIVE_PATH}" -C "${WORKDIR}" "${OUTPUT_NAME}"
  rm -rf "${WORKDIR}"
}

main() {
  echo "================================================================================"
  echo "                        XRay Log Collector ${VERSION}"
  echo "================================================================================"

  INSTALL_DIR="$(detect_xray_home)" || {
    log_error "XRay installation not found. Try XRAY_HOME=/path/to/x-ray $0"
    exit 1
  }
  log_info "Installation path: ${INSTALL_DIR}"
  log_info "Output archive: ${ARCHIVE_PATH}"

  BUNDLE_ROOT="${WORKDIR}/${OUTPUT_NAME}"
  SUMMARY_DIR="${BUNDLE_ROOT}/summary"
  SYSTEM_DIR="${BUNDLE_ROOT}/system"
  CONTAINERS_DIR="${BUNDLE_ROOT}/containers"
  SYSTEM_LOG_DIR="${BUNDLE_ROOT}/system-logs"
  RESOURCE_SNAPSHOT_DIR="${BUNDLE_ROOT}/resource-snapshots"
  HEALTH_CHECKS_DIR="${BUNDLE_ROOT}/health-checks"
  MINION_LOG_DIR="${BUNDLE_ROOT}/minion-logs"
  CONTAINER_LOG_DIR="${BUNDLE_ROOT}/container-logs"
  NETWORK_DIR="${BUNDLE_ROOT}/network"
  XRAY_LOG_DIR="${BUNDLE_ROOT}/xray-logs"
  NODE_INFO_DIR="${BUNDLE_ROOT}/node-info"
  HEALTH_CHECK_DIR="${BUNDLE_ROOT}/health-check"
  RESOURCE_USAGE_DIR="${BUNDLE_ROOT}/resource-usage"
  CONTAINER_STATUS_DIR="${BUNDLE_ROOT}/container-status"
  CONTAINER_HISTORY_DIR="${BUNDLE_ROOT}/container-history"
  ANOMALY_DIR="${BUNDLE_ROOT}/anomaly-detection"
  MINION_COLLECT_DIR="${BUNDLE_ROOT}/minion-collect"
  METADATA_DIR="${BUNDLE_ROOT}/metadata"

  safe_mkdirs
  collect_manifest
  collect_node_info
  collect_versions
  collect_health
  collect_resource_usage
  collect_container_status
  collect_anomalies
  collect_minion_collect
  write_summary_json
  package_logs

  echo "================================================================================"
  echo "Collection completed."
  echo "Output: ${ARCHIVE_PATH}"
  echo "================================================================================"
}

main "$@"
