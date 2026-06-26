#!/bin/bash
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

# Track A gate runner: baseline `private/env-test`.
# Runs start -> probes -> pytest files sequentially -> stop in one command.
# This avoids runner environments that reap background processes between commands.

ENV_FILE="${1:-private/env-test}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

./server_control.sh --env "$ENV_FILE" force-stop-all >/dev/null 2>&1 || true
./server_control.sh --env "$ENV_FILE" start-all
sleep 2

echo "== Health Probes (app/env must be present) =="
for u in \
  "http://127.0.0.1:18083/health" \
  "http://127.0.0.1:18080/health" \
  "http://127.0.0.1:18081/health" \
  "http://127.0.0.1:18082/health" \
; do
  echo "-- $u"
  curl --noproxy '*' -fsS -m 5 "$u" | head -c 600
  echo
done

echo "== Pytest Gate (sequential) =="
files=(
  tests/system/ST1.2_MCPServer/test_mcp_modes_compliance.py
  tests/system/ST1.2_MCPServer/test_mcp_tools.py
  tests/system/ST1.3_A2AServer/test_a2a_websocket.py
  tests/system/ST1.4_WebUIServer/test_web_ui.py
  tests/integration/IT2.5_A2AProtocol/test_cross_interface_parity.py
  tests/system/ST1.30_VectorBackends/test_vector_backend_crud.py
)

rc=0
for f in "${files[@]}"; do
  echo "===== RUN $f ====="
  ./venv/bin/python -m pytest --env "$ENV_FILE" -q "$f"
  c=$?
  echo "===== RC $c $f ====="
  if [ $c -ne 0 ]; then
    rc=1
  fi
done

./server_control.sh --env "$ENV_FILE" force-stop-all >/dev/null 2>&1 || true
exit $rc
