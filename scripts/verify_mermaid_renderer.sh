#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${MERMAID_RENDERER_HOST:-127.0.0.1}"
HOST_PORT="${MERMAID_RENDERER_HOST_PORT:-8092}"
BASE_URL="${MERMAID_RENDERER_BASE_URL:-http://${HOST}:${HOST_PORT}}"
RUN_PLATFORM_CHECK=false
HEALTH_ONLY=false

for arg in "$@"; do
  case "${arg}" in
    --platform)
      RUN_PLATFORM_CHECK=true
      ;;
    --health-only)
      HEALTH_ONLY=true
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      echo "Usage: $0 [--health-only] [--platform]" >&2
      exit 2
      ;;
  esac
done

pass() {
  echo "[PASS] $1"
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || fail "curl is required"

health_body="$(curl -fsS "${BASE_URL}/health" || true)"
if [[ "${health_body}" != *'"service":"mermaid-renderer-service"'* ]]; then
  fail "Mermaid renderer health check failed at ${BASE_URL}/health. Response: ${health_body:-<empty>}"
fi
pass "Mermaid renderer /health is reachable at ${BASE_URL}"

if [[ "${HEALTH_ONLY}" == "true" ]]; then
  exit 0
fi

tmp_png="$(mktemp /tmp/mermaid-renderer-verify-XXXXXX.png)"
tmp_headers="$(mktemp /tmp/mermaid-renderer-verify-XXXXXX.headers)"
curl -fsS -X POST "${BASE_URL}/render" \
  -H "Content-Type: application/json" \
  -d '{"source":"flowchart LR\n  A[历史窗口] --> B[当前风险]\n  B --> C[未来观察]","format":"png","theme":"default","background":"white"}' \
  -D "${tmp_headers}" \
  -o "${tmp_png}" || fail "POST /render failed"

if ! grep -qi "Content-Type: image/png" "${tmp_headers}"; then
  fail "POST /render did not return image/png"
fi
if ! grep -qi "Cache-Control: no-store" "${tmp_headers}"; then
  fail "POST /render did not return Cache-Control: no-store"
fi
if [[ ! -s "${tmp_png}" ]]; then
  fail "POST /render returned an empty PNG"
fi
pass "Mermaid renderer /render returned PNG bytes"

if [[ "${RUN_PLATFORM_CHECK}" == "true" ]]; then
  if [[ ! -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    fail "Missing ${ROOT_DIR}/.venv/bin/python"
  fi
  tmp_json="$(mktemp /tmp/mermaid-renderer-platform-XXXXXX.json)"
  (
    cd "${ROOT_DIR}"
    MERMAID_RENDERER_MODE=remote \
      MERMAID_RENDERER_BASE_URL="${BASE_URL}" \
      .venv/bin/python scripts/run_trend_enhancement.py tests/fixtures/trend_reports/multi_point_status_analysis.md
  ) > "${tmp_json}"
  png_path="$(
    ROOT_DIR="${ROOT_DIR}" TMP_JSON="${tmp_json}" .venv/bin/python - <<'PY'
import json
import os
from pathlib import Path

payload = json.loads(Path(os.environ["TMP_JSON"]).read_text())
path = payload.get("trend_state_graph_image_path")
if not path:
    raise SystemExit(1)
print(path)
PY
  )" || fail "Platform trend run did not return trend_state_graph_image_path"
  if [[ ! -s "${ROOT_DIR}/${png_path}" ]]; then
    fail "Platform trend graph PNG is missing: ${png_path}"
  fi
  pass "Platform remote trend run produced ${png_path}"
fi
