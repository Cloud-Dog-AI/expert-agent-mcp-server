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
Backoff Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Exponential backoff with jitter for retries

Related Requirements: FR1.9
Related Tasks: T098
Related Architecture: RR1.3
Related Tests: ST1.16

Recent Changes:
- Initial implementation
"""

import random
import time
import asyncio

from src.utils.logger import get_logger

logger = get_logger(__name__)


class BackoffManager:
    """Manages exponential backoff with jitter."""

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: bool = True,
    ):
        """
        Initialize backoff manager.

        Args:
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            multiplier: Exponential multiplier
            jitter: Whether to add random jitter
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        Get delay for attempt number.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = self.initial_delay * (self.multiplier**attempt)
        delay = min(delay, self.max_delay)

        # Add jitter if enabled
        if self.jitter:
            jitter_amount = delay * 0.1  # 10% jitter
            delay += random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay)  # Ensure non-negative

        return delay

    async def wait(self, attempt: int):
        """Wait for the calculated delay."""
        delay = self.get_delay(attempt)
        logger.debug(f"Backoff: waiting {delay:.2f}s before attempt {attempt + 1}")
        await asyncio.sleep(delay)

    def retry(self, func, max_attempts: int = 3, *args, **kwargs):
        """
        Retry function with exponential backoff.

        Args:
            func: Function to retry
            max_attempts: Maximum number of attempts
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If all attempts fail
        """
        last_exception = None

        for attempt in range(max_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    delay = self.get_delay(attempt)
                    time.sleep(delay)
                else:
                    logger.error(f"All {max_attempts} attempts failed")

        raise last_exception
