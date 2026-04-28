#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=./lib/local_stack_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/local_stack_common.sh"

show_help() {
  cat <<'EOF'
Usage: scripts/start_local_stack.sh

Start the standard local stack for this repository:
- Carbone runtime (local Docker container when CARBONE_BASE_URL is loopback)
- log-analyzer-service (when ANALYZER_MODE=remote and ANALYZER_BASE_URL is loopback)
- FastAPI platform
EOF
  usage_common_note
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

load_local_stack_env
ensure_runtime_dir
require_root_venv
remove_stale_pid_file "${STACK_ANALYZER_PID_FILE}"
remove_stale_pid_file "${STACK_PLATFORM_PID_FILE}"

start_carbone() {
  if curl -fsS "${CARBONE_STATUS_URL}" >/dev/null 2>&1; then
    echo "Carbone already reachable at ${CARBONE_STATUS_URL}"
    return 0
  fi

  if ! is_loopback_host "${STACK_CARBONE_HOST}"; then
    echo "Carbone is configured as a non-local runtime (${CARBONE_BASE_URL}); skipping local container startup."
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required to start local Carbone at ${CARBONE_BASE_URL}" >&2
    exit 1
  fi

  if ! docker image inspect "${CARBONE_IMAGE_REF}" >/dev/null 2>&1; then
    echo "Pulling ${CARBONE_IMAGE_REF}"
    docker pull "${CARBONE_IMAGE_REF}"
  fi

  local existing_id
  existing_id="$(docker ps -aq -f "name=^/${STACK_CARBONE_CONTAINER_NAME}$" || true)"
  if [[ -n "${existing_id}" ]]; then
    local running_id
    running_id="$(docker ps -q -f "name=^/${STACK_CARBONE_CONTAINER_NAME}$" || true)"
    if [[ -z "${running_id}" ]]; then
      docker start "${STACK_CARBONE_CONTAINER_NAME}" >/dev/null
      echo "Started existing Carbone container ${STACK_CARBONE_CONTAINER_NAME}"
    else
      echo "Carbone container ${STACK_CARBONE_CONTAINER_NAME} is already running"
    fi
  else
    docker run -d \
      --name "${STACK_CARBONE_CONTAINER_NAME}" \
      -p "${STACK_CARBONE_HOST_PORT}:4000" \
      "${CARBONE_IMAGE_REF}" >/dev/null
    echo "Started Carbone container ${STACK_CARBONE_CONTAINER_NAME} on ${CARBONE_BASE_URL}"
  fi

  wait_for_http "${CARBONE_STATUS_URL}" "Carbone runtime"
}

start_analyzer() {
  if [[ "${ANALYZER_MODE}" != "remote" ]]; then
    echo "Analyzer mode is ${ANALYZER_MODE}; skipping standalone analyzer startup."
    return 0
  fi

  local analyzer_host
  analyzer_host="$(url_host_or_default "${ANALYZER_BASE_URL}" "127.0.0.1")"
  if ! is_loopback_host "${analyzer_host}"; then
    echo "Analyzer is configured as a non-local runtime (${ANALYZER_BASE_URL}); skipping local analyzer startup."
    return 0
  fi

  if curl -fsS "${ANALYZER_HEALTH_URL}" >/dev/null 2>&1; then
    echo "Analyzer already reachable at ${ANALYZER_HEALTH_URL}"
    return 0
  fi

  if pid_is_alive "${STACK_ANALYZER_PID_FILE}"; then
    echo "Analyzer process already running from ${STACK_ANALYZER_PID_FILE}"
    wait_for_http "${ANALYZER_HEALTH_URL}" "log-analyzer-service"
    return 0
  fi

  echo "Starting log-analyzer-service on http://${ANALYZER_APP_HOST}:${ANALYZER_APP_PORT}"
  (
    cd "${ROOT_DIR}/log-analyzer-service"
    nohup "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app \
      --host "${ANALYZER_APP_HOST}" \
      --port "${ANALYZER_APP_PORT}" \
      >"${STACK_ANALYZER_LOG_FILE}" 2>&1 &
    echo $! >"${STACK_ANALYZER_PID_FILE}"
  )

  wait_for_http "${ANALYZER_HEALTH_URL}" "log-analyzer-service"
}

start_platform() {
  if curl -fsS "${APP_HEALTH_URL}" >/dev/null 2>&1; then
    echo "Platform already reachable at ${APP_HEALTH_URL}"
    return 0
  fi

  if pid_is_alive "${STACK_PLATFORM_PID_FILE}"; then
    echo "Platform process already running from ${STACK_PLATFORM_PID_FILE}"
    wait_for_http "${APP_HEALTH_URL}" "inspection-report-platform"
    return 0
  fi

  echo "Starting platform on http://127.0.0.1:${APP_PORT}"
  (
    cd "${ROOT_DIR}"
    ENV_FILE="${ROOT_DIR}/.env" \
    nohup "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app \
      --host "${APP_HOST}" \
      --port "${APP_PORT}" \
      >"${STACK_PLATFORM_LOG_FILE}" 2>&1 &
    echo $! >"${STACK_PLATFORM_PID_FILE}"
  )

  wait_for_http "${APP_HEALTH_URL}" "inspection-report-platform"
}

start_carbone
start_analyzer
start_platform

cat <<EOF

Local stack is ready.
- Platform health: ${APP_HEALTH_URL}
- Analyzer health: ${ANALYZER_HEALTH_URL}
- Carbone status: ${CARBONE_STATUS_URL}

Useful pages:
- Xray: ${XRAY_URL}
- WAF preprocessing: ${WAF_URL}
- WAF audits: ${WAF_AUDITS_URL}

Logs:
- Platform: ${STACK_PLATFORM_LOG_FILE}
- Analyzer: ${STACK_ANALYZER_LOG_FILE}
EOF
