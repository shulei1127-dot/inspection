#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACK_RUNTIME_DIR="${STACK_RUNTIME_DIR:-${ROOT_DIR}/logs/local-stack}"
STACK_PLATFORM_PID_FILE="${STACK_RUNTIME_DIR}/platform.pid"
STACK_ANALYZER_PID_FILE="${STACK_RUNTIME_DIR}/analyzer.pid"
STACK_PLATFORM_LOG_FILE="${STACK_RUNTIME_DIR}/platform.log"
STACK_ANALYZER_LOG_FILE="${STACK_RUNTIME_DIR}/analyzer.log"
STACK_CARBONE_CONTAINER_NAME="${STACK_CARBONE_CONTAINER_NAME:-inspection-carbone-local-stack}"
CARBONE_IMAGE_REF="${CARBONE_IMAGE_REF:-carbone/carbone-ee:latest}"

usage_common_note() {
  cat <<'EOF'
Environment loading priority:
1. current shell env
2. repository .env file
3. built-in defaults in the scripts
EOF
}

load_local_stack_env() {
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
    set +a
  fi

  APP_HOST="${APP_HOST:-0.0.0.0}"
  APP_PORT="${APP_PORT:-8000}"
  APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:${APP_PORT}/health}"

  ANALYZER_MODE="${ANALYZER_MODE:-remote}"
  ANALYZER_BASE_URL="${ANALYZER_BASE_URL:-http://127.0.0.1:8090}"
  ANALYZER_HEALTH_URL="${ANALYZER_HEALTH_URL:-${ANALYZER_BASE_URL%/}/health}"
  ANALYZER_APP_HOST="${ANALYZER_APP_HOST:-127.0.0.1}"
  ANALYZER_APP_PORT="${ANALYZER_APP_PORT:-$(url_port_or_default "${ANALYZER_BASE_URL}" "8090")}"

  CARBONE_BASE_URL="${CARBONE_BASE_URL:-http://127.0.0.1:4000}"
  CARBONE_STATUS_URL="${CARBONE_STATUS_URL:-${CARBONE_BASE_URL%/}/status}"
  STACK_CARBONE_HOST_PORT="${STACK_CARBONE_HOST_PORT:-$(url_port_or_default "${CARBONE_BASE_URL}" "4000")}"
  STACK_CARBONE_HOST="${STACK_CARBONE_HOST:-$(url_host_or_default "${CARBONE_BASE_URL}" "127.0.0.1")}"

  XRAY_URL="http://127.0.0.1:${APP_PORT}/xray"
  WAF_URL="http://127.0.0.1:${APP_PORT}/waf"
  WAF_AUDITS_URL="http://127.0.0.1:${APP_PORT}/waf-audits/ui"
}

ensure_runtime_dir() {
  mkdir -p "${STACK_RUNTIME_DIR}"
}

require_root_venv() {
  if [[ ! -x "${ROOT_DIR}/.venv/bin/uvicorn" ]]; then
    echo "Missing ${ROOT_DIR}/.venv/bin/uvicorn. Run scripts/bootstrap_local_env.sh first." >&2
    exit 1
  fi
}

url_host_or_default() {
  local url="$1"
  local default_host="$2"
  local trimmed="${url#http://}"
  trimmed="${trimmed#https://}"
  trimmed="${trimmed%%/*}"
  if [[ -z "${trimmed}" ]]; then
    printf '%s\n' "${default_host}"
    return
  fi
  if [[ "${trimmed}" == *:* ]]; then
    printf '%s\n' "${trimmed%%:*}"
    return
  fi
  printf '%s\n' "${trimmed}"
}

url_port_or_default() {
  local url="$1"
  local default_port="$2"
  local trimmed="${url#http://}"
  trimmed="${trimmed#https://}"
  trimmed="${trimmed%%/*}"
  if [[ "${trimmed}" == *:* ]]; then
    printf '%s\n' "${trimmed##*:}"
    return
  fi
  printf '%s\n' "${default_port}"
}

is_loopback_host() {
  local host="$1"
  [[ "${host}" == "127.0.0.1" || "${host}" == "localhost" || "${host}" == "0.0.0.0" ]]
}

pid_is_alive() {
  local pid_file="$1"
  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi
  local pid
  pid="$(<"${pid_file}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

remove_stale_pid_file() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]] && ! pid_is_alive "${pid_file}"; then
    rm -f "${pid_file}"
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local delay_seconds="${4:-1}"

  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay_seconds}"
  done

  echo "${label} did not become ready at ${url}." >&2
  return 1
}

kill_from_pid_file() {
  local pid_file="$1"
  local label="$2"

  if ! pid_is_alive "${pid_file}"; then
    rm -f "${pid_file}"
    echo "${label} is not running from a managed PID file."
    return 0
  fi

  local pid
  pid="$(<"${pid_file}")"
  kill "${pid}" >/dev/null 2>&1 || true

  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      rm -f "${pid_file}"
      echo "Stopped ${label} (pid ${pid})."
      return 0
    fi
    sleep 1
  done

  kill -9 "${pid}" >/dev/null 2>&1 || true
  rm -f "${pid_file}"
  echo "Force-stopped ${label} (pid ${pid})."
}
