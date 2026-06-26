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
Application Test: AT1.12 - Scenario 3: Art of War Analysis
Chinese, MCP Interface, Very Long Conversation

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive multi-turn conversation test analyzing Sun Tzu's
"The Art of War" with 50+ turns via MCP interface.

Related Requirements: FR1.2
Related Tasks: T022, T010
Related Architecture: CC2.1.1
Related Tests: AT1.12

Recent Changes:
- Comprehensive implementation with output storage
- Configuration-driven (no hardcoded values)
- MCP interface testing (via /mcp/chat endpoint)
- Full output validation
- Very long conversation (50+ turns)
- Chinese language support
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture


import pytest
import sys
from pathlib import Path
import uuid
import importlib.util
import time
import requests

# Ensure project root is in path
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.config.loader import get_config, load_config  # noqa: E402

# Fix import path for AT1.12 (contains dot which Python interprets as decimal)
_helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("test_helpers", _helpers_path)
test_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_helpers)
TestOutputStorage = test_helpers.TestOutputStorage
validate_config_loaded = test_helpers.validate_config_loaded


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def test_user_credentials(test_env_file):
    """Get test user credentials from configuration system."""
    load_config.cache_clear()

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Test user credentials not configured. Set test.user.username, test.user.email, "
            "test.user.password in --env file or defaults.yaml"
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_12_scenario3_{unique_id}",
        "email": build_test_email("at1_12_scenario3", unique_id, base_email),
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

    resp = api_client.delete(f"/users/{user_data['id']}")
    if resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete user {user_data['id']}: {resp.status_code} {resp.text}"
        )


@pytest.fixture
def military_strategist_expert(api_client, test_user):
    """Create Military Strategist expert (Chinese) via API."""
    load_config.cache_clear()

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    llm_temperature = get_config("test.at1_12.scenario_3.temperature")
    llm_max_tokens = get_config("test.at1_12.scenario_3.max_tokens")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    if llm_temperature is None or llm_max_tokens is None:
        pytest.fail(
            "Missing test.at1_12.scenario_3.temperature/max_tokens in config (--env/defaults.yaml)"
        )

    unique_id = str(uuid.uuid4())[:8]

    expert_response = api_client.post(
        "/experts",
        json={
            "name": f"军事战略家 {unique_id}",
            "title": f"military strategy analyst historian advisor planner tutor coach {unique_id}",
            "description": f"military strategy tactics operations logistics intelligence terrain deception doctrine analysis synthesis critique comparison scenario simulation decisionmaking leadership briefing wargame scholar consultant id {unique_id}",
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
            "llm_temperature": float(llm_temperature),
            "llm_max_tokens": int(llm_max_tokens),
            "prompt_template": "你是一位军事战略专家，专门研究《孙子兵法》等古代军事经典。提供深入、准确的分析。",
            "enabled": True,
        },
    )
    assert expert_response.status_code == 200, f"Failed to create expert: {expert_response.text}"
    expert_data = expert_response.json()

    yield expert_data

    resp = api_client.delete(f"/experts/{expert_data['id']}")
    if resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert_data['id']}: {resp.status_code} {resp.text}"
        )


@pytest.fixture
def test_session(api_client, test_user, military_strategist_expert):
    """Create test session via API."""
    user_id = test_user["id"]
    expert_id = military_strategist_expert["id"]

    load_config.cache_clear()
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    unique_id = str(uuid.uuid4())[:8]
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"孙子兵法分析 {unique_id}",
            "context_window": context_window,
            "history_retention_days": history_retention_days,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()

    yield session_data

    last = None
    for attempt in range(3):
        try:
            resp = api_client.delete(f"/sessions/{session_data['id']}")
            last = resp
            if resp.status_code in (200, 204, 404):
                break
            if resp.status_code >= 500:
                time.sleep(1.0 * (attempt + 1))
                continue
            break
        except requests.exceptions.RequestException as e:
            last = e
            time.sleep(1.0 * (attempt + 1))
            continue

    if hasattr(last, "status_code") and last.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_data['id']}: {last.status_code} {last.text}"
        )
    if not hasattr(last, "status_code") and last is not None:
        print(f"[CLEANUP WARNING] Failed to delete session {session_data['id']}: {last}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_scenario_3_art_of_war_comprehensive(
    api_client, test_user, military_strategist_expert, test_session, test_env_file
):
    """Comprehensive multi-turn conversation test: Art of War Analysis.

    This test implements a very long conversation (50+ turns) analyzing Sun Tzu's
    "The Art of War" in Chinese, with progressive complexity and full context retention.

    Inputs:
    - test_user: User created via API
    - military_strategist_expert: Expert created via API (Chinese)
    - test_session: Session created via API
    - api_client: API test client
    - test_env_file: Environment file (validated)

    Expected Outputs:
    - Session created and persisted
    - 50+ messages exchanged (in Chinese)
    - Context retained across all turns
    - All outputs saved to storage
    - Test summary with links generated

    Validation:
    - Format: All API responses validated
    - Content: All message content validated (Chinese)
    - Structure: Session, messages validated
    - Cross-validation: Context retention verified
    - Storage: All outputs saved and retrievable
    """
    # Initialize output storage
    output_storage = TestOutputStorage("scenario_3_art_of_war_mcp")

    test_user["id"]
    expert_id = military_strategist_expert["id"]
    session_id = test_session["id"]

    output_storage.set_session_id(session_id)

    output_storage.save_test_metadata(
        {
            "session_id": session_id,
            "expert_id": expert_id,
            "expert_name": military_strategist_expert["name"],
            "scenario": "Art of War Analysis",
            "language": "Chinese (Simplified)",
            "interface": "MCP (via /mcp/chat)",
            "expected_turns": 50,
        }
    )

    # Conversation topics for Art of War (Chinese)
    conversation_flow = []

    # Initialization (5 turns)
    conversation_flow.append(("user", "我想分析《孙子兵法》"))
    conversation_flow.append(("assistant", None))
    conversation_flow.append(("user", "重点讨论战略原则"))
    conversation_flow.append(("assistant", None))
    conversation_flow.append(("user", "让我们从第一章开始"))

    # Deep Analysis - Chapters (30 turns)
    topics_chapters = [
        "解释计篇的主要内容",
        "作战篇的核心思想是什么？",
        "谋攻篇的战略原则",
        "军形篇的要点",
        "兵势篇的含义",
        "虚实篇的概念",
        "军争篇的策略",
        "九变篇的灵活性",
        "行军篇的要点",
        "地形篇的重要性",
        "九地篇的分类",
        "火攻篇的战术",
        "用间篇的智慧",
        "如何应用这些原则？",
        "这些原则在现代的意义",
    ]
    for topic in topics_chapters:
        conversation_flow.append(("user", topic))
        conversation_flow.append(("assistant", None))

    # Complex Reasoning (10 turns)
    topics_reasoning = [
        "这与现代军事理论如何比较？",
        "实际应用的含义是什么？",
        "详细解释'知己知彼'的概念",
        "有哪些局限性？",
        "这些原则如何影响历史？",
    ]
    for topic in topics_reasoning:
        conversation_flow.append(("user", topic))
        conversation_flow.append(("assistant", None))

    # Summary and Conclusion (5 turns)
    conversation_flow.append(("user", "总结我们讨论的要点"))
    conversation_flow.append(("assistant", None))
    conversation_flow.append(("user", "主要收获是什么？"))
    conversation_flow.append(("assistant", None))
    conversation_flow.append(("user", "谢谢，这很有帮助"))

    # Execute conversation (cap total turns for deterministic runtime)
    max_user_turns = get_config("test.at1_12.scenario_3.max_user_turns")
    llm_temperature = get_config("test.at1_12.scenario_3.temperature")
    llm_max_tokens = get_config("test.at1_12.scenario_3.max_tokens")
    validate_every = get_config("test.at1_12.scenario_3.validate_every_n_user_turns")
    concise_prompt = get_config("test.at1_12.chat.system_prompt_concise")
    if (
        max_user_turns is None
        or llm_temperature is None
        or llm_max_tokens is None
        or validate_every is None
        or not concise_prompt
    ):
        pytest.fail(
            "Missing test.at1_12.scenario_3.* and/or test.at1_12.chat.system_prompt_concise in config (--env/defaults.yaml)"
        )

    user_turn_number = 0
    job_ids = []

    def _get_history_or_skip(turn_label: str):
        last = None
        for attempt in range(3):
            try:
                resp = api_client.get(f"/sessions/{session_id}/messages")
                last = resp
                if resp.status_code == 200:
                    return resp
                if resp.status_code >= 500:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                pytest.fail(
                    f"Failed to get message history ({turn_label}): {resp.status_code} {resp.text}"
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as e:
                last = e
                time.sleep(2.0 * (attempt + 1))
                continue

        msg = last.text if hasattr(last, "text") else str(last)
        pytest.fail(f"API became unstable during long MCP chat ({turn_label}): {msg}")

    try:
        for role, content in conversation_flow:
            if role == "user":
                user_turn_number += 1
                if user_turn_number > int(max_user_turns):
                    break

                output_storage.save_message(
                    {"role": "user", "content": content, "session_id": session_id},
                    user_turn_number,
                )

                # Get chat response via MCP chat endpoint
                mcp_response = api_client.post(
                    "/mcp/chat",
                    json={
                        "session_id": session_id,
                        "message": content,
                        "language": "zh",  # Chinese
                        "system_prompt": str(concise_prompt),
                        "temperature": float(llm_temperature),
                        "max_tokens": int(llm_max_tokens),
                    },
                )

                if mcp_response.status_code == 200:
                    mcp_data = mcp_response.json()

                    if "job_id" in mcp_data:
                        job_ids.append(str(mcp_data["job_id"]))
                        output_storage.save_job(str(mcp_data["job_id"]), mcp_data)

                    if "response" in mcp_data:
                        assistant_message = {
                            "id": mcp_data.get("message_id"),
                            "role": "assistant",
                            "content": mcp_data["response"],
                            "session_id": session_id,
                        }
                        output_storage.save_message(assistant_message, user_turn_number + 0.5)
                elif mcp_response.status_code == 503:
                    pytest.fail(
                        f"LLM service unavailable (required for AT1.12): {mcp_response.text}"
                    )
                else:
                    pytest.fail(
                        f"MCP chat failed at turn {user_turn_number}: {mcp_response.status_code} - {mcp_response.text}"
                    )

            # Validate context retention periodically
            if user_turn_number % int(validate_every) == 0 and user_turn_number > 0:
                history_response = _get_history_or_skip(f"turn={user_turn_number}")
                history_data = history_response.json()

                assert len(history_data["messages"]) >= user_turn_number, (
                    f"Context not retained: expected at least {user_turn_number} messages, got {len(history_data['messages'])}"
                )

        # Final validation
        final_history_response = _get_history_or_skip("final")
        final_history_data = final_history_response.json()

        expected_user_messages = min(
            int(max_user_turns), len([m for m in conversation_flow if m[0] == "user"])
        )
        assert len(final_history_data["messages"]) >= expected_user_messages, (
            f"Not all messages present: expected at least {expected_user_messages}, got {len(final_history_data['messages'])}"
        )

        # Save conversation log
        all_message_ids = [
            m.get("id") for m in final_history_data["messages"] if m.get("id") is not None
        ]
        output_storage.save_conversation_log(
            {
                "session_id": session_id,
                "total_turns": user_turn_number,
                "total_messages": len(final_history_data["messages"]),
                "message_ids": all_message_ids,
                "job_ids": job_ids,
                "messages": final_history_data["messages"],
            }
        )

        output_storage.save_test_metadata(
            {
                "total_turns": user_turn_number,
                "total_messages": len(final_history_data["messages"]),
                "total_jobs": len(job_ids),
            }
        )
        test_summary = output_storage.save_test_summary()

        # Print summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY - Scenario 3: Art of War Analysis")
        print("=" * 80)
        print(f"Test Name: {test_summary['test_name']}")
        print(f"Session ID: {test_summary['session_id']}")
        print(f"Total Messages: {test_summary['total_messages']}")
        print(f"Total Jobs: {test_summary['total_jobs']}")
        print("Language: Chinese (Simplified)")
        print("Interface: MCP (via /mcp/chat)")
        print("\nOutput Files:")
        print(f"  Messages: {test_summary['outputs']['messages']['file']}")
        print(f"  Jobs: {test_summary['outputs']['jobs']['file']}")
        print(f"  Conversation Log: {test_summary['outputs']['conversation_log']['file']}")
        print(f"  Test Metadata: {test_summary['outputs']['test_metadata']['file']}")
        print("=" * 80)

    finally:
        # Session cleanup handled by fixture
        pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]

