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

"""
Async Callback Mechanisms

License: Apache 2.0
Ownership: Cloud Dog
Description: Callback handling for async operations

Related Requirements: FR1.7, T037
Related Tasks: T037
Related Architecture: AI1.1
Related Tests: UT1.42, ST1.26

Recent Changes:
- Initial implementation
"""

from typing import Dict, Any, Optional

from src.core.http import get_shared_async_client
from src.utils.logger import get_logger
from src.config import get_config

logger = get_logger(__name__)


def _callback_timeout() -> float:
    """Read callback timeout from config (PS-75 JQ7.1, zero hardcoded values)."""
    try:
        return float(get_config("queue.callback_timeout_seconds") or 10)
    except Exception:
        return 10.0


class CallbackManager:
    """Manages callbacks for async operations."""

    def __init__(self):
        """Initialize callback manager."""
        self.registered_callbacks: Dict[int, Dict[str, Any]] = {}  # job_id -> callback info

    def register_callback(
        self,
        job_id: int,
        callback_url: str,
        callback_method: str = "POST",
        callback_headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Register callback for async job.

        Args:
            job_id: Job ID
            callback_url: URL to call when job completes
            callback_method: HTTP method (POST, PUT)
            callback_headers: Optional headers for callback

        Returns:
            True if registered
        """
        self.registered_callbacks[job_id] = {
            "url": callback_url,
            "method": callback_method,
            "headers": callback_headers or {},
        }
        logger.info(f"Registered callback for job {job_id}: {callback_url}")
        return True

    async def trigger_callback(
        self, job_id: int, job_status: str, job_result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Trigger callback for completed job.

        Args:
            job_id: Job ID
            job_status: Job status (completed, failed)
            job_result: Optional job result data

        Returns:
            True if callback triggered successfully
        """
        if job_id not in self.registered_callbacks:
            return False

        callback_info = self.registered_callbacks[job_id]

        payload = {"job_id": job_id, "status": job_status, "result": job_result}

        try:
            cb_timeout = _callback_timeout()
            client = get_shared_async_client(timeout=cb_timeout)
            if callback_info["method"] == "POST":
                response = await client.post(
                    callback_info["url"],
                    json=payload,
                    headers=callback_info["headers"],
                    timeout=cb_timeout,
                )
            elif callback_info["method"] == "PUT":
                response = await client.put(
                    callback_info["url"],
                    json=payload,
                    headers=callback_info["headers"],
                    timeout=cb_timeout,
                )
            else:
                logger.error(f"Unsupported callback method: {callback_info['method']}")
                return False

            response.raise_for_status()
            logger.info(f"Callback triggered for job {job_id}: {response.status_code}")
            return True
        except Exception as e:
            logger.error(f"Failed to trigger callback for job {job_id}: {e}", exc_info=True)
            return False

    def unregister_callback(self, job_id: int) -> bool:
        """Unregister callback for job."""
        if job_id in self.registered_callbacks:
            del self.registered_callbacks[job_id]
            logger.info(f"Unregistered callback for job {job_id}")
            return True
        return False
