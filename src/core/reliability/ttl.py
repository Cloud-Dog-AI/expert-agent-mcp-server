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
TTL Handler

License: Apache 2.0
Ownership: Cloud Dog
Description: TTL expiry handling for cached data

Related Requirements: FR1.9
Related Tasks: T099
Related Architecture: RR1.4
Related Tests: ST1.16

Recent Changes:
- Initial implementation
"""

import time
from typing import Dict, Any, Optional
from threading import Lock

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TTLHandler:
    """Handles TTL expiry for cached data."""

    def __init__(self):
        """Initialize TTL handler."""
        self.cache: Dict[str, tuple[Any, float]] = {}  # key -> (value, expiry_time)
        self.lock = Lock()

    def set(self, key: str, value: Any, ttl_seconds: int):
        """
        Set value with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds
        """
        with self.lock:
            expiry_time = time.time() + ttl_seconds
            self.cache[key] = (value, expiry_time)
            logger.debug(f"Cached {key} with TTL {ttl_seconds}s")

    def get(self, key: str) -> Optional[Any]:
        """
        Get value if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/not found
        """
        with self.lock:
            if key not in self.cache:
                return None

            value, expiry_time = self.cache[key]

            if time.time() > expiry_time:
                # Expired
                del self.cache[key]
                logger.debug(f"Cache key {key} expired")
                return None

            return value

    def delete(self, key: str):
        """Delete cache key."""
        with self.lock:
            self.cache.pop(key, None)

    def cleanup_expired(self):
        """Remove all expired entries."""
        with self.lock:
            now = time.time()
            expired_keys = [key for key, (_, expiry) in self.cache.items() if now > expiry]
            for key in expired_keys:
                del self.cache[key]

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
