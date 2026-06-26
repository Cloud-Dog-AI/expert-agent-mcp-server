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

"""code-runner A2A consumer client (W28I-1218).

Sends ``code.execute`` requests to the code-runner service over A2A so the
expert agent can use it as an analyst reasoning tool ("run this code to
compute / verify"). Follows the existing outbound-HTTP pattern used by
``ServiceCompositionManager``:

* reuses the process-wide shared ``httpx.AsyncClient``
  (``src.core.http.get_shared_async_client``);
* resolves the target host + API key from the standard config hierarchy
  (``get_config('code_runner.*')``) so secrets are env-injected, never
  hardcoded;
* propagates the expert agent's correlation id to code-runner via the
  ``X-Correlation-Id`` header so the producer's audit can be linked.

Producer contract (live, verified):
    POST <base_url>/a2a/tasks
    headers: X-API-Key: <key>, content-type: application/json
    body:    {"task_id": "<id>", "skill_id": "code.execute",
              "input": {"code": "<code>", "language": "python"|"node"}}
    resp:    {"status": "completed"|"failed",
              "result": {"stdout", "stderr", "exit_code", "duration_ms", ...}}

Related Requirements: FR1.15, UC1.10
Related Tasks: W28I-1218
Related Architecture: CC8.1.1
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

import httpx

from src.config.loader import get_config
from src.core.http import get_shared_async_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

SKILL_ID = "code.execute"
_SUPPORTED_LANGUAGES = ("python", "node")


def _resolve_correlation_id(explicit: Optional[str]) -> Optional[str]:
    """Resolve the correlation id to forward to code-runner.

    Prefers an explicitly supplied value, otherwise falls back to the active
    request's correlation id from the platform correlation context (the same
    context populated by the API server's correlation middleware).
    """
    if explicit:
        return str(explicit)
    try:
        from cloud_dog_api_kit.correlation.context import get_correlation_id

        active = get_correlation_id()
        return str(active) if active else None
    except Exception:  # pragma: no cover - context import/availability guard
        return None


class CodeRunnerClient:
    """A2A client for the code-runner ``code.execute`` skill."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client

    # -- config resolution ------------------------------------------------

    @staticmethod
    def _base_url() -> str:
        base_url = get_config("code_runner.base_url")
        if not base_url or not str(base_url).strip():
            raise RuntimeError("code_runner.base_url is not configured")
        return str(base_url).strip().rstrip("/")

    @staticmethod
    def _api_key() -> str:
        api_key = get_config("code_runner.api_key")
        if not api_key or not str(api_key).strip():
            raise RuntimeError("code_runner.api_key is not configured")
        return str(api_key).strip()

    @staticmethod
    def _timeout_seconds() -> float:
        raw = get_config("code_runner.timeout_seconds")
        try:
            timeout = float(raw)
        except (TypeError, ValueError):
            timeout = 60.0
        return timeout if timeout > 0 else 60.0

    @staticmethod
    def _verify_tls() -> bool:
        raw = get_config("code_runner.verify_tls")
        if raw is None:
            return True
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _default_language() -> str:
        lang = str(get_config("code_runner.default_language") or "python").strip().lower()
        return lang if lang in _SUPPORTED_LANGUAGES else "python"

    def _tasks_url(self) -> str:
        base = self._base_url()
        if base.endswith("/a2a"):
            return f"{base}/tasks"
        return f"{base}/a2a/tasks"

    def _resolve_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return get_shared_async_client(
            timeout=self._timeout_seconds(),
            verify=self._verify_tls(),
        )

    # -- invocation -------------------------------------------------------

    async def execute(
        self,
        code: str,
        language: Optional[str] = None,
        *,
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run ``code`` on the code-runner service over A2A.

        Args:
            code: Source code to execute.
            language: ``"python"`` or ``"node"`` (defaults to config value).
            task_id: Optional caller-supplied A2A task id (auto-generated if
                omitted).
            correlation_id: Optional explicit correlation id; when omitted the
                active platform correlation id is forwarded.

        Returns:
            A normalised dict with ``status`` ("completed"/"failed"), the
            producer ``result`` payload (stdout/stderr/exit_code/duration_ms),
            and the ``task_id`` / ``correlation_id`` used for the call.
        """
        if not code or not str(code).strip():
            raise ValueError("code must be a non-empty string")

        resolved_language = str(language or self._default_language()).strip().lower()
        if resolved_language not in _SUPPORTED_LANGUAGES:
            raise ValueError(
                f"unsupported language '{resolved_language}'; "
                f"expected one of {_SUPPORTED_LANGUAGES}"
            )

        resolved_task_id = str(task_id or uuid.uuid4())
        resolved_correlation_id = _resolve_correlation_id(correlation_id)

        headers: Dict[str, str] = {
            "X-API-Key": self._api_key(),
            "content-type": "application/json",
            "Accept": "application/json",
        }
        if resolved_correlation_id:
            headers["X-Correlation-Id"] = resolved_correlation_id

        payload: Dict[str, Any] = {
            "task_id": resolved_task_id,
            "skill_id": SKILL_ID,
            "input": {"code": str(code), "language": resolved_language},
        }

        client = self._resolve_client()
        try:
            response = await client.post(
                self._tasks_url(),
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds(),
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            logger.warning(
                "code-runner code.execute failed task_id=%s correlation_id=%s: %s",
                resolved_task_id,
                resolved_correlation_id,
                exc,
            )
            return {
                "status": "failed",
                "task_id": resolved_task_id,
                "correlation_id": resolved_correlation_id,
                "skill_id": SKILL_ID,
                "language": resolved_language,
                "error": str(exc),
                "result": {},
            }

        status = str(body.get("status") or "completed")
        result = body.get("result")
        if not isinstance(result, dict):
            result = {}

        return {
            "status": status,
            "task_id": resolved_task_id,
            "correlation_id": resolved_correlation_id,
            "skill_id": SKILL_ID,
            "language": resolved_language,
            "result": result,
        }
