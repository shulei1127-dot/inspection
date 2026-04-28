#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=./lib/local_stack_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/local_stack_common.sh"

show_help() {
  cat <<'EOF'
Usage: scripts/verify_local_stack.sh

Verify the standard local stack:
- platform /health
- analyzer /health
- Carbone /status
EOF
  usage_common_note
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

load_local_stack_env

printf 'Checking platform: %s\n' "${APP_HEALTH_URL}"
curl -fsS "${APP_HEALTH_URL}" >/dev/null
echo "  ok"

printf 'Checking analyzer: %s\n' "${ANALYZER_HEALTH_URL}"
curl -fsS "${ANALYZER_HEALTH_URL}" >/dev/null
echo "  ok"

printf 'Checking Carbone: %s\n' "${CARBONE_STATUS_URL}"
curl -fsS "${CARBONE_STATUS_URL}" >/dev/null
echo "  ok"

cat <<EOF

Local stack verification succeeded.
- Xray page: ${XRAY_URL}
- WAF preprocessing page: ${WAF_URL}
- WAF audits page: ${WAF_AUDITS_URL}
EOF
