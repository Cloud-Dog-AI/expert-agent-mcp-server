#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 || "$1" != "--env" ]]; then
  echo "Usage: $0 --env <env-file> <pytest args...>" >&2
  echo "Example: $0 --env tests/env-AT tests/application/AT1.102_ResponseQualityEvaluation/ -x -q" >&2
  exit 2
fi

ENV_FILE="$2"
shift 2

ATTEMPTS="${TEST_RETRY_ATTEMPTS:-2}"
DELAY_SECONDS="${TEST_RETRY_DELAY_SECONDS:-15}"

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

rc=1
for ((attempt=1; attempt<=ATTEMPTS; attempt++)); do
  echo "[INFO] Attempt ${attempt}/${ATTEMPTS}: pytest --env ${ENV_FILE} $*"
  echo "[INFO] Sequential lock is managed by tests/conftest.py"

  ./server_control.sh --env "$ENV_FILE" force-stop-all >/dev/null 2>&1 || true

  set +e
  "$PYTHON_BIN" -m pytest "$@" --env "$ENV_FILE"
  rc=$?
  set -e

  if [[ $rc -eq 0 ]]; then
    echo "[INFO] PASS on attempt ${attempt}" 
    ./server_control.sh --env "$ENV_FILE" stop-all >/dev/null 2>&1 || true
    exit 0
  fi

  echo "[WARN] Attempt ${attempt} failed with rc=${rc}"
  ./server_control.sh --env "$ENV_FILE" force-stop-all >/dev/null 2>&1 || true

  if [[ $attempt -lt $ATTEMPTS ]]; then
    sleep "$DELAY_SECONDS"
  fi
done

echo "[ERROR] All ${ATTEMPTS} attempts failed (last rc=${rc})" >&2
exit "$rc"
