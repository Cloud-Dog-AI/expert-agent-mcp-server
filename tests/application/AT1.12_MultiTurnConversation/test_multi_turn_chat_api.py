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
Application Test: AT1.12 - Multi-turn Conversation via Chat API

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for multi-turn conversation with context retention via chat API

Related Requirements: FR1.2
Related Tasks: T022
Related Architecture: CC2.1.1
Related Tests: AT1.12

Recent Changes:
- Initial comprehensive implementation
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import json
import pytest
import requests
import uuid
from src.config.loader import get_config


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def test_user_credentials(test_env_file, test_secrets_file):
    """Get test user credentials from configuration system."""
    from src.config.loader import load_config

    load_config.cache_clear()

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Test user credentials not configured. Set test.user.* keys in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_12_chat_{unique_id}",
        "email": build_test_email("at1_12_chat", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API."""
    creds = test_user_credentials

    response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert response.status_code == 200, f"Failed to create test user: {response.text}"
    user_data = response.json()

    yield user_data

    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_12_chat_{unique_id}",
        "title": f"Multi Turn Chat Expert {unique_id} context retention followup memory recall disambiguation",
        "description": "Multi-turn chat scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass


@pytest.fixture
def test_channel(api_client, test_user, test_expert):
    """Create test channel via API."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"channel_at1_12_chat_{unique_id}",
        "expert_config_id": expert_id,
        "user_id": user_id,
        "enabled": True,
    }

    response = api_client.post("/channels", json=channel_data)
    if response.status_code != 200:
        pytest.fail(
            f"Channel endpoint not available (required for AT1.12): {response.status_code} {response.text}"
        )

    channel = response.json()

    yield channel

    try:
        api_client.delete(f"/channels/{channel['id']}")
    except Exception:
        pass


def _llm_request_params(idx: int = 0):
    """Get per-request LLM params from config (no hardcoded defaults)."""
    settings = get_config("test.at1_10.llm_settings")
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except json.JSONDecodeError as exc:
            pytest.fail(f"test.at1_10.llm_settings is not valid JSON: {exc}")
    if not settings or not isinstance(settings, list):
        pytest.fail("Missing test.at1_10.llm_settings in config (--env/defaults.yaml)")
    if idx < 0 or idx >= len(settings):
        pytest.fail(f"test.at1_10.llm_settings[{idx}] not configured (len={len(settings)})")
    base = settings[idx] or {}
    temperature = base.get("temperature")
    max_tokens = base.get("max_tokens")
    if temperature is None or max_tokens is None:
        pytest.fail(f"test.at1_10.llm_settings[{idx}].temperature/max_tokens not configured")
    return {"temperature": float(temperature), "max_tokens": int(max_tokens)}


def _system_prompt_concise() -> str:
    prompt = get_config("test.at1_12.chat.system_prompt_concise")
    if not prompt:
        pytest.fail(
            "Missing test.at1_12.chat.system_prompt_concise in config (--env/defaults.yaml)"
        )
    return str(prompt)


def _create_session_with_seed_message(
    api_client, user_id: int, expert_id: int, title: str, seed_message: str
) -> int:
    """Create a session and seed it with a user message via API (no LLM call)."""
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    resp = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": title,
            "context_window": int(context_window),
            "history_retention_days": int(history_retention_days),
        },
    )
    assert resp.status_code == 200, f"Failed to create session: {resp.text}"
    session_id = resp.json()["id"]

    msg = api_client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": seed_message},
    )
    assert msg.status_code == 200, f"Failed to seed session message: {msg.text}"
    return session_id


def _assert_chat_response_shape(data: dict):
    assert data.get("mode") == "sync"
    assert isinstance(data.get("session_id"), int)
    assert isinstance(data.get("response"), str) and data.get("response")
    assert "job_id" in data
    assert "model" in data
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_via_chat_api(api_client, test_user, test_expert, test_channel):
    """Validate context retention via 1 LLM call using pre-seeded session history."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_id = _create_session_with_seed_message(
        api_client,
        user_id=user_id,
        expert_id=expert_id,
        title=f"AT1.12 Chat Seeded Session {unique_id}",
        seed_message=f"My name is Alice and I work as a software engineer. Test {unique_id}",
    )
    try:
        params = _llm_request_params(0)
        params["max_tokens"] = max(int(params.get("max_tokens", 0)), 16)
        resp = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": "What is my name? Reply with only the name.",
                "user_id": user_id,
                "session_id": session_id,
                "async_mode": False,
                "system_prompt": _system_prompt_concise(),
                **params,
            },
        )
        if resp.status_code == 503:
            pytest.fail(f"LLM service unavailable (required for AT1.12): {resp.text}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        _assert_chat_response_shape(data)
        assert "alice" in data["response"].lower()
    finally:
        delete_resp = api_client.delete(f"/sessions/{session_id}")
        if delete_resp.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_resp.status_code} {delete_resp.text}"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_with_llm_settings_via_chat_api(
    api_client, test_user, test_expert, test_channel
):
    """Validate request-scoped LLM settings (single chat call)."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_id = _create_session_with_seed_message(
        api_client,
        user_id=user_id,
        expert_id=expert_id,
        title=f"AT1.12 Chat LLM Settings {unique_id}",
        seed_message=f"I'm learning Python programming. Test {unique_id}",
    )
    try:
        try:
            resp = api_client.post(
                f"/channels/{channel_id}/chat",
                json={
                    "message": "What programming language am I learning?",
                    "user_id": user_id,
                    "session_id": session_id,
                    "async_mode": False,
                    "system_prompt": _system_prompt_concise(),
                    **_llm_request_params(1),
                },
            )
        except requests.exceptions.ReadTimeout as e:
            pytest.fail(f"LLM request exceeded HTTP timeout in this environment: {e}")
        if resp.status_code == 503:
            pytest.fail(f"LLM service unavailable (required for AT1.12): {resp.text}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        _assert_chat_response_shape(data)
        assert "python" in data["response"].lower()
    finally:
        delete_resp = api_client.delete(f"/sessions/{session_id}")
        if delete_resp.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_resp.status_code} {delete_resp.text}"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_with_response_formats_via_chat_api(
    api_client, test_user, test_expert, test_channel
):
    """Validate response_format parameter (one call per format)."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    for response_format in ["text", "markdown", "json"]:
        session_id = _create_session_with_seed_message(
            api_client,
            user_id=user_id,
            expert_id=expert_id,
            title=f"AT1.12 Chat Format {response_format} {unique_id}",
            seed_message=f"Seed for {response_format} format test {unique_id}",
        )
        try:
            try:
                resp = api_client.post(
                    f"/channels/{channel_id}/chat",
                    json={
                        "message": f"Respond in {response_format} format.",
                        "user_id": user_id,
                        "session_id": session_id,
                        "async_mode": False,
                        "response_format": response_format,
                        "system_prompt": _system_prompt_concise(),
                        **_llm_request_params(0),
                    },
                )
            except requests.exceptions.ReadTimeout as e:
                pytest.fail(f"LLM request exceeded HTTP timeout in this environment: {e}")
            if resp.status_code == 503:
                pytest.fail(f"LLM service unavailable (required for AT1.12): {resp.text}")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            _assert_chat_response_shape(data)
        finally:
            delete_resp = api_client.delete(f"/sessions/{session_id}")
            if delete_resp.status_code not in (200, 204, 404):
                print(
                    f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_resp.status_code} {delete_resp.text}"
                )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_with_languages_via_chat_api(
    api_client, test_user, test_expert, test_channel
):
    """Validate language parameter (one call per language)."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    for lang, seed in {
        "en": f"My favorite color is blue. Test {unique_id}",
        "fr": f"Ma couleur préférée est bleue. Test {unique_id}",
        "pl": f"Mój ulubiony kolor to niebieski. Test {unique_id}",
    }.items():
        session_id = _create_session_with_seed_message(
            api_client,
            user_id=user_id,
            expert_id=expert_id,
            title=f"AT1.12 Chat Lang {lang} {unique_id}",
            seed_message=seed,
        )
        try:
            resp = api_client.post(
                f"/channels/{channel_id}/chat",
                json={
                    "message": "What is my favorite colour?",
                    "user_id": user_id,
                    "session_id": session_id,
                    "async_mode": False,
                    "language": lang,
                    "system_prompt": _system_prompt_concise(),
                    **_llm_request_params(0),
                },
            )
            if resp.status_code == 503:
                pytest.fail(f"LLM service unavailable (required for AT1.12): {resp.text}")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            _assert_chat_response_shape(data)
        finally:
            delete_resp = api_client.delete(f"/sessions/{session_id}")
            if delete_resp.status_code not in (200, 204, 404):
                print(
                    f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_resp.status_code} {delete_resp.text}"
                )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_complex_via_chat_api(
    api_client, test_user, test_expert, test_channel
):
    """Validate long context via seeded messages + 1 LLM call."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_id = _create_session_with_seed_message(
        api_client,
        user_id=user_id,
        expert_id=expert_id,
        title=f"AT1.12 Chat Complex {unique_id}",
        seed_message=f"I'm planning a vacation to Paris. Test {unique_id}",
    )
    try:
        for message in [
            "I'm interested in museums and art galleries.",
            "Can you suggest a 3-day itinerary?",
            "I also want to try French cuisine.",
        ]:
            msg = api_client.post(
                f"/sessions/{session_id}/messages",
                json={"role": "user", "content": message},
            )
            assert msg.status_code == 200, msg.text

        resp = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": "Suggest a 3-day itinerary in Paris.",
                "user_id": user_id,
                "session_id": session_id,
                "async_mode": False,
                "system_prompt": _system_prompt_concise(),
                **_llm_request_params(0),
            },
        )
        if resp.status_code == 503:
            pytest.fail(f"LLM service unavailable (required for AT1.12): {resp.text}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        _assert_chat_response_shape(data)
    finally:
        delete_resp = api_client.delete(f"/sessions/{session_id}")
        if delete_resp.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_resp.status_code} {delete_resp.text}"
            )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
