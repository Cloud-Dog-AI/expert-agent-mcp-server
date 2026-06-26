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
Rate Limiter

License: Apache 2.0
Ownership: Cloud Dog
Description: Rate limiting per user/group

Related Requirements: FR1.9
Related Tasks: T096
Related Architecture: RR1.1
Related Tests: ST1.16

Recent Changes:
- Initial implementation
"""

import time
from typing import Dict, Optional
from collections import defaultdict
from threading import Lock

from src.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Rate limiter with per-user/group limits."""

    def __init__(self, default_limit: int = 100, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            default_limit: Default requests per window
            window_seconds: Time window in seconds
        """
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.limits: Dict[str, int] = {}  # user_id/group_id -> limit
        self.requests: Dict[str, list] = defaultdict(list)  # user_id/group_id -> timestamps
        self.lock = Lock()

    def set_limit(self, identifier: str, limit: int):
        """Set rate limit for user/group."""
        self.limits[identifier] = limit

    def is_allowed(self, identifier: str) -> tuple[bool, Optional[int]]:
        """
        Check if request is allowed.

        Args:
            identifier: User ID or group ID

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        with self.lock:
            now = time.time()
            limit = self.limits.get(identifier, self.default_limit)

            # Clean old requests
            cutoff = now - self.window_seconds
            self.requests[identifier] = [ts for ts in self.requests[identifier] if ts > cutoff]

            # Check limit
            if len(self.requests[identifier]) >= limit:
                retry_after = int(self.window_seconds - (now - self.requests[identifier][0]))
                logger.warning(
                    f"Rate limit exceeded for {identifier}: {len(self.requests[identifier])}/{limit}"
                )
                return False, retry_after

            # Record request
            self.requests[identifier].append(now)
            return True, None

    def reset(self, identifier: str):
        """Reset rate limit for identifier."""
        with self.lock:
            self.requests[identifier] = []
