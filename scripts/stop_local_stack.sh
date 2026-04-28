#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=./lib/local_stack_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/local_stack_common.sh"

show_help() {
  cat <<'EOF'
Usage: scripts/stop_local_stack.sh

Stop the local services that were started by scripts/start_local_stack.sh.
The script stops:
- managed platform process
- managed analyzer process
- managed Carbone container by its standard local-stack container name
EOF
  usage_common_note
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

load_local_stack_env
ensure_runtime_dir

kill_from_pid_file "${STACK_PLATFORM_PID_FILE}" "inspection-report-platform"
kill_from_pid_file "${STACK_ANALYZER_PID_FILE}" "log-analyzer-service"

if command -v docker >/dev/null 2>&1; then
  carbone_container_id="$(docker ps -aq -f "name=^/${STACK_CARBONE_CONTAINER_NAME}$" || true)"
  if [[ -n "${carbone_container_id}" ]]; then
    docker rm -f "${STACK_CARBONE_CONTAINER_NAME}" >/dev/null
    echo "Stopped Carbone container ${STACK_CARBONE_CONTAINER_NAME}."
  else
    echo "No managed Carbone container named ${STACK_CARBONE_CONTAINER_NAME} was found."
  fi
else
  echo "Docker not found; skipping Carbone container shutdown."
fi
