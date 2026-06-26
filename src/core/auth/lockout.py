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
Account Lockout Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: In-memory lockout tracking for local authentication.

Config keys:
- auth.lockout_enabled (bool)
- auth.lockout_max_attempts (int)
- auth.lockout_window_seconds (int)
- auth.lockout_seconds (int)

Related Requirements: CS1.1
Related Tests: AT1.35 (extended), UT1.91
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional, Tuple

from src.config.loader import get_config


@dataclass
class _AttemptWindow:
    attempts: List[float]
    locked_until: Optional[float] = None


class LockoutManager:
    """Simple in-memory lockout manager (suitable for single-node local auth)."""

    def __init__(self):
        """Initialise the lockout manager with an empty per-subject attempt map."""
        self._lock = Lock()
        self._by_subject: Dict[str, _AttemptWindow] = {}

    def _cfg(self) -> Tuple[bool, int, int, int]:
        """Resolve lockout config (enabled, max_attempts, window_seconds, lockout_seconds)."""
        raw_enabled = get_config("auth.lockout_enabled", False)
        if isinstance(raw_enabled, str):
            enabled = raw_enabled.strip().lower() in ("1", "true", "yes", "y", "on")
        else:
            enabled = bool(raw_enabled)
        max_attempts = int(get_config("auth.lockout_max_attempts", 5))
        window_seconds = int(get_config("auth.lockout_window_seconds", 300))
        lockout_seconds = int(get_config("auth.lockout_seconds", 300))
        return enabled, max_attempts, window_seconds, lockout_seconds

    def is_locked(self, subject: str) -> bool:
        """Return True if the subject is currently locked out (expired locks auto-clear)."""
        enabled, _, _, _ = self._cfg()
        if not enabled:
            return False
        now = time.time()
        with self._lock:
            state = self._by_subject.get(subject)
            if not state or not state.locked_until:
                return False
            if now >= state.locked_until:
                state.locked_until = None
                state.attempts = []
                return False
            return True

    def register_failure(self, subject: str) -> None:
        """Record a failed attempt; lock the subject once max attempts within the window is reached."""
        enabled, max_attempts, window_seconds, lockout_seconds = self._cfg()
        if not enabled:
            return
        now = time.time()
        with self._lock:
            state = self._by_subject.get(subject)
            if not state:
                state = _AttemptWindow(attempts=[])
                self._by_subject[subject] = state

            # If still locked, keep it locked
            if state.locked_until and now < state.locked_until:
                return

            # Keep only attempts within window
            state.attempts = [t for t in state.attempts if (now - t) <= window_seconds]
            state.attempts.append(now)

            if len(state.attempts) >= max_attempts:
                state.locked_until = now + lockout_seconds

    def register_success(self, subject: str) -> None:
        """Clear any tracked failures/lock for the subject on a successful authentication."""
        enabled, _, _, _ = self._cfg()
        if not enabled:
            return
        with self._lock:
            self._by_subject.pop(subject, None)
