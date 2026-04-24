#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${MERMAID_RENDERER_IMAGE:-mermaid-renderer-service:0.1.0}"
CONTAINER_NAME="${MERMAID_RENDERER_CONTAINER_NAME:-mermaid-renderer-service}"
HOST_PORT="${MERMAID_RENDERER_HOST_PORT:-8092}"
CONTAINER_PORT="${MERMAID_RENDERER_CONTAINER_PORT:-8091}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to start ${CONTAINER_NAME}." >&2
  exit 1
fi

if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  echo "Image ${IMAGE_NAME} not found. Build it first:" >&2
  echo "  cd ${ROOT_DIR}/mermaid-renderer-service && DOCKER_BUILDKIT=0 docker build -t ${IMAGE_NAME} ." >&2
  exit 1
fi

existing_id="$(docker ps -aq -f "name=^/${CONTAINER_NAME}$" || true)"
if [[ -n "${existing_id}" ]]; then
  running_id="$(docker ps -q -f "name=^/${CONTAINER_NAME}$" || true)"
  if [[ -n "${running_id}" ]]; then
    echo "${CONTAINER_NAME} is already running on host port ${HOST_PORT}."
    exit 0
  fi
  docker start "${CONTAINER_NAME}" >/dev/null
  echo "Started existing ${CONTAINER_NAME}."
else
  docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    -p "${HOST_PORT}:${CONTAINER_PORT}" \
    "${IMAGE_NAME}" >/dev/null
  echo "Started new ${CONTAINER_NAME} on http://127.0.0.1:${HOST_PORT}."
fi

"${ROOT_DIR}/scripts/verify_mermaid_renderer.sh" --health-only
