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
**************************************************
License: Apache 2.0
Ownership: Cloud Dog
Description: Unit tests for knowledge versioning/rollback.
**************************************************
"""

from __future__ import annotations

import pytest

from src.core.knowledge.manager import KnowledgeHistoryManager
from src.config.loader import get_config
from src.core.auth.user_manager import UserManager


@pytest.fixture
def test_user(db_session):
    manager = UserManager(db_session)
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
    return manager.create_user(
        username=f"{base_username}_ut1_93",
        email=f"ut1_93@{domain}",
        password=password,
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_UT1_93_knowledge_versions_increment_and_rollback(db_session, test_user):
    manager = KnowledgeHistoryManager(db_session)

    user_id = test_user.id
    knowledge_type = "user"
    knowledge_id = user_id

    manager.list_versions(user_id=user_id, knowledge_type=knowledge_type, knowledge_id=knowledge_id)
    # Ensure we can always query versions (initial auto-created on first history read)
    manager.get_knowledge_history(
        user_id=user_id, knowledge_type=knowledge_type, knowledge_id=knowledge_id
    )

    manager.add_knowledge(
        user_id=user_id,
        knowledge_type=knowledge_type,
        knowledge_id=knowledge_id,
        content="one",
        metadata={"x": 1},
    )
    manager.add_knowledge(
        user_id=user_id,
        knowledge_type=knowledge_type,
        knowledge_id=knowledge_id,
        content="two",
        metadata={"x": 2},
    )

    versions = manager.list_versions(
        user_id=user_id, knowledge_type=knowledge_type, knowledge_id=knowledge_id
    )
    assert len(versions) >= 3
    assert any(v.get("is_current") for v in versions)

    # Roll back to version 2 -> should not include "two"
    assert (
        manager.rollback(
            user_id=user_id, knowledge_type=knowledge_type, knowledge_id=knowledge_id, version=2
        )
        is True
    )
    hist = manager.get_knowledge_history(
        user_id=user_id, knowledge_type=knowledge_type, knowledge_id=knowledge_id
    )
    contents = [h["content"] for h in hist]
    assert "one" in contents
    assert "two" not in contents

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

