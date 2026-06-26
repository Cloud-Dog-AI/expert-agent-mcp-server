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
AT1.60 - Channel Chat Error Handling & Edge Cases

This test suite validates channel chat error handling, edge cases, and robustness.
Tests ensure proper error responses, validation, and graceful degradation.

RULES.md Compliance:
- TestOutputManager for comprehensive logging
- API-only operations (no direct DB access)
- No hardcoded values (all from config)
- Full cleanup via API DELETE endpoints
- Comprehensive error scenario coverage
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
    """Create API client for tests."""
    return create_api_client_fixture()()


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
        "name": f"AT1.60 Error Expert {uuid.uuid4().hex[:8]}",
        "title": f"AT1.60 Error Expert {uuid.uuid4().hex[:8]}",
        "description": "Test expert for channel chat error handling",
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
    """Create test channel."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    channel_data = {
        "name": f"AT1.60 Error Channel {uuid.uuid4().hex[:8]}",
        "expert_config_id": test_expert["id"],
        "description": "Test channel for error handling",
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
        "username": f"testuser_at1_60_{uuid.uuid4().hex[:8]}",
        "email": build_test_email("at1_60", uuid.uuid4().hex[:8]),
        "display_name": f"AT1.60 Test User {uuid.uuid4().hex[:8]}",
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


def test_AT1_60a_channel_chat_invalid_channel(api_client, test_user, test_expert):
    """AT1.60a: Channel chat with invalid channel ID"""
    mgr = TestOutputManager("AT1_60a_channel_chat_invalid_channel")
    mgr.log_console("TEST START: AT1.60a - Invalid Channel ID")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.60a Test Session {uuid.uuid4()}",
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

        # Try to chat with invalid channel ID
        invalid_channel_id = 999999
        chat_data = {
            "message": "Test message",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input("chat_invalid_channel", chat_data)

        chat_response = api_client.post(f"/channels/{invalid_channel_id}/chat", json=chat_data)
        mgr.save_output("chat_invalid_channel", chat_response)

        mgr.validate(
            "error_status",
            chat_response.status_code == 404,
            chat_response.status_code,
            404,
            "Returns 404 for invalid channel",
        )
        mgr.validate(
            "has_error_detail",
            "detail" in chat_response.json() if chat_response.status_code >= 400 else False,
            "detail" in chat_response.json() if chat_response.status_code >= 400 else False,
            True,
            "Error response has detail",
        )

        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_60b_channel_chat_invalid_session(api_client, test_channel, test_user):
    """AT1.60b: Channel chat with invalid session ID"""
    mgr = TestOutputManager("AT1_60b_channel_chat_invalid_session")
    mgr.log_console("TEST START: AT1.60b - Invalid Session ID")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Try to chat with invalid session ID
    invalid_session_id = 999999
    chat_data = {
        "message": "Test message",
        "user_id": test_user["id"],
        "session_id": invalid_session_id,
        "mode": "sync",
    }
    mgr.save_input("chat_invalid_session", chat_data)

    chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
    mgr.save_output("chat_invalid_session", chat_response)

    mgr.validate(
        "error_status",
        chat_response.status_code in [404, 400],
        chat_response.status_code,
        "404 or 400",
        "Returns error for invalid session",
    )
    mgr.validate(
        "has_error_detail",
        "detail" in chat_response.json() if chat_response.status_code >= 400 else False,
        "detail" in chat_response.json() if chat_response.status_code >= 400 else False,
        True,
        "Error response has detail",
    )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_60c_channel_chat_empty_message(api_client, test_channel, test_user, test_expert):
    """AT1.60c: Channel chat with empty message"""
    mgr = TestOutputManager("AT1_60c_channel_chat_empty_message")
    mgr.log_console("TEST START: AT1.60c - Empty Message")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.60c Test Session {uuid.uuid4()}",
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

        # Try to send empty message
        chat_data = {
            "message": "",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input("chat_empty_message", chat_data)

        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("chat_empty_message", chat_response)

        mgr.validate(
            "error_status",
            chat_response.status_code in [400, 422],
            chat_response.status_code,
            "400 or 422",
            "Returns validation error for empty message",
        )

        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_60d_channel_chat_missing_required_fields(api_client, test_channel, test_user):
    """AT1.60d: Channel chat with missing required fields"""
    mgr = TestOutputManager("AT1_60d_channel_chat_missing_required_fields")
    mgr.log_console("TEST START: AT1.60d - Missing Required Fields")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Try to chat without message field
    chat_data = {"user_id": test_user["id"], "mode": "sync"}
    mgr.save_input("chat_no_message", chat_data)

    chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
    mgr.save_output("chat_no_message", chat_response)

    # API might return 422 or 400 for missing fields
    mgr.validate(
        "error_status",
        chat_response.status_code in [400, 422],
        chat_response.status_code,
        "400/422",
        "Returns error for missing required field",
    )

    # Try to chat without user_id
    chat_data_2 = {"message": "Test message", "mode": "sync"}
    mgr.save_input("chat_no_user_id", chat_data_2)

    chat_response_2 = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data_2)
    mgr.save_output("chat_no_user_id", chat_response_2)

    # API might return 422, 400, or even 200 if user_id is optional
    mgr.validate(
        "error_or_success",
        chat_response_2.status_code in [200, 400, 422],
        chat_response_2.status_code,
        "200/400/422",
        "Handles missing user_id appropriately",
    )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_60e_channel_chat_disabled_channel(api_client, test_user, test_expert):
    """AT1.60e: Channel chat with disabled channel"""
    mgr = TestOutputManager("AT1_60e_channel_chat_disabled_channel")
    mgr.log_console("TEST START: AT1.60e - Disabled Channel")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create disabled channel
    channel_data = {
        "name": f"AT1.60e Disabled Channel {uuid.uuid4().hex[:8]}",
        "expert_config_id": test_expert["id"],
        "description": "Test disabled channel",
        "enabled": False,
    }
    channel_response = api_client.post("/channels", json=channel_data)
    mgr.validate(
        "channel_created",
        channel_response.status_code == 200,
        channel_response.status_code,
        200,
        "Disabled channel created",
    )

    if channel_response.status_code == 200:
        channel = channel_response.json()

        # Create session
        session_data = {
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.60e Test Session {uuid.uuid4()}",
        }
        session_response = api_client.post("/sessions", json=session_data)

        if session_response.status_code == 200:
            session = session_response.json()

            # Try to chat with disabled channel
            chat_data = {
                "message": "Test message",
                "user_id": test_user["id"],
                "session_id": session["id"],
                "mode": "sync",
            }
            mgr.save_input("chat_disabled_channel", chat_data)

            chat_response = api_client.post(f"/channels/{channel['id']}/chat", json=chat_data)
            mgr.save_output("chat_disabled_channel", chat_response)

            mgr.validate(
                "error_or_success",
                chat_response.status_code in [200, 400, 403],
                chat_response.status_code,
                "200/400/403",
                "Handles disabled channel appropriately",
            )

            # Cleanup
            api_client.delete(f"/sessions/{session['id']}")

        api_client.delete(f"/channels/{channel['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_60f_channel_chat_very_long_message(api_client, test_channel, test_user, test_expert):
    """AT1.60f: Channel chat with very long message"""
    mgr = TestOutputManager("AT1_60f_channel_chat_very_long_message")
    mgr.log_console("TEST START: AT1.60f - Very Long Message")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.60f Test Session {uuid.uuid4()}",
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

        # Send very long message (10000 characters)
        long_message = "This is a test message. " * 400  # ~10000 chars
        chat_data = {
            "message": long_message,
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input(
            "chat_long_message",
            {
                "message_length": len(long_message),
                "user_id": test_user["id"],
                "session_id": session["id"],
            },
        )

        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("chat_long_message", chat_response)

        mgr.validate(
            "handles_long_message",
            chat_response.status_code in [200, 400, 413],
            chat_response.status_code,
            "200/400/413",
            "Handles long message appropriately",
        )

        if chat_response.status_code == 200:
            data = chat_response.json()
            mgr.validate(
                "has_response",
                "response" in data,
                "response" in data,
                True,
                "Response generated for long message",
            )

        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_60g_channel_chat_special_characters(api_client, test_channel, test_user, test_expert):
    """AT1.60g: Channel chat with special characters and unicode"""
    mgr = TestOutputManager("AT1_60g_channel_chat_special_characters")
    mgr.log_console("TEST START: AT1.60g - Special Characters")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.60g Test Session {uuid.uuid4()}",
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

        # Send message with special characters
        special_message = "Test with special chars: <>&\"' 日本語 中文 한국어 🚀 emoji"
        chat_data = {
            "message": special_message,
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input("chat_special_chars", chat_data)

        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("chat_special_chars", chat_response)

        mgr.validate(
            "handles_special_chars",
            chat_response.status_code == 200,
            chat_response.status_code,
            200,
            "Handles special characters",
        )

        if chat_response.status_code == 200:
            data = chat_response.json()
            mgr.validate(
                "has_response", "response" in data, "response" in data, True, "Response generated"
            )
            mgr.validate(
                "response_not_empty",
                len(data.get("response", "")) > 0,
                len(data.get("response", "")),
                ">0",
                "Response not empty",
            )

        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_60h_channel_chat_concurrent_requests(api_client, test_channel, test_user, test_expert):
    """AT1.60h: Channel chat with concurrent requests"""
    mgr = TestOutputManager("AT1_60h_channel_chat_concurrent_requests")
    mgr.log_console("TEST START: AT1.60h - Concurrent Requests")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.60h Test Session {uuid.uuid4()}",
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

        # Send multiple async requests
        job_ids = []
        for i in range(3):
            chat_data = {
                "message": f"Concurrent message {i + 1}",
                "user_id": test_user["id"],
                "session_id": session["id"],
                "mode": "async",
            }
            mgr.save_input(f"chat_concurrent_{i + 1}", chat_data)

            chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
            mgr.save_output(f"chat_concurrent_{i + 1}", chat_response)

            mgr.validate(
                f"request_{i + 1}_queued",
                chat_response.status_code == 200,
                chat_response.status_code,
                200,
                f"Request {i + 1} queued",
            )

            if chat_response.status_code == 200:
                data = chat_response.json()
                if "job_id" in data:
                    job_ids.append(data["job_id"])

        mgr.validate("all_queued", len(job_ids) == 3, len(job_ids), 3, "All 3 requests queued")

        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
