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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEFAULT_COMPOSE_FILE="docker-compose.yml"
DEFAULT_SERVICES="api-server,web-server,mcp-server,a2a-server"
DEFAULT_PROJECT_NAME="expert-agent-local-docker"

STATE_DIR="${SCRIPT_DIR}/.run"
STATE_FILE="${STATE_DIR}/local-docker-server.state"
mkdir -p "$STATE_DIR"

usage() {
  cat <<USAGE
Usage:
  ./local-docker-server.sh --env <control-env-file> <start|stop|restart|status|ensure> [all|service1,service2]

Behavior:
  - Reads a control env file and optional LOCAL_DOCKER_* keys.
  - Supports source env indirection via LOCAL_DOCKER_SOURCE_ENV.
  - Enforces strict env consistency using a persisted env hash.

Supported LOCAL_DOCKER_* keys (in control env file):
  LOCAL_DOCKER_SOURCE_ENV=<path-to-runtime-env>
  LOCAL_DOCKER_COMPOSE_FILE=<compose-file-path>
  LOCAL_DOCKER_PROJECT_NAME=<docker-compose-project-name>
  LOCAL_DOCKER_SERVICES=<comma-separated-service-list>
USAGE
}

abspath() {
  local p="$1"
  if [[ "$p" = /* ]]; then
    printf '%s\n' "$p"
  else
    printf '%s\n' "${SCRIPT_DIR}/${p}"
  fi
}

ensure_file_exists() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "CRITICAL ERROR: file not found: $p" >&2
    exit 2
  fi
}

load_env_file() {
  local env_file="$1"
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    line="${line#export }"
    if [[ "$line" != *=* ]]; then
      continue
    fi
    key="${line%%=*}"
    value="${line#*=}"
    key="$(printf '%s' "$key" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi

    value="${value#${value%%[![:space:]]*}}"
    value="${value%${value##*[![:space:]]}}"
    if [[ ( "$value" == '"'*'"' ) || ( "$value" == "'"*"'" ) ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "${key}=${value}"
  done < "$env_file"
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "CRITICAL ERROR: docker not found in PATH" >&2
    exit 2
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "CRITICAL ERROR: docker daemon is not available" >&2
    exit 2
  fi
}

load_private_pypi_from_vault() {
  if [[ -n "${PYPI_URL:-}" && -n "${PYPI_USERNAME:-}" && -n "${PYPI_PASSWORD:-}" ]]; then
    export PYPI_URL PYPI_USERNAME PYPI_PASSWORD
    return 0
  fi

  if [[ -z "${VAULT_ADDR:-}" || -z "${VAULT_TOKEN:-}" || -z "${VAULT_MOUNT_POINT:-}" ]]; then
    return 0
  fi

  local vault_mount_name vault_secret_path vault_url vault_raw
  if [[ -n "${VAULT_CONFIG_PATH:-}" ]]; then
    vault_mount_name="${VAULT_MOUNT_POINT}"
    vault_secret_path="${VAULT_CONFIG_PATH}"
  else
    vault_mount_name="${VAULT_MOUNT_POINT%%/*}"
    if [[ "$vault_mount_name" == "$VAULT_MOUNT_POINT" ]]; then
      vault_secret_path="config"
    else
      vault_secret_path="${VAULT_MOUNT_POINT#*/}"
    fi
  fi

  vault_url="${VAULT_ADDR%/}/v1/${vault_mount_name}/data/${vault_secret_path}"
  vault_raw="$(curl -sk -H "X-Vault-Token: ${VAULT_TOKEN}" "${vault_url}" 2>/dev/null || true)"
  if [[ -z "$vault_raw" ]]; then
    return 0
  fi

  vault_extract() {
    local key_path="$1"
    VAULT_RAW_INPUT="$vault_raw" python3 - "$key_path" <<'PY' 2>/dev/null || true
import json
import os
import sys

key_path = sys.argv[1]
raw = os.environ.get("VAULT_RAW_INPUT", "")
doc = json.loads(raw)
blob = doc["data"]["data"]
cfg = blob.get("json", blob)
if "dev" in cfg and isinstance(cfg["dev"], dict):
    cfg = cfg["dev"]
value = cfg
for part in key_path.split("."):
    if not isinstance(value, dict):
        raise KeyError(part)
    value = value[part]
if isinstance(value, str):
    print(value)
PY
  }

  if [[ -z "${PYPI_URL:-}" ]]; then
    PYPI_URL="$(vault_extract "repository.pypi.url")"
  fi
  if [[ -z "${PYPI_USERNAME:-}" ]]; then
    PYPI_USERNAME="$(vault_extract "repository.pypi.username")"
  fi
  if [[ -z "${PYPI_PASSWORD:-}" ]]; then
    PYPI_PASSWORD="$(vault_extract "repository.pypi.password")"
  fi

  export PYPI_URL PYPI_USERNAME PYPI_PASSWORD
}

load_state() {
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    return 0
  fi
  return 1
}

write_state() {
  local env_file="$1"
  local env_hash="$2"
  local compose_file="$3"
  local project_name="$4"
  local services_csv="$5"

  {
    printf 'STATE_RUNTIME_ENV_FILE=%q\n' "$env_file"
    printf 'STATE_RUNTIME_ENV_HASH=%q\n' "$env_hash"
    printf 'STATE_COMPOSE_FILE=%q\n' "$compose_file"
    printf 'STATE_PROJECT_NAME=%q\n' "$project_name"
    printf 'STATE_SERVICES=%q\n' "$services_csv"
  } > "$STATE_FILE"
}

compose_cmd() {
  local runtime_env="$1"
  local compose_file="$2"
  local project_name="$3"
  shift 3
  ENV_FILE="$runtime_env" docker compose -f "$compose_file" --project-name "$project_name" --env-file "$runtime_env" "$@"
}

split_services() {
  local csv="$1"
  local norm
  norm="${csv//,/ }"
  # shellcheck disable=SC2206
  SERVICES=( $norm )
  if [[ ${#SERVICES[@]} -eq 0 ]]; then
    echo "CRITICAL ERROR: no services selected" >&2
    exit 2
  fi
}

running_ids_for_services() {
  local runtime_env="$1"
  local compose_file="$2"
  local project_name="$3"
  shift 3
  local ids=""
  ids="$(compose_cmd "$runtime_env" "$compose_file" "$project_name" ps --status running -q "$@" 2>/dev/null || true)"
  if [[ -z "$ids" ]]; then
    ids="$(compose_cmd "$runtime_env" "$compose_file" "$project_name" ps -q "$@" 2>/dev/null || true)"
  fi
  printf '%s\n' "$ids"
}

# -------------------- argument parsing --------------------
ENV_FILE=""
ACTION=""
TARGET_SERVICES="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    start|stop|restart|status|ensure)
      ACTION="$1"
      shift
      ;;
    all|*)
      if [[ -z "$ACTION" ]]; then
        echo "CRITICAL ERROR: unknown action '$1'" >&2
        usage
        exit 2
      fi
      TARGET_SERVICES="$1"
      shift
      ;;
  esac
done

if [[ -z "$ENV_FILE" ]]; then
  echo "CRITICAL ERROR: --env <control-env-file> is required" >&2
  usage
  exit 2
fi

if [[ -z "$ACTION" ]]; then
  echo "CRITICAL ERROR: action is required" >&2
  usage
  exit 2
fi

CONTROL_ENV_FILE="$(abspath "$ENV_FILE")"
ensure_file_exists "$CONTROL_ENV_FILE"
load_env_file "$CONTROL_ENV_FILE"

RUNTIME_ENV_FILE="$CONTROL_ENV_FILE"
if [[ -n "${LOCAL_DOCKER_SOURCE_ENV:-}" ]]; then
  RUNTIME_ENV_FILE="$(abspath "$LOCAL_DOCKER_SOURCE_ENV")"
  ensure_file_exists "$RUNTIME_ENV_FILE"
  load_env_file "$RUNTIME_ENV_FILE"
fi

COMPOSE_FILE_RAW="${LOCAL_DOCKER_COMPOSE_FILE:-$DEFAULT_COMPOSE_FILE}"
COMPOSE_FILE="$(abspath "$COMPOSE_FILE_RAW")"
ensure_file_exists "$COMPOSE_FILE"

PROJECT_NAME="${LOCAL_DOCKER_PROJECT_NAME:-$DEFAULT_PROJECT_NAME}"

SERVICES_CSV="${LOCAL_DOCKER_SERVICES:-$DEFAULT_SERVICES}"
if [[ "$TARGET_SERVICES" != "all" ]]; then
  SERVICES_CSV="$TARGET_SERVICES"
fi
split_services "$SERVICES_CSV"

require_docker
load_private_pypi_from_vault

RUNTIME_ENV_HASH="$(sha256sum "$RUNTIME_ENV_FILE" | awk '{print $1}')"

state_matches_current() {
  [[ "${STATE_RUNTIME_ENV_HASH:-}" == "$RUNTIME_ENV_HASH" ]] &&
  [[ "${STATE_COMPOSE_FILE:-}" == "$COMPOSE_FILE" ]] &&
  [[ "${STATE_PROJECT_NAME:-}" == "$PROJECT_NAME" ]]
}

stop_with_env() {
  local env_for_down="$1"
  if [[ -f "$env_for_down" ]]; then
    compose_cmd "$env_for_down" "$COMPOSE_FILE" "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
  else
    compose_cmd "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
  fi
}

handle_mismatch_and_block() {
  local mismatch_reason="$1"
  local down_env="${STATE_RUNTIME_ENV_FILE:-$RUNTIME_ENV_FILE}"
  echo "BLOCKED: $mismatch_reason"
  echo "Stopping currently running stack for project '$PROJECT_NAME'..."
  stop_with_env "$down_env"
  rm -f "$STATE_FILE"
  echo "Stopped due env/runtime mismatch. Local hands required to confirm and rerun with the intended env file." >&2
  exit 20
}

case "$ACTION" in
  status)
    IDS="$(running_ids_for_services "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" "${SERVICES[@]}")"
    if [[ -n "$IDS" ]]; then
      if load_state && ! state_matches_current; then
        echo "status: RUNNING (env mismatch)"
        echo "current_env=$RUNTIME_ENV_FILE"
        echo "state_env=${STATE_RUNTIME_ENV_FILE:-unknown}"
        exit 21
      fi
      echo "status: RUNNING"
      compose_cmd "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" ps "${SERVICES[@]}" || true
      exit 0
    fi
    echo "status: STOPPED"
    exit 0
    ;;

  stop)
    if load_state; then
      stop_with_env "${STATE_RUNTIME_ENV_FILE:-$RUNTIME_ENV_FILE}"
    else
      stop_with_env "$RUNTIME_ENV_FILE"
    fi
    rm -f "$STATE_FILE"
    echo "stop: COMPLETE"
    exit 0
    ;;

  start|ensure)
    IDS="$(running_ids_for_services "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" "${SERVICES[@]}")"
    if [[ -n "$IDS" ]]; then
      if load_state; then
        if state_matches_current; then
          echo "$ACTION: ALREADY RUNNING with matching env ($RUNTIME_ENV_FILE)"
          compose_cmd "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" ps "${SERVICES[@]}" || true
          exit 0
        fi
        handle_mismatch_and_block "stack running with different env/compose/project"
      else
        handle_mismatch_and_block "stack running without state provenance"
      fi
    fi

    compose_cmd "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" up -d "${SERVICES[@]}"
    write_state "$RUNTIME_ENV_FILE" "$RUNTIME_ENV_HASH" "$COMPOSE_FILE" "$PROJECT_NAME" "$SERVICES_CSV"
    echo "$ACTION: STARTED (project=$PROJECT_NAME, env=$RUNTIME_ENV_FILE, services=$SERVICES_CSV)"
    compose_cmd "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" ps "${SERVICES[@]}" || true
    exit 0
    ;;

  restart)
    if load_state; then
      stop_with_env "${STATE_RUNTIME_ENV_FILE:-$RUNTIME_ENV_FILE}"
    else
      stop_with_env "$RUNTIME_ENV_FILE"
    fi
    rm -f "$STATE_FILE"
    compose_cmd "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" up -d "${SERVICES[@]}"
    write_state "$RUNTIME_ENV_FILE" "$RUNTIME_ENV_HASH" "$COMPOSE_FILE" "$PROJECT_NAME" "$SERVICES_CSV"
    echo "restart: COMPLETE (project=$PROJECT_NAME, env=$RUNTIME_ENV_FILE, services=$SERVICES_CSV)"
    compose_cmd "$RUNTIME_ENV_FILE" "$COMPOSE_FILE" "$PROJECT_NAME" ps "${SERVICES[@]}" || true
    exit 0
    ;;

  *)
    echo "CRITICAL ERROR: unsupported action '$ACTION'" >&2
    usage
    exit 2
    ;;
esac
