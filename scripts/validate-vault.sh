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

required=(VAULT_ADDR VAULT_TOKEN VAULT_MOUNT_POINT VAULT_CONFIG_PATH)
missing=0
for key in "${required[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    echo "MISSING: $key"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "Vault bootstrap variables are incomplete."
  exit 1
fi

echo "Vault bootstrap variables present."

# Optional lightweight connectivity probe using Python stdlib (no secret output).
python3 - <<'PY'
import os
import urllib.request
import urllib.error
addr=os.environ.get('VAULT_ADDR','').rstrip('/')
url=f"{addr}/v1/sys/health"
req=urllib.request.Request(url, method='GET')
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        code=resp.getcode()
except urllib.error.HTTPError as e:
    code=e.code
except Exception as e:
    print(f"Vault health probe failed: {e}")
    raise SystemExit(1)
if code in (200,429,472,473,501,503):
    print(f"Vault health endpoint reachable (HTTP {code}).")
else:
    print(f"Unexpected Vault health status: {code}")
    raise SystemExit(1)
PY
