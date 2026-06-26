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
AT1.59 - Channel Chat with History Scopes Integration

This test suite validates channel chat functionality with different history scopes
(user, channel, session). Tests ensure proper history retrieval and context management
across different scope levels.

RULES.md Compliance:
- TestOutputManager for comprehensive logging
- API-only operations (no direct DB access)
- No hardcoded values (all from config)
- Full cleanup via API DELETE endpoints
- Real LLM integration with history validation
"""

import pytest
import uuid
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.application.test_helpers_common import (  # noqa: E402
    build_test_email,
    create_api_client_fixture,
    get_admin_api_key,
    get_config,
)

# Import TestOutputManager from AT1.58
sys.path.insert(0, str(Path(__file__).parent.parent / "AT1.58_ChannelChatVectorStoreRAG"))
from test_AT1_58_real import TestOutputManager  # noqa: E402


# Fixtures
@pytest.fixture
def api_client():
    """Create API client for tests with 120s timeout."""
    client = create_api_client_fixture()()
    # Force 120s timeout for all requests
    client.session.request = lambda method, url, **kwargs: client.session.__class__.request(
        client.session,
        method,
        url,
        timeout=120,
        **{k: v for k, v in kwargs.items() if k != "timeout"},
    )
    return client


@pytest.fixture
def test_expert(api_client):
    """Create test expert configuration."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    expert_data = {
        "name": f"AT1.59 History Expert {uuid.uuid4().hex[:8]}",
        "title": f"AT1.59 History Expert {uuid.uuid4().hex[:8]}",
        "description": "Test expert for channel chat with history scopes",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create expert: {response.text}"
    expert = response.json()

    yield expert

    api_client.delete(f"/experts/{expert['id']}")
    api_client.session.headers.pop("X-API-Key", None)


@pytest.fixture
def test_channel(api_client, test_expert):
    """Create test channel with user scope."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    channel_data = {
        "name": f"AT1.59 History Channel {uuid.uuid4().hex[:8]}",
        "expert_config_id": test_expert["id"],
        "description": "Test channel for history scope testing",
        "history_scope": "user",
        "enabled": True,
    }

    response = api_client.post("/channels", json=channel_data)
    assert response.status_code == 200, f"Failed to create channel: {response.text}"
    channel = response.json()

    yield channel

    api_client.delete(f"/channels/{channel['id']}")
    api_client.session.headers.pop("X-API-Key", None)


@pytest.fixture
def test_user(api_client):
    """Create test user."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    user_data = {
        "username": f"testuser_at1_59_{uuid.uuid4().hex[:8]}",
        "email": build_test_email("at1_59", uuid.uuid4().hex[:8]),
        "display_name": f"AT1.59 Test User {uuid.uuid4().hex[:8]}",
        "role": "user",
        "enabled": True,
        "password": None,
    }

    response = api_client.post("/users", json=user_data)
    assert response.status_code == 200, f"Failed to create user: {response.text}"
    user = response.json()

    yield user

    api_client.session.headers.pop("X-API-Key", None)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_59a_channel_chat_user_scope_history(api_client, test_channel, test_user, test_expert):
    """AT1.59a: Channel chat with user-scoped history"""
    mgr = TestOutputManager("AT1_59a_channel_chat_user_scope_history")
    mgr.log_console("TEST START: AT1.59a - User Scope History")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create first session
    session_data_1 = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.59a Session 1 {uuid.uuid4()}",
    }
    session_response_1 = api_client.post("/sessions", json=session_data_1)
    mgr.validate(
        "session_1_created",
        session_response_1.status_code == 200,
        session_response_1.status_code,
        200,
        "First session created",
    )

    if session_response_1.status_code == 200:
        session_1 = session_response_1.json()

        # Send message in first session
        chat_data_1 = {
            "message": "My favorite color is blue.",
            "user_id": test_user["id"],
            "session_id": session_1["id"],
            "mode": "sync",
        }
        mgr.save_input("chat_session_1", chat_data_1)
        chat_response_1 = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data_1)
        mgr.save_output("chat_session_1", chat_response_1)
        mgr.validate(
            "chat_1_success",
            chat_response_1.status_code == 200,
            chat_response_1.status_code,
            200,
            "First chat successful",
        )

        # Create second session (same user)
        session_data_2 = {
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.59a Session 2 {uuid.uuid4()}",
        }
        session_response_2 = api_client.post("/sessions", json=session_data_2)
        mgr.validate(
            "session_2_created",
            session_response_2.status_code == 200,
            session_response_2.status_code,
            200,
            "Second session created",
        )

        if session_response_2.status_code == 200:
            session_2 = session_response_2.json()

            # Verify user history includes both sessions
            history_params = {"scope": "user", "user_id": test_user["id"]}
            history_response = api_client.get(
                f"/channels/{test_channel['id']}/history", params=history_params
            )
            mgr.save_output("user_history", history_response)
            mgr.validate(
                "history_retrieved",
                history_response.status_code == 200,
                history_response.status_code,
                200,
                "User history retrieved",
            )

            if history_response.status_code == 200:
                history = history_response.json()
                mgr.validate(
                    "has_messages",
                    len(history.get("messages", [])) >= 2,
                    len(history.get("messages", [])),
                    ">=2",
                    "User history contains messages from session 1",
                )

            # Cleanup
            api_client.delete(f"/sessions/{session_2['id']}")

        api_client.delete(f"/sessions/{session_1['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_59b_channel_chat_session_scope_isolation(api_client, test_user, test_expert):
    """AT1.59b: Channel chat with session-scoped history isolation"""
    mgr = TestOutputManager("AT1_59b_channel_chat_session_scope_isolation")
    mgr.log_console("TEST START: AT1.59b - Session Scope Isolation")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create channel with session scope
    channel_data = {
        "name": f"AT1.59b Session Channel {uuid.uuid4().hex[:8]}",
        "expert_config_id": test_expert["id"],
        "description": "Test channel for session scope",
        "history_scope": "session",
        "enabled": True,
    }
    channel_response = api_client.post("/channels", json=channel_data)
    mgr.validate(
        "channel_created",
        channel_response.status_code == 200,
        channel_response.status_code,
        200,
        "Channel created",
    )

    if channel_response.status_code == 200:
        channel = channel_response.json()

        # Create two sessions
        session_data_1 = {
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.59b Session 1 {uuid.uuid4()}",
        }
        session_response_1 = api_client.post("/sessions", json=session_data_1)

        session_data_2 = {
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.59b Session 2 {uuid.uuid4()}",
        }
        session_response_2 = api_client.post("/sessions", json=session_data_2)

        mgr.validate(
            "sessions_created",
            session_response_1.status_code == 200 and session_response_2.status_code == 200,
            f"{session_response_1.status_code},{session_response_2.status_code}",
            "200,200",
            "Both sessions created",
        )

        if session_response_1.status_code == 200 and session_response_2.status_code == 200:
            session_1 = session_response_1.json()
            session_2 = session_response_2.json()

            # Send message in session 1
            chat_data_1 = {
                "message": "Session 1 message",
                "user_id": test_user["id"],
                "session_id": session_1["id"],
                "mode": "sync",
            }
            chat_response_1 = api_client.post(f"/channels/{channel['id']}/chat", json=chat_data_1)
            mgr.validate(
                "chat_1_success",
                chat_response_1.status_code == 200,
                chat_response_1.status_code,
                200,
                "Session 1 chat successful",
            )

            # Verify session 1 history
            history_params_1 = {"scope": "session", "session_id": session_1["id"]}
            history_response_1 = api_client.get(
                f"/channels/{channel['id']}/history", params=history_params_1
            )
            mgr.save_output("session_1_history", history_response_1)

            if history_response_1.status_code == 200:
                history_1 = history_response_1.json()
                mgr.validate(
                    "session_1_has_messages",
                    len(history_1.get("messages", [])) >= 2,
                    len(history_1.get("messages", [])),
                    ">=2",
                    "Session 1 has its messages",
                )

            # Verify session 2 history is empty
            history_params_2 = {"scope": "session", "session_id": session_2["id"]}
            history_response_2 = api_client.get(
                f"/channels/{channel['id']}/history", params=history_params_2
            )
            mgr.save_output("session_2_history", history_response_2)

            if history_response_2.status_code == 200:
                history_2 = history_response_2.json()
                mgr.validate(
                    "session_2_isolated",
                    len(history_2.get("messages", [])) == 0,
                    len(history_2.get("messages", [])),
                    0,
                    "Session 2 has no messages (isolated)",
                )

            # Cleanup
            api_client.delete(f"/sessions/{session_1['id']}")
            api_client.delete(f"/sessions/{session_2['id']}")

        api_client.delete(f"/channels/{channel['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_59c_channel_chat_channel_scope_aggregation(api_client, test_user, test_expert):
    """AT1.59c: Channel chat with channel-scoped history aggregation"""
    mgr = TestOutputManager("AT1_59c_channel_chat_channel_scope_aggregation")
    mgr.log_console("TEST START: AT1.59c - Channel Scope Aggregation")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create channel with channel scope
    channel_data = {
        "name": f"AT1.59c Channel Scope {uuid.uuid4().hex[:8]}",
        "expert_config_id": test_expert["id"],
        "description": "Test channel for channel scope",
        "history_scope": "channel",
        "enabled": True,
    }
    channel_response = api_client.post("/channels", json=channel_data)
    mgr.validate(
        "channel_created",
        channel_response.status_code == 200,
        channel_response.status_code,
        200,
        "Channel created",
    )

    if channel_response.status_code == 200:
        channel = channel_response.json()

        # Create two sessions
        session_data_1 = {
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.59c Session 1 {uuid.uuid4()}",
        }
        session_response_1 = api_client.post("/sessions", json=session_data_1)

        session_data_2 = {
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.59c Session 2 {uuid.uuid4()}",
        }
        session_response_2 = api_client.post("/sessions", json=session_data_2)

        if session_response_1.status_code == 200 and session_response_2.status_code == 200:
            session_1 = session_response_1.json()
            session_2 = session_response_2.json()

            # Send messages in both sessions
            chat_data_1 = {
                "message": "Message from session 1",
                "user_id": test_user["id"],
                "session_id": session_1["id"],
                "mode": "sync",
            }
            chat_response_1 = api_client.post(f"/channels/{channel['id']}/chat", json=chat_data_1)
            mgr.validate(
                "chat_1_success",
                chat_response_1.status_code == 200,
                chat_response_1.status_code,
                200,
                "Session 1 chat successful",
            )

            chat_data_2 = {
                "message": "Message from session 2",
                "user_id": test_user["id"],
                "session_id": session_2["id"],
                "mode": "sync",
            }
            chat_response_2 = api_client.post(f"/channels/{channel['id']}/chat", json=chat_data_2)
            mgr.validate(
                "chat_2_success",
                chat_response_2.status_code == 200,
                chat_response_2.status_code,
                200,
                "Session 2 chat successful",
            )

            # Verify channel history includes both sessions
            history_params = {"scope": "channel"}
            history_response = api_client.get(
                f"/channels/{channel['id']}/history", params=history_params
            )
            mgr.save_output("channel_history", history_response)
            mgr.validate(
                "history_retrieved",
                history_response.status_code == 200,
                history_response.status_code,
                200,
                "Channel history retrieved",
            )

            if history_response.status_code == 200:
                history = history_response.json()
                mgr.validate(
                    "aggregated_messages",
                    len(history.get("messages", [])) >= 4,
                    len(history.get("messages", [])),
                    ">=4",
                    "Channel history aggregates both sessions",
                )

            # Cleanup
            api_client.delete(f"/sessions/{session_1['id']}")
            api_client.delete(f"/sessions/{session_2['id']}")

        api_client.delete(f"/channels/{channel['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_59d_channel_chat_history_pagination(api_client, test_channel, test_user, test_expert):
    """AT1.59d: Channel chat with history pagination"""
    mgr = TestOutputManager("AT1_59d_channel_chat_history_pagination")
    mgr.log_console("TEST START: AT1.59d - History Pagination")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.59d Test Session {uuid.uuid4()}",
    }
    session_response = api_client.post("/sessions", json=session_data)
    mgr.validate(
        "session_created",
        session_response.status_code == 200,
        session_response.status_code,
        200,
        "Session created",
    )

    if session_response.status_code == 200:
        session = session_response.json()

        # Send multiple messages
        for i in range(5):
            chat_data = {
                "message": f"Test message {i + 1}",
                "user_id": test_user["id"],
                "session_id": session["id"],
                "mode": "sync",
            }
            chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
            mgr.validate(
                f"chat_{i + 1}_success",
                chat_response.status_code == 200,
                chat_response.status_code,
                200,
                f"Message {i + 1} sent",
            )

        # Test pagination - first page
        history_params_1 = {"scope": "channel", "limit": 5, "offset": 0}
        history_response_1 = api_client.get(
            f"/channels/{test_channel['id']}/history", params=history_params_1
        )
        mgr.save_output("history_page_1", history_response_1)
        mgr.validate(
            "page_1_retrieved",
            history_response_1.status_code == 200,
            history_response_1.status_code,
            200,
            "First page retrieved",
        )

        if history_response_1.status_code == 200:
            history_1 = history_response_1.json()
            mgr.validate(
                "page_1_limit",
                len(history_1.get("messages", [])) <= 5,
                len(history_1.get("messages", [])),
                "<=5",
                "First page respects limit",
            )
            mgr.validate(
                "has_pagination_meta",
                "limit" in history_1 and "offset" in history_1,
                f"limit:{history_1.get('limit')},offset:{history_1.get('offset')}",
                "present",
                "Pagination metadata present",
            )

        # Test pagination - second page
        history_params_2 = {"scope": "channel", "limit": 5, "offset": 5}
        history_response_2 = api_client.get(
            f"/channels/{test_channel['id']}/history", params=history_params_2
        )
        mgr.save_output("history_page_2", history_response_2)
        mgr.validate(
            "page_2_retrieved",
            history_response_2.status_code == 200,
            history_response_2.status_code,
            200,
            "Second page retrieved",
        )

        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_59e_channel_chat_cross_user_isolation(api_client, test_channel, test_expert):
    """AT1.59e: Channel chat with cross-user history isolation"""
    mgr = TestOutputManager("AT1_59e_channel_chat_cross_user_isolation")
    mgr.log_console("TEST START: AT1.59e - Cross-User Isolation")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create two users
    user_data_1 = {
        "username": f"testuser1_at1_59e_{uuid.uuid4().hex[:8]}",
        "email": build_test_email("at1_59e_user1", uuid.uuid4().hex[:8]),
        "display_name": f"AT1.59e Test User 1 {uuid.uuid4().hex[:8]}",
        "role": "user",
        "enabled": True,
        "password": None,
    }
    user_response_1 = api_client.post("/users", json=user_data_1)

    user_data_2 = {
        "username": f"testuser2_at1_59e_{uuid.uuid4().hex[:8]}",
        "email": build_test_email("at1_59e_user2", uuid.uuid4().hex[:8]),
        "display_name": f"AT1.59e Test User 2 {uuid.uuid4().hex[:8]}",
        "role": "user",
        "enabled": True,
        "password": None,
    }
    user_response_2 = api_client.post("/users", json=user_data_2)

    mgr.validate(
        "users_created",
        user_response_1.status_code == 200 and user_response_2.status_code == 200,
        f"{user_response_1.status_code},{user_response_2.status_code}",
        "200,200",
        "Both users created",
    )

    if user_response_1.status_code == 200 and user_response_2.status_code == 200:
        user_1 = user_response_1.json()
        user_2 = user_response_2.json()

        # Create sessions for both users
        session_data_1 = {
            "user_id": user_1["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.59e User 1 Session {uuid.uuid4()}",
        }
        session_response_1 = api_client.post("/sessions", json=session_data_1)

        session_data_2 = {
            "user_id": user_2["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.59e User 2 Session {uuid.uuid4()}",
        }
        session_response_2 = api_client.post("/sessions", json=session_data_2)

        if session_response_1.status_code == 200 and session_response_2.status_code == 200:
            session_1 = session_response_1.json()
            session_2 = session_response_2.json()

            # User 1 sends message
            chat_data_1 = {
                "message": "User 1 private message",
                "user_id": user_1["id"],
                "session_id": session_1["id"],
                "mode": "sync",
            }
            chat_response_1 = api_client.post(
                f"/channels/{test_channel['id']}/chat", json=chat_data_1
            )
            mgr.validate(
                "user_1_chat_success",
                chat_response_1.status_code == 200,
                chat_response_1.status_code,
                200,
                "User 1 chat successful",
            )

            # Verify user 2 cannot see user 1's history
            history_params_2 = {"scope": "user", "user_id": user_2["id"]}
            history_response_2 = api_client.get(
                f"/channels/{test_channel['id']}/history", params=history_params_2
            )
            mgr.save_output("user_2_history", history_response_2)

            if history_response_2.status_code == 200:
                history_2 = history_response_2.json()
                mgr.validate(
                    "user_2_isolated",
                    len(history_2.get("messages", [])) == 0,
                    len(history_2.get("messages", [])),
                    0,
                    "User 2 cannot see User 1's messages",
                )

            # Cleanup
            api_client.delete(f"/sessions/{session_1['id']}")
            api_client.delete(f"/sessions/{session_2['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
