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

cd /app

mkdir -p logs .pids database storage cache
chmod 700 logs 2>/dev/null || true
if [[ -f logs/audit.log.jsonl ]]; then
  chmod 600 logs/audit.log.jsonl 2>/dev/null || true
fi

MODE="${1:-all}"
ENV_ARGS=()
if [[ -n "${EXPERT_ENV_FILE:-}" ]]; then
  if [[ ! -f "${EXPERT_ENV_FILE}" ]]; then
    echo "[ERROR] EXPERT_ENV_FILE not found: ${EXPERT_ENV_FILE}" >&2
    exit 2
  fi
  ENV_ARGS=(--env "${EXPERT_ENV_FILE}")
fi

if [[ -n "${EXPERT_CA_BUNDLE:-}" && -f "${EXPERT_CA_BUNDLE}" ]]; then
  cp "${EXPERT_CA_BUNDLE}" /usr/local/share/ca-certificates/expert-custom-ca.crt
  update-ca-certificates >/dev/null 2>&1 || true
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
  export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  export CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
fi

shutdown() {
  echo "[INFO] Stopping services..."
  ./server_control.sh "${ENV_ARGS[@]}" force-stop-all >/dev/null 2>&1 || true
}

trap shutdown INT TERM

case "${MODE}" in
  all|start-all)
    ./server_control.sh "${ENV_ARGS[@]}" force-stop-all >/dev/null 2>&1 || true
    ./server_control.sh "${ENV_ARGS[@]}" start-all
    if compgen -G "logs/*.log" >/dev/null; then
      tail -F logs/*.log &
      wait $!
    else
      while true; do sleep 60; done
    fi
    ;;
  api|web|mcp|a2a)
    ./server_control.sh "${ENV_ARGS[@]}" force-stop-all >/dev/null 2>&1 || true
    ./server_control.sh "${ENV_ARGS[@]}" start "${MODE}"
    if compgen -G "logs/*.log" >/dev/null; then
      tail -F logs/*.log &
      wait $!
    else
      while true; do sleep 60; done
    fi
    ;;
  *)
    echo "Usage: docker-entrypoint.sh [all|start-all|api|web|mcp|a2a]" >&2
    exit 2
    ;;
esac
