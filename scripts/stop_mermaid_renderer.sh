#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${MERMAID_RENDERER_CONTAINER_NAME:-mermaid-renderer-service}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to stop ${CONTAINER_NAME}." >&2
  exit 1
fi

if docker ps -aq -f "name=^/${CONTAINER_NAME}$" >/dev/null 2>&1; then
  container_id="$(docker ps -aq -f "name=^/${CONTAINER_NAME}$" || true)"
  if [[ -n "${container_id}" ]]; then
    docker rm -f "${CONTAINER_NAME}" >/dev/null
    echo "Stopped and removed ${CONTAINER_NAME}."
    exit 0
  fi
fi

echo "${CONTAINER_NAME} is not present."
