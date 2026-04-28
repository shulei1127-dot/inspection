#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${ROOT_DIR}/.venv"

show_help() {
  cat <<'EOF'
Usage: scripts/bootstrap_local_env.sh

Prepare the repository for local use:
- create .venv when missing
- install root requirements
- install log-analyzer-service requirements into the same venv
- create .env from .env.example when missing
- ensure common data directories exist
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
else
  echo "Using existing virtual environment at ${VENV_DIR}"
fi

echo "Upgrading pip"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip

echo "Installing root requirements"
"${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/requirements.txt"

echo "Installing log-analyzer-service requirements"
"${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/log-analyzer-service/requirements.txt"

mkdir -p \
  "${ROOT_DIR}/uploads" \
  "${ROOT_DIR}/workdir" \
  "${ROOT_DIR}/outputs" \
  "${ROOT_DIR}/logs"

touch \
  "${ROOT_DIR}/uploads/.gitkeep" \
  "${ROOT_DIR}/workdir/.gitkeep" \
  "${ROOT_DIR}/outputs/.gitkeep"

if [[ ! -f "${ROOT_DIR}/.env" && -f "${ROOT_DIR}/.env.example" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "Created ${ROOT_DIR}/.env from .env.example"
else
  echo "Keeping existing .env configuration"
fi

cat <<EOF

Bootstrap complete.

Next steps:
1. Review ${ROOT_DIR}/.env
2. Start services with: ${ROOT_DIR}/scripts/start_local_stack.sh
3. Verify services with: ${ROOT_DIR}/scripts/verify_local_stack.sh
EOF
