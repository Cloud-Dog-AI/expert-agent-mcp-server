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
Unit Test: UT1.92 - Concurrency queue position behaviour

License: Apache 2.0
Ownership: Cloud Dog
Description: Verifies queue position is stable and non-placeholder.
"""

from __future__ import annotations

import pytest
from src.config.loader import get_config, load_config
from src.core.session.concurrency import ConcurrencyManager, QueuePriority
from src.database.models import ExpertConfig
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_queue_position_increments(monkeypatch, test_env_file, db_session):
    # Ensure queue enabled and limits present
    monkeypatch.setenv("CLOUD_DOG__EXPERT__SESSION__QUEUE_ENABLED", "true")
    monkeypatch.setenv("CLOUD_DOG__EXPERT__SESSION__MAX_SESSIONS_PER_USER", "1")
    monkeypatch.setenv("CLOUD_DOG__EXPERT__SESSION__MAX_SESSIONS_PER_GROUP", "1")
    load_config.cache_clear()

    from src.core.auth.user_manager import UserManager

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    user_manager = UserManager(db_session)
    user = user_manager.create_user(
        username=f"{base_username}_ut1_92",
        email=f"ut1_92@{domain}",
        password=password,
    )

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")
    expert = ExpertConfig(
        name="ut1_92_expert",
        title="UT1.92 Expert",
        description="UT1.92 expert configuration for concurrency queue tests.",
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)

    cm = ConcurrencyManager(db_session)
    from src.core.session import concurrency as concurrency_module

    with concurrency_module._QUEUE_LOCK:
        concurrency_module._SESSION_QUEUE.clear()
    e1 = cm.queue_session(
        user_id=user.id, expert_config_id=expert.id, priority=QueuePriority.NORMAL, channel_id=None
    )
    e2 = cm.queue_session(
        user_id=user.id, expert_config_id=expert.id, priority=QueuePriority.NORMAL, channel_id=None
    )
    assert cm.get_queue_position(user.id, e1) == 0
    assert cm.get_queue_position(user.id, e2) == 1

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

