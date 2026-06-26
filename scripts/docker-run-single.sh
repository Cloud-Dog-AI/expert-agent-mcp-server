#!/usr/bin/env bash
# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-expert-agent-mcp-server:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-expert-agent-4servers}"
ENV_FILE="${1:-env-docker-example}"
MODE="${2:-all}"
SECRETS_FILE="${3:-}"
NETWORK_MODE="${NETWORK_MODE:-host}"
PORT_ARGS=()

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}" >&2
  exit 2
fi

mkdir -p logs storage database cache

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

# If secrets file isn't provided explicitly, use the conventional sibling.
if [[ -z "${SECRETS_FILE}" ]]; then
  if [[ -f "${ENV_FILE}-secrets" ]]; then
    SECRETS_FILE="${ENV_FILE}-secrets"
  fi
fi

if [[ "${NETWORK_MODE}" != "host" ]]; then
  API_PORT="${API_PORT:-18083}"
  WEB_PORT="${WEB_PORT:-18080}"
  MCP_PORT="${MCP_PORT:-18081}"
  A2A_PORT="${A2A_PORT:-18082}"
  PORT_ARGS=(-p "${WEB_PORT}:${WEB_PORT}" -p "${MCP_PORT}:${MCP_PORT}" -p "${A2A_PORT}:${A2A_PORT}" -p "${API_PORT}:${API_PORT}")
fi

docker run -d \
  --name "${CONTAINER_NAME}" \
  --network="${NETWORK_MODE}" \
  --env-file "${ENV_FILE}" \
  -e "EXPERT_ENV_FILE=/app/${ENV_FILE}" \
  -e "CLOUD_DOG__EXPERT__ENV_FILE=/app/${ENV_FILE}" \
  -e "CLOUD_DOG__EXPERT__ENV_SECRETS_FILES=/app/${SECRETS_FILE}" \
  -v "$(pwd)/${ENV_FILE}:/app/${ENV_FILE}:ro" \
  $( [[ -n "${SECRETS_FILE}" ]] && echo "-v $(pwd)/${SECRETS_FILE}:/app/${SECRETS_FILE}:ro" ) \
  $( [[ -f "$(pwd)/certs/ca.crt" ]] && echo "-e EXPERT_CA_BUNDLE=/app/certs/ca.crt -v $(pwd)/certs:/app/certs:ro" ) \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/storage:/app/storage" \
  -v "$(pwd)/database:/app/database" \
  -v "$(pwd)/cache:/app/cache" \
  "${PORT_ARGS[@]}" \
  "${IMAGE_NAME}" "${MODE}"

echo "Container started: ${CONTAINER_NAME}"
docker ps --filter "name=${CONTAINER_NAME}"
