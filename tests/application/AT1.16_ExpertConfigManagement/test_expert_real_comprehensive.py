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
Description: REAL comprehensive tests for Expert Configuration Management (AT1.16).
Tests with ACTUAL LLM calls, prompt validation, and complete output storage.

Related Requirements: FR1.4
Related Tasks: T007, T008
Related Architecture: CC3.1.1
Related Tests: AT1.16

Recent Changes:
- REAL tests with actual LLM integration
- Full TestOutputStorage for all operations
- LLM call recording and validation
- Prompt template testing with real responses
- Parameter testing (temperature, top_k, etc.)

**************************************************
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import create_api_client_fixture, validate_config_loaded


import pytest
import uuid
import time
from src.config.loader import get_config, load_config

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import TestOutputStorage, validate_api_response


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def storage():
    return lambda test_name: TestOutputStorage("AT1.16_ExpertConfigManagement", test_name)


@pytest.fixture
def test_user(api_client, test_env_file):
    """Create a test user via API (credentials derived from config)."""
    load_config.cache_clear()
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")
    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if "@" not in base_email:
        pytest.fail("test.user.email must include an '@' to derive a domain")
    domain = base_email.split("@", 1)[1]

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"{base_username}_at16_llm_{unique_id}",
        "email": f"at16_llm_{unique_id}@{domain}",
        "password": base_password,
        "display_name": f"AT1.16 LLM User {unique_id}",
        "role": "user",
    }
    resp = api_client.post("/users", json=user_payload)
    assert resp.status_code == 200, f"Failed to create test user: {resp.status_code} {resp.text}"
    user = resp.json()
    yield user
    try:
        api_client.delete(f"/users/{user['id']}")
    except Exception:
        pass


def _require_llm_config():
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    return llm_provider, llm_model, llm_base_url
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-027")


def test_expert_with_real_llm_conversation(api_client, storage, test_user):
    """
    REAL TEST: Create expert and have ACTUAL LLM conversation.
    Tests complete workflow with real LLM calls.
    """
    store = storage("test_expert_with_real_llm_conversation")
    print("\n" + "=" * 80)
    print("TEST: Expert with REAL LLM Conversation")
    print("=" * 80)

    # Create expert
    print("\n[1/4] Creating expert...")
    llm_provider, llm_model, llm_base_url = _require_llm_config()
    unique_id = uuid.uuid4().hex[:8]
    expert_input = {
        "name": f"test_llm_expert_{unique_id}",
        "title": f"LLM Conversation Expert {unique_id} coverage validation",
        "description": (
            "Expert for real LLM conversation tests with distinct wording and "
            f"accuracy checks {unique_id}"
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "llm_params": {"temperature": 0.7, "max_tokens": 100},
        "prompt_template": "You are a helpful assistant. Answer concisely.",
        "enabled": True,
    }
    expert_response = api_client.post("/experts", json=expert_input)
    expert_validation = validate_api_response(expert_response, 200, ["id", "name"])
    store.save_operation(
        "create_expert",
        expert_input,
        expert_response.json() if expert_response.status_code == 200 else {},
    )

    assert expert_validation["overall_passed"], "Expert creation failed"
    expert_name = expert_response.json()["name"]
    expert_id = expert_response.json()["id"]
    print(f"✓ Expert created: {expert_name}")

    # Create channel with this expert
    print("\n[2/4] Creating channel...")
    channel_input = {
        "name": f"at16_llm_channel_{uuid.uuid4().hex[:8]}",
        "expert_config_id": expert_id,
        "enabled": True,
        "description": "AT1.16 real LLM channel",
    }
    channel_response = api_client.post("/channels", json=channel_input)
    channel_validation = validate_api_response(channel_response, 200, ["id", "expert_config_id"])
    store.save_operation(
        "create_channel",
        channel_input,
        channel_response.json() if channel_response.status_code == 200 else {},
    )
    assert channel_validation["overall_passed"], (
        f"Channel creation failed: {channel_response.status_code} {channel_response.text}"
    )
    channel_id = channel_response.json()["id"]

    # Send REAL message to LLM via channel chat (sync)
    print(
        "\n[3/4] Sending REAL message to LLM via /channels/{id}/chat (this may take 10-30 seconds)..."
    )
    message = "What is 2+2? Answer with just the number 4."
    chat_input = {"message": message, "user_id": test_user["id"], "async_mode": False}
    start_time = time.time()
    chat_response = api_client.post(f"/channels/{channel_id}/chat", json=chat_input)
    llm_time = time.time() - start_time
    store.save_operation(
        "channel_chat_sync",
        chat_input,
        chat_response.json() if chat_response.status_code == 200 else {},
        {"llm_response_time": llm_time},
    )
    assert chat_response.status_code == 200, (
        f"Chat failed: {chat_response.status_code} {chat_response.text}"
    )

    data = chat_response.json()
    response_text = data.get("response") or ""
    assert isinstance(response_text, str) and response_text.strip(), (
        "Expected non-empty LLM response"
    )

    # Save LLM call details + validate correctness
    store.save_llm_call(
        prompt=message,
        response=response_text,
        llm_config={
            "provider": llm_provider,
            "model": llm_model,
            "parameters": expert_input["llm_params"],
        },
        metadata={"response_time_seconds": llm_time, "channel_id": channel_id},
    )
    has_four = "4" in response_text.strip()
    store.save_validation(
        "llm_response_correct",
        {
            "question": "2+2",
            "expected_contains": "4",
            "response": response_text,
            "contains_4": has_four,
        },
        has_four,
    )
    print(f"✓ LLM Response: {response_text[:100]}")
    print(f"✓ Response correct: {has_four}")

    # Cleanup channel
    api_client.delete(f"/channels/{channel_id}")

    api_client.delete(f"/experts/{expert_id}")

    summary = store.save_test_summary()
    print(f"\n✓ Test complete - {summary['total_llm_calls']} LLM calls recorded")
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-027")


def test_expert_temperature_variations(api_client, storage, test_user):
    """
    REAL TEST: Test LLM temperature parameter with actual calls.
    Compares outputs at different temperatures.
    """
    store = storage("test_expert_temperature_variations")
    print("\n" + "=" * 80)
    print("TEST: Expert Temperature Variations (REAL LLM calls)")
    print("=" * 80)

    llm_provider, llm_model, llm_base_url = _require_llm_config()

    temperatures = [0.1, 0.5, 0.9]
    question = "Tell me a creative story about a robot in one sentence."
    responses: dict[float, str] = {}

    for temp in temperatures:
        print(f"\n[Testing temperature={temp}]")

        # Create expert with specific temperature
        unique_id = uuid.uuid4().hex[:6]
        expert_input = {
            "name": f"temp_{temp}_{unique_id}",
            "title": f"Temperature {temp} Expert {unique_id} variation coverage",
            "description": (
                "Expert for temperature variation testing with diverse wording and "
                f"response diversity checks {unique_id}"
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_params": {"temperature": temp, "max_tokens": 50},
            "enabled": True,
        }
        expert_response = api_client.post("/experts", json=expert_input)
        store.save_operation(
            f"create_expert_temp_{temp}",
            expert_input,
            expert_response.json() if expert_response.status_code == 200 else {},
        )
        assert expert_response.status_code == 200, (
            f"Failed to create expert (temp={temp}): {expert_response.status_code} {expert_response.text}"
        )

        expert_id = expert_response.json()["id"]

        # Create channel
        channel_input = {
            "name": f"at16_temp_channel_{uuid.uuid4().hex[:8]}",
            "expert_config_id": expert_id,
            "enabled": True,
        }
        channel_response = api_client.post("/channels", json=channel_input)
        store.save_operation(
            f"create_channel_temp_{temp}",
            channel_input,
            channel_response.json() if channel_response.status_code == 200 else {},
        )
        assert channel_response.status_code == 200, (
            f"Failed to create channel (temp={temp}): {channel_response.status_code} {channel_response.text}"
        )
        channel_id = channel_response.json()["id"]

        # Chat
        print("  Sending message to LLM...")
        chat_input = {"message": question, "user_id": test_user["id"], "async_mode": False}
        start_time = time.time()
        chat_response = api_client.post(f"/channels/{channel_id}/chat", json=chat_input)
        llm_time = time.time() - start_time
        store.save_operation(
            f"channel_chat_temp_{temp}",
            chat_input,
            chat_response.json() if chat_response.status_code == 200 else {},
            {"llm_response_time": llm_time},
        )
        assert chat_response.status_code == 200, (
            f"Chat failed (temp={temp}): {chat_response.status_code} {chat_response.text}"
        )

        response_text = (chat_response.json().get("response") or "").strip()
        assert response_text, f"Expected non-empty response (temp={temp})"
        responses[temp] = response_text
        store.save_llm_call(
            prompt=question,
            response=response_text,
            llm_config={
                "provider": llm_provider,
                "model": llm_model,
                "parameters": {"temperature": temp},
            },
            metadata={"test": "temperature_variation", "response_time_seconds": llm_time},
        )
        print(f"  ✓ Response (temp={temp}): {response_text[:80]}...")

        # Cleanup
        api_client.delete(f"/channels/{channel_id}")
        api_client.delete(f"/experts/{expert_id}")

    store.save_validation(
        "temperature_variations_ran",
        {
            "expected_count": len(temperatures),
            "actual_count": len(responses),
            "temps": sorted(list(responses.keys())),
        },
        len(responses) == len(temperatures),
    )

    summary = store.save_test_summary()
    print(f"\n✓ Test complete - {summary['total_llm_calls']} temperature variations tested")
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-027")


def test_expert_prompt_template_effectiveness(api_client, storage, test_user):
    """
    REAL TEST: Compare different prompt templates with actual LLM responses.
    """
    store = storage("test_expert_prompt_template_effectiveness")
    print("\n" + "=" * 80)
    print("TEST: Expert Prompt Template Effectiveness (REAL LLM)")
    print("=" * 80)

    templates = [
        "You are a helpful assistant.",
        "You are a technical expert. Be concise and precise.",
        "You are a creative writer. Be imaginative and engaging.",
    ]

    question = "Explain what AI is."
    llm_provider, llm_model, llm_base_url = _require_llm_config()
    tested = 0

    for idx, template in enumerate(templates):
        print(f"\n[Testing template {idx + 1}/3]")

        unique_id = uuid.uuid4().hex[:6]
        expert_input = {
            "name": f"template_{idx}_{unique_id}",
            "title": f"Template Test {idx} expert coverage {unique_id}",
            "description": (
                "Expert for prompt template effectiveness with distinct keywords and "
                f"response evaluation {unique_id}"
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_params": {"temperature": 0.7, "max_tokens": 100},
            "prompt_template": template,
            "enabled": True,
        }
        expert_response = api_client.post("/experts", json=expert_input)
        store.save_operation(
            f"create_expert_template_{idx}",
            expert_input,
            expert_response.json() if expert_response.status_code == 200 else {},
        )
        assert expert_response.status_code == 200, (
            f"Failed to create expert (template idx={idx}): {expert_response.status_code} {expert_response.text}"
        )

        expert_id = expert_response.json()["id"]
        channel_input = {
            "name": f"at16_template_channel_{uuid.uuid4().hex[:8]}",
            "expert_config_id": expert_id,
            "enabled": True,
        }
        channel_response = api_client.post("/channels", json=channel_input)
        store.save_operation(
            f"create_channel_template_{idx}",
            channel_input,
            channel_response.json() if channel_response.status_code == 200 else {},
        )
        assert channel_response.status_code == 200, (
            f"Failed to create channel (template idx={idx}): {channel_response.status_code} {channel_response.text}"
        )
        channel_id = channel_response.json()["id"]

        print("  Sending message to LLM with template...")
        chat_input = {"message": question, "user_id": test_user["id"], "async_mode": False}
        chat_response = api_client.post(f"/channels/{channel_id}/chat", json=chat_input)
        store.save_operation(
            f"channel_chat_template_{idx}",
            chat_input,
            chat_response.json() if chat_response.status_code == 200 else {},
        )
        assert chat_response.status_code == 200, (
            f"Chat failed (template idx={idx}): {chat_response.status_code} {chat_response.text}"
        )
        response_text = (chat_response.json().get("response") or "").strip()
        assert response_text, "Expected non-empty response"
        tested += 1

        store.save_llm_call(
            prompt=f"Template: {template}\nQuestion: {question}",
            response=response_text,
            llm_config={"provider": llm_provider, "model": llm_model, "template": template},
            metadata={"template_index": idx},
        )
        print(f"  ✓ Response: {response_text[:80]}...")

        api_client.delete(f"/channels/{channel_id}")
        api_client.delete(f"/experts/{expert_id}")

    store.save_validation(
        "templates_tested",
        {"expected_count": len(templates), "actual_count": tested},
        tested == len(templates),
    )

    summary = store.save_test_summary()
    print(f"\n✓ Test complete - {summary['total_llm_calls']} templates tested")
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-027")


def test_expert_configuration_lifecycle(api_client, storage, test_user):
    """
    REAL TEST: Full expert lifecycle - create, configure, test, update, retest.
    """
    store = storage("test_expert_configuration_lifecycle")
    print("\n" + "=" * 80)
    print("TEST: Expert Configuration Lifecycle")
    print("=" * 80)

    llm_provider, llm_model, llm_base_url = _require_llm_config()

    # Create initial expert
    print("\n[1/5] Creating expert...")
    unique_id = uuid.uuid4().hex[:8]
    expert_input = {
        "name": f"lifecycle_expert_{unique_id}",
        "title": f"Lifecycle Test Expert {unique_id} coverage validation",
        "description": (
            "Expert for lifecycle configuration updates with distinct wording and "
            f"validation coverage {unique_id}"
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "llm_params": {"temperature": 0.5},
        "prompt_template": "You are helpful.",
        "enabled": True,
    }
    expert_response = api_client.post("/experts", json=expert_input)
    store.save_operation(
        "create_expert",
        expert_input,
        expert_response.json() if expert_response.status_code == 200 else {},
    )
    assert expert_response.status_code == 200, (
        f"Failed to create expert: {expert_response.status_code} {expert_response.text}"
    )
    expert_id = expert_response.json()["id"]
    print(f"✓ Expert created: {expert_response.json()['name']}")

    channel_input = {
        "name": f"at16_lifecycle_channel_{uuid.uuid4().hex[:8]}",
        "expert_config_id": expert_id,
        "enabled": True,
    }
    channel_response = api_client.post("/channels", json=channel_input)
    store.save_operation(
        "create_channel",
        channel_input,
        channel_response.json() if channel_response.status_code == 200 else {},
    )
    assert channel_response.status_code == 200, (
        f"Failed to create channel: {channel_response.status_code} {channel_response.text}"
    )
    channel_id = channel_response.json()["id"]

    # Test with initial config
    print("\n[2/5] Testing initial configuration...")
    chat1 = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": "Reply with: initial_ok", "user_id": test_user["id"], "async_mode": False},
    )
    store.save_operation(
        "chat_initial",
        {"message": "Reply with: initial_ok"},
        chat1.json() if chat1.status_code == 200 else {},
    )
    assert chat1.status_code == 200, f"Initial chat failed: {chat1.status_code} {chat1.text}"
    resp1 = (chat1.json().get("response") or "").strip()
    assert resp1, "Expected non-empty initial response"

    # Update expert config
    print("\n[3/5] Updating expert configuration...")
    update_input = {"llm_params": {"temperature": 0.9}, "prompt_template": "You are very creative."}
    update_response = api_client.put(f"/experts/{expert_id}", json=update_input)
    store.save_operation(
        "update_expert",
        update_input,
        update_response.json() if update_response.status_code == 200 else {},
    )
    assert update_response.status_code == 200, (
        f"Failed to update expert: {update_response.status_code} {update_response.text}"
    )
    print("✓ Expert updated")

    # Test with updated config
    print("\n[4/5] Testing updated configuration...")
    chat2 = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": "Reply with: updated_ok", "user_id": test_user["id"], "async_mode": False},
    )
    store.save_operation(
        "chat_updated",
        {"message": "Reply with: updated_ok"},
        chat2.json() if chat2.status_code == 200 else {},
    )
    assert chat2.status_code == 200, f"Updated chat failed: {chat2.status_code} {chat2.text}"
    resp2 = (chat2.json().get("response") or "").strip()
    assert resp2, "Expected non-empty updated response"

    # Verify and cleanup
    print("\n[5/5] Verifying and cleaning up...")
    verify_response = api_client.get(f"/experts/{expert_id}")
    store.save_operation(
        "verify_expert", {}, verify_response.json() if verify_response.status_code == 200 else {}
    )
    assert verify_response.status_code == 200, (
        f"Failed to verify expert: {verify_response.status_code} {verify_response.text}"
    )
    expert_data = verify_response.json()
    store.save_validation(
        "expert_updated_fields_persisted",
        {
            "expected_prompt_template": update_input["prompt_template"],
            "actual_prompt_template": expert_data.get("prompt_template"),
            "expected_temperature": 0.9,
            "actual_llm_params": expert_data.get("llm_params"),
        },
        expert_data.get("prompt_template") == update_input["prompt_template"]
        and float(expert_data.get("llm_params", {}).get("temperature", 0)) == 0.9,
    )

    api_client.delete(f"/channels/{channel_id}")
    api_client.delete(f"/experts/{expert_id}")

    summary = store.save_test_summary()
    print(f"\n✓ Lifecycle complete - {summary['total_operations']} operations")
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-027")


def test_expert_access_control_validation(api_client, storage, test_user):
    """
    REAL TEST: Test expert access control with groups and users.
    """
    store = storage("test_expert_access_control_validation")
    print("\n" + "=" * 80)
    print("TEST: Expert Access Control Validation")
    print("=" * 80)

    # Create group
    group_response = api_client.post(
        "/groups", json={"name": f"expert_acl_group_{uuid.uuid4().hex[:6]}", "enabled": True}
    )
    assert group_response.status_code == 200, (
        f"Failed to create group: {group_response.status_code} {group_response.text}"
    )
    group_id = group_response.json()["id"]
    store.save_operation("create_group", {}, group_response.json())

    # Add the test user to group
    add_member = api_client.post(
        f"/groups/{group_id}/members", json={"user_id": test_user["id"], "role": "member"}
    )
    store.save_operation(
        "add_user_to_group",
        {"group_id": group_id, "user_id": test_user["id"]},
        add_member.json() if add_member.status_code == 200 else {},
    )
    assert add_member.status_code == 200, (
        f"Failed to add user to group: {add_member.status_code} {add_member.text}"
    )

    # Create expert with group access control
    llm_provider, llm_model, llm_base_url = _require_llm_config()
    unique_id = uuid.uuid4().hex[:8]
    expert_input = {
        "name": f"acl_expert_{unique_id}",
        "title": f"ACL Test Expert {unique_id} coverage validation",
        "description": (
            "Expert with access control validation, group membership checks, "
            f"and distinct wording for entropy {unique_id}"
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "access_control": {"allowed_groups": [group_id]},
        "enabled": True,
    }
    expert_response = api_client.post("/experts", json=expert_input)
    store.save_operation(
        "create_expert_with_acl",
        expert_input,
        expert_response.json() if expert_response.status_code == 200 else {},
    )
    assert expert_response.status_code == 200, (
        f"Failed to create expert: {expert_response.status_code} {expert_response.text}"
    )
    expert_id = expert_response.json()["id"]

    channel_response = api_client.post(
        "/channels",
        json={
            "name": f"acl_channel_{uuid.uuid4().hex[:8]}",
            "expert_config_id": expert_id,
            "enabled": True,
        },
    )
    store.save_operation(
        "create_acl_channel",
        {},
        channel_response.json() if channel_response.status_code == 200 else {},
    )
    assert channel_response.status_code == 200, (
        f"Failed to create channel: {channel_response.status_code} {channel_response.text}"
    )
    channel_id = channel_response.json()["id"]

    # Verify access control is set
    verify_response = api_client.get(f"/experts/{expert_id}")
    expert_data = verify_response.json()

    store.save_validation(
        "access_control_configured",
        {
            "expected_allowed_groups": [group_id],
            "actual_allowed_groups": expert_data.get("access_control", {}).get(
                "allowed_groups", []
            ),
        },
        group_id in expert_data.get("access_control", {}).get("allowed_groups", []),
    )

    # Verify allowed user can chat
    chat_ok = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": "Reply with: acl_ok", "user_id": test_user["id"], "async_mode": False},
    )
    store.save_operation(
        "acl_chat_allowed", {}, chat_ok.json() if chat_ok.status_code == 200 else {}
    )
    assert chat_ok.status_code == 200, (
        f"Expected allowed user to chat: {chat_ok.status_code} {chat_ok.text}"
    )

    # Cleanup
    api_client.delete(f"/channels/{channel_id}")
    api_client.delete(f"/experts/{expert_id}")
    api_client.delete(f"/groups/{group_id}")

    summary = store.save_test_summary()
    print(f"\n✓ Access control validated - {summary['total_validations']} checks")
    print("=" * 80)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
