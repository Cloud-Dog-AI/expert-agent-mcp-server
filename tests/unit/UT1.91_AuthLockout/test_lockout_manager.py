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
Unit Test: UT1.91 - Auth Lockout Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates lockout behaviour is config-driven and deterministic.

Related Requirements: CS1.1
Related Tests: UT1.91
"""

from __future__ import annotations
import pytest

import time

from src.config.loader import load_config
from src.core.auth.lockout import LockoutManager
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_lockout_disabled_is_noop(monkeypatch, test_env_file):
    load_config.cache_clear()
    monkeypatch.setenv("CLOUD_DOG__EXPERT__AUTH__LOCKOUT_ENABLED", "false")
    load_config.cache_clear()

    lm = LockoutManager()
    subj = "user@example"
    for _ in range(10):
        lm.register_failure(subj)
    assert lm.is_locked(subj) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_lockout_enabled_locks_and_expires(monkeypatch, test_env_file):
    load_config.cache_clear()
    monkeypatch.setenv("CLOUD_DOG__EXPERT__AUTH__LOCKOUT_ENABLED", "true")
    monkeypatch.setenv("CLOUD_DOG__EXPERT__AUTH__LOCKOUT_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("CLOUD_DOG__EXPERT__AUTH__LOCKOUT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("CLOUD_DOG__EXPERT__AUTH__LOCKOUT_SECONDS", "1")
    load_config.cache_clear()

    lm = LockoutManager()
    subj = "user@example"
    lm.register_failure(subj)
    lm.register_failure(subj)
    assert lm.is_locked(subj) is False
    lm.register_failure(subj)
    assert lm.is_locked(subj) is True
    time.sleep(1.2)
    assert lm.is_locked(subj) is False

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]

