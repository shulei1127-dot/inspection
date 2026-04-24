#!/usr/bin/env bash

set -euo pipefail

XRAY_HOME="${XRAY_HOME:-/data/x-ray}"
TIMESTAMP="${TIMESTAMP:-$(date +%s)}"
OUTPUT_NAME="${OUTPUT_NAME:-xray-collector.${TIMESTAMP}}"
WORKDIR="${WORKDIR:-/tmp/${OUTPUT_NAME}}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)}"

if [[ ! -x "${XRAY_HOME}/minion" ]]; then
  echo "ERROR: ${XRAY_HOME}/minion not found or not executable" >&2
  exit 1
fi

cleanup() {
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

mkdir -p "${WORKDIR}"

BUNDLE_ROOT="${WORKDIR}/${OUTPUT_NAME}"
SYSTEM_DIR="${BUNDLE_ROOT}/system"
CONTAINERS_DIR="${BUNDLE_ROOT}/containers"
SYSTEM_LOG_DIR="${BUNDLE_ROOT}/system-logs"
RESOURCE_DIR="${BUNDLE_ROOT}/resource-snapshots"
NETWORK_DIR="${BUNDLE_ROOT}/network"
XRAY_LOG_DIR="${BUNDLE_ROOT}/xray-logs"
MINION_LOG_DIR="${BUNDLE_ROOT}/minion-logs"
RAW_DIR="${BUNDLE_ROOT}/raw"

mkdir -p \
  "${SYSTEM_DIR}" \
  "${CONTAINERS_DIR}" \
  "${SYSTEM_LOG_DIR}" \
  "${RESOURCE_DIR}" \
  "${NETWORK_DIR}" \
  "${XRAY_LOG_DIR}" \
  "${MINION_LOG_DIR}" \
  "${RAW_DIR}"

run_capture() {
  local target="$1"
  shift
  if "$@" > "${target}" 2>&1; then
    return 0
  fi
  {
    echo
    echo "[collector-note] command failed: $*"
  } >> "${target}"
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

echo "[1/6] Running built-in minion collect..."
pushd "${XRAY_HOME}" >/dev/null
run_capture "${XRAY_LOG_DIR}/minion-collect-command.txt" ./minion collect
MINION_REPORT_PATH="${XRAY_HOME}/minion_report.gz"
if [[ ! -f "${MINION_REPORT_PATH}" ]]; then
  echo "ERROR: minion collect did not produce ${MINION_REPORT_PATH}" >&2
  exit 1
fi
cp "${MINION_REPORT_PATH}" "${RAW_DIR}/minion_report.gz"
tar -xzf "${MINION_REPORT_PATH}" -C "${BUNDLE_ROOT}"
popd >/dev/null

echo "[2/6] Capturing canonical parser inputs..."
HOSTNAME_VAL="$(hostname 2>/dev/null || true)"
IP_VAL="$(first_ipv4 || true)"
TIMEZONE_VAL="$(timezone_value || true)"
UPTIME_VAL="$(awk '{print int($1)}' /proc/uptime 2>/dev/null || true)"
LAST_BOOT_VAL="$(last_boot_iso || true)"
OS_PRETTY="$(hostnamectl 2>/dev/null | awk -F': ' '/Operating System/ {print $2; exit}' || true)"
KERNEL_VAL="$(uname -r 2>/dev/null || true)"

cat > "${SYSTEM_DIR}/system_info" <<EOF
hostname=${HOSTNAME_VAL}
ip=${IP_VAL}
timezone=${TIMEZONE_VAL}
uptime_seconds=${UPTIME_VAL}
last_boot_at=${LAST_BOOT_VAL}
pretty_name=${OS_PRETTY}
kernel=${KERNEL_VAL}
EOF

run_capture "${SYSTEM_DIR}/systemctl_status" systemctl list-units --type=service --all --no-pager
run_capture "${CONTAINERS_DIR}/docker_ps" docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"

echo "[3/6] Capturing x-ray friendly raw inputs..."
run_capture "${SYSTEM_LOG_DIR}/hostnamectl.txt" hostnamectl
run_capture "${SYSTEM_LOG_DIR}/timedatectl.txt" timedatectl
run_capture "${SYSTEM_LOG_DIR}/uname.txt" uname -a
run_capture "${SYSTEM_LOG_DIR}/uptime.txt" uptime
run_capture "${SYSTEM_LOG_DIR}/list-boot.txt" journalctl --list-boot
run_capture "${SYSTEM_LOG_DIR}/systemctl-failed.txt" systemctl --failed --no-pager
run_capture "${MINION_LOG_DIR}/minion-service-status.txt" systemctl status minion --no-pager
run_capture "${RESOURCE_DIR}/docker-ps-a.txt" docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
run_capture "${NETWORK_DIR}/ip-addr.txt" ip -d addr

echo "[4/6] Capturing extra report-oriented diagnostics..."
run_capture "${SYSTEM_LOG_DIR}/lscpu.txt" lscpu
run_capture "${SYSTEM_LOG_DIR}/memory.txt" free -h
run_capture "${SYSTEM_LOG_DIR}/disk.txt" df -h
run_capture "${SYSTEM_LOG_DIR}/top.txt" top -b -n 1
run_capture "${XRAY_LOG_DIR}/version.txt" "${XRAY_HOME}/minion" version

MACHINE_ID_VAL="$(machine_id_value || true)"
VULN_DB_VAL="$(vuln_db_value || true)"
{
  echo "machine_id=${MACHINE_ID_VAL}"
} > "${XRAY_LOG_DIR}/machineid.txt"
{
  echo "hyuna_dump=${VULN_DB_VAL}"
} > "${XRAY_LOG_DIR}/vuln-db-version.txt"

echo "[5/6] Writing collection manifest..."
cat > "${XRAY_LOG_DIR}/collection-info.txt" <<EOF
collector=xray-report-bundle-v1
collected_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
xray_home=${XRAY_HOME}
output_name=${OUTPUT_NAME}
machine_id=${MACHINE_ID_VAL}
hyuna_dump=${VULN_DB_VAL}
EOF

echo "[6/6] Packing final archive..."
mkdir -p "${OUTPUT_DIR}"
FINAL_ARCHIVE="${OUTPUT_DIR}/${OUTPUT_NAME}.tar.gz"
tar -czf "${FINAL_ARCHIVE}" -C "${WORKDIR}" "${OUTPUT_NAME}"

echo
echo "Collection completed."
echo "Final archive: ${FINAL_ARCHIVE}"
echo "Bundle root inside archive: ${OUTPUT_NAME}/"
