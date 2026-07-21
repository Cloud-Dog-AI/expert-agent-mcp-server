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

# Probe API and Web servers in parallel. Both must respond for Traefik to
# route correctly. MCP and A2A are excluded — they run on dedicated entrypoints
# and don't affect SPA/auth/login routing on the websecure entrypoint.
API_HOST="${CLOUD_DOG__EXPERT__API_SERVER__HOST:?CLOUD_DOG__EXPERT__API_SERVER__HOST missing}"
API_PORT="${CLOUD_DOG__EXPERT__API_SERVER__PORT:?CLOUD_DOG__EXPERT__API_SERVER__PORT missing}"
WEB_HOST="${CLOUD_DOG__EXPERT__WEB_SERVER__HOST:?CLOUD_DOG__EXPERT__WEB_SERVER__HOST missing}"
WEB_PORT="${CLOUD_DOG__EXPERT__WEB_SERVER__PORT:?CLOUD_DOG__EXPERT__WEB_SERVER__PORT missing}"

normalise_probe_host() {
    case "$1" in
        0.0.0.0|::) printf '127.0.0.1' ;;
        *) printf '%s' "$1" ;;
    esac
}

API_PROBE_HOST="$(normalise_probe_host "$API_HOST")"
WEB_PROBE_HOST="$(normalise_probe_host "$WEB_HOST")"

# Run both probes in parallel to stay within Docker --timeout=45s.
curl --max-time 15 --noproxy '*' -fsS "http://${API_PROBE_HOST}:${API_PORT}/health" >/dev/null &
API_PROBE_PID=$!
curl --max-time 15 --noproxy '*' -fsS "http://${WEB_PROBE_HOST}:${WEB_PORT}/health" >/dev/null &
WEB_PROBE_PID=$!

# A bare `wait` can reap all children without preserving every failing status.
# Capture both results explicitly so a partially started container is unhealthy.
API_PROBE_OK=0
WEB_PROBE_OK=0
if wait "$API_PROBE_PID"; then API_PROBE_OK=1; fi
if wait "$WEB_PROBE_PID"; then WEB_PROBE_OK=1; fi
test "$API_PROBE_OK" -eq 1
test "$WEB_PROBE_OK" -eq 1
