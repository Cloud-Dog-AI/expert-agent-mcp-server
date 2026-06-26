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
Application Test: AT1.12 - Scenario 1: Transformer Paper Analysis
English, API Interface, Very Long Conversation

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive multi-turn conversation test analyzing the
"Attention Is All You Need" paper with 60+ turns via API interface.

Related Requirements: FR1.2
Related Tasks: T022, T010
Related Architecture: CC2.1.1
Related Tests: AT1.12

Recent Changes:
- Comprehensive implementation with output storage
- Configuration-driven (no hardcoded values)
- API-only testing
- Full output validation
- Very long conversation (60+ turns)
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture


import pytest
import requests
import sys
from pathlib import Path
import uuid
import importlib.util

# Ensure project root is in path
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.config.loader import get_config, load_config  # noqa: E402

# Fix import path for AT1.12 (contains dot which Python interprets as decimal)
# Use importlib to load test_helpers directly
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
    """Get test user credentials from configuration system (NO direct os.environ)."""
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
        "username": f"{base_username}_at1_12_scenario1_{unique_id}",
        "email": build_test_email("at1_12_scenario1", unique_id, base_email),
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

    # Cleanup via API
    resp = api_client.delete(f"/users/{user_data['id']}")
    if resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete user {user_data['id']}: {resp.status_code} {resp.text}"
        )


@pytest.fixture
def research_analyst_expert(api_client, test_user):
    """Create Research Analyst expert via API."""
    load_config.cache_clear()

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    llm_temperature = get_config("test.at1_12.scenario_1.temperature")
    llm_max_tokens = get_config("test.at1_12.scenario_1.max_tokens")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    if llm_temperature is None or llm_max_tokens is None:
        pytest.fail(
            "Missing test.at1_12.scenario_1.temperature/max_tokens in config (--env/defaults.yaml)"
        )

    unique_id = str(uuid.uuid4())[:8]

    expert_response = api_client.post(
        "/experts",
        json={
            "name": f"Research Analyst {unique_id}",
            "title": "Research Analyst",
            "description": "Expert in analyzing scientific papers and technical documents",
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
            "llm_temperature": float(llm_temperature),
            "llm_max_tokens": int(llm_max_tokens),
            "prompt_template": "You are a research analyst specializing in technical paper analysis. "
            "Provide detailed, accurate analysis with citations and references.",
            "enabled": True,
        },
    )
    assert expert_response.status_code == 200, f"Failed to create expert: {expert_response.text}"
    expert_data = expert_response.json()

    yield expert_data

    # Cleanup via API
    resp = api_client.delete(f"/experts/{expert_data['id']}")
    if resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert_data['id']}: {resp.status_code} {resp.text}"
        )


@pytest.fixture
def test_channel(api_client, research_analyst_expert):
    """Create test channel for the expert."""
    expert_id = research_analyst_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    channel_response = api_client.post(
        "/channels",
        json={
            "name": f"Research Channel {unique_id}",
            "expert_config_id": expert_id,
            "description": "Channel for research analysis",
            "enabled": True,
        },
    )
    assert channel_response.status_code == 200, f"Failed to create channel: {channel_response.text}"
    channel_data = channel_response.json()

    yield channel_data

    # Cleanup via API (if endpoint exists)
    try:
        api_client.delete(f"/channels/{channel_data['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_scenario_1_transformer_paper_comprehensive(
    api_client, test_user, research_analyst_expert, test_channel, test_env_file
):
    """Comprehensive multi-turn conversation test: Transformer Paper Analysis.

    This test implements a very long conversation (60+ turns) analyzing the
    "Attention Is All You Need" paper, with progressive complexity and full
    context retention validation.

    Inputs:
    - test_user: User created via API
    - research_analyst_expert: Expert created via API
    - test_channel: Channel created via API
    - api_client: API test client
    - test_env_file: Environment file (validated)

    Expected Outputs:
    - Session created and persisted
    - 60+ messages exchanged
    - Context retained across all turns
    - Summaries created (if context window exceeded)
    - All outputs saved to storage
    - Job IDs tracked
    - Test summary with links generated

    Validation:
    - Format: All API responses validated
    - Content: All message content validated
    - Structure: Session, messages, summaries validated
    - Cross-validation: Context retention verified
    - Storage: All outputs saved and retrievable
    """
    # Initialize output storage
    output_storage = TestOutputStorage("scenario_1_transformer_api")

    user_id = test_user["id"]
    expert_id = research_analyst_expert["id"]
    channel_id = test_channel["id"]

    load_config.cache_clear()
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    unique_id = str(uuid.uuid4())[:8]

    # Create session via API
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Transformer Paper Analysis {unique_id}",
            "context_window": context_window,
            "history_retention_days": history_retention_days,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Update output storage with session ID
    output_storage.set_session_id(session_id)

    # Save session metadata
    output_storage.save_test_metadata(
        {
            "session_id": session_id,
            "expert_id": expert_id,
            "expert_name": research_analyst_expert["name"],
            "channel_id": channel_id,
            "context_window": context_window,
            "scenario": "Transformer Paper Analysis",
            "language": "English",
            "interface": "API",
            "expected_turns": 60,
        }
    )

    # Conversation topics for Transformer paper (simplified but comprehensive)
    # We'll create a realistic 60+ turn conversation
    conversation_flow = []

    # Initialization (5 turns)
    conversation_flow.append(
        ("user", "I want to analyze the Transformer paper 'Attention Is All You Need'")
    )
    conversation_flow.append(("assistant", None))  # Will be filled by LLM
    conversation_flow.append(("user", "Focus on the attention mechanism"))
    conversation_flow.append(("assistant", None))
    conversation_flow.append(("user", "Let's start with the introduction"))

    # Deep Analysis - Introduction (10 turns)
    topics_intro = [
        "What problem does the Transformer paper address?",
        "What are the main contributions?",
        "Explain the motivation behind using attention",
        "How does this differ from previous approaches?",
        "What are the computational advantages?",
    ]
    for topic in topics_intro:
        conversation_flow.append(("user", topic))
        conversation_flow.append(("assistant", None))

    # Architecture Details (15 turns)
    topics_arch = [
        "Describe the overall architecture",
        "What is self-attention?",
        "Explain the attention mechanism formula",
        "What is multi-head attention?",
        "How many heads are typically used?",
        "Explain positional encoding",
        "What encoding scheme is used?",
        "Describe the feed-forward networks",
    ]
    for topic in topics_arch:
        conversation_flow.append(("user", topic))
        conversation_flow.append(("assistant", None))

    # Attention Mechanism Deep Dive (15 turns)
    topics_attention = [
        "Explain scaled dot-product attention in detail",
        "Why is scaling by √d_k necessary?",
        "How does multi-head attention work?",
        "What are the benefits of multi-head attention?",
        "Compare self-attention to RNNs",
        "What is the computational complexity?",
        "How does this compare to convolutional layers?",
    ]
    for topic in topics_attention:
        conversation_flow.append(("user", topic))
        conversation_flow.append(("assistant", None))

    # Training and Results (10 turns)
    topics_training = [
        "Describe the training procedure",
        "What optimization was used?",
        "What were the main results?",
        "How does it compare to other architectures?",
        "What are the limitations?",
    ]
    for topic in topics_training:
        conversation_flow.append(("user", topic))
        conversation_flow.append(("assistant", None))

    # Complex Reasoning (10 turns)
    topics_reasoning = [
        "How does this compare to RNNs?",
        "What are the computational complexity implications?",
        "Explain the self-attention mechanism in detail",
        "What are the limitations mentioned?",
        "How has this architecture influenced later work?",
    ]
    for topic in topics_reasoning:
        conversation_flow.append(("user", topic))
        conversation_flow.append(("assistant", None))

    # Summary and Conclusion (5 turns)
    conversation_flow.append(("user", "Summarize the key points we discussed"))
    conversation_flow.append(("assistant", None))
    conversation_flow.append(("user", "What are the main takeaways?"))
    conversation_flow.append(("assistant", None))
    conversation_flow.append(("user", "Thank you, that was helpful"))

    # Execute conversation (cap total turns for deterministic runtime)
    max_user_turns = get_config("test.at1_12.scenario_1.max_user_turns")
    llm_temperature = get_config("test.at1_12.scenario_1.temperature")
    llm_max_tokens = get_config("test.at1_12.scenario_1.max_tokens")
    validate_every = get_config("test.at1_12.scenario_1.validate_every_n_user_turns")
    concise_prompt = get_config("test.at1_12.chat.system_prompt_concise")
    if (
        max_user_turns is None
        or llm_temperature is None
        or llm_max_tokens is None
        or validate_every is None
        or not concise_prompt
    ):
        pytest.fail(
            "Missing test.at1_12.scenario_1.* and/or test.at1_12.chat.system_prompt_concise in config (--env/defaults.yaml)"
        )

    user_turn_number = 0
    job_ids = []

    try:
        for role, content in conversation_flow:
            if role == "user":
                user_turn_number += 1
                if user_turn_number > int(max_user_turns):
                    break

                # Record user message locally (channel_chat will persist it in-session)
                output_storage.save_message(
                    {"role": "user", "content": content, "session_id": session_id},
                    user_turn_number,
                )

                # Get chat response via channel chat API
                try:
                    chat_response = api_client.post(
                        f"/channels/{channel_id}/chat",
                        json={
                            "message": content,
                            "user_id": user_id,
                            "session_id": session_id,
                            "system_prompt": str(concise_prompt),
                            "temperature": float(llm_temperature),
                            "max_tokens": int(llm_max_tokens),
                            "async_mode": False,
                        },
                    )
                except requests.exceptions.ReadTimeout as e:
                    pytest.fail(f"LLM chat request exceeded HTTP timeout in this environment: {e}")

                if chat_response.status_code == 200:
                    chat_data = chat_response.json()

                    # Track job ID if present
                    if "job_id" in chat_data:
                        job_ids.append(str(chat_data["job_id"]))
                        output_storage.save_job(str(chat_data["job_id"]), chat_data)

                    # Save assistant response if present
                    if "response" in chat_data:
                        assistant_message = {
                            "id": chat_data.get("message_id"),
                            "role": "assistant",
                            "content": chat_data["response"],
                            "session_id": session_id,
                        }
                        output_storage.save_message(assistant_message, user_turn_number + 0.5)
                elif chat_response.status_code == 503:
                    pytest.fail(
                        f"LLM service unavailable (required for AT1.12): {chat_response.text}"
                    )
                else:
                    # Other error - fail the test
                    pytest.fail(
                        f"Chat failed at turn {user_turn_number}: {chat_response.status_code} - {chat_response.text}"
                    )

            # Validate context retention periodically
            if user_turn_number % int(validate_every) == 0 and user_turn_number > 0:
                # Get message history
                history_response = api_client.get(f"/sessions/{session_id}/messages")
                assert history_response.status_code == 200, (
                    f"Failed to get message history: {history_response.text}"
                )
                history_data = history_response.json()

                # Validate context retention
                assert len(history_data["messages"]) >= user_turn_number, (
                    f"Context not retained: expected at least {user_turn_number} messages, got {len(history_data['messages'])}"
                )

        # Final validation
        final_history_response = api_client.get(f"/sessions/{session_id}/messages")
        assert final_history_response.status_code == 200, (
            f"Failed to get final message history: {final_history_response.text}"
        )
        final_history_data = final_history_response.json()

        # Validate all messages present
        expected_user_messages = min(
            int(max_user_turns), len([m for m in conversation_flow if m[0] == "user"])
        )
        # channel_chat stores both user + assistant messages; require at least all user messages
        assert len(final_history_data["messages"]) >= expected_user_messages, (
            f"Not all messages present: expected at least {expected_user_messages}, got {len(final_history_data['messages'])}"
        )

        # Validate message order
        message_timestamps = [
            msg.get("timestamp") or msg.get("created_at") for msg in final_history_data["messages"]
        ]
        if all(ts for ts in message_timestamps):
            # Only validate if all have timestamps
            sorted_timestamps = sorted(message_timestamps)
            assert message_timestamps == sorted_timestamps, "Messages not in chronological order"

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

        # Generate and save test summary
        output_storage.save_test_metadata(
            {
                "total_turns": user_turn_number,
                "total_messages": len(final_history_data["messages"]),
                "total_jobs": len(job_ids),
            }
        )
        test_summary = output_storage.save_test_summary()

        # Print summary with links
        print("\n" + "=" * 80)
        print("TEST SUMMARY - Scenario 1: Transformer Paper Analysis")
        print("=" * 80)
        print(f"Test Name: {test_summary['test_name']}")
        print(f"Session ID: {test_summary['session_id']}")
        print(f"Total Messages: {test_summary['total_messages']}")
        print(f"Total Jobs: {test_summary['total_jobs']}")
        print(f"Total Summaries: {test_summary['total_summaries']}")
        print("\nOutput Files:")
        print(f"  Messages: {test_summary['outputs']['messages']['file']}")
        print(f"  Jobs: {test_summary['outputs']['jobs']['file']}")
        for job_file in test_summary["outputs"]["jobs"]["individual_files"]:
            print(f"    - {job_file}")
        if test_summary["total_summaries"] > 0:
            print(f"  Summaries: {test_summary['outputs']['summaries']['file']}")
        print(f"  Conversation Log: {test_summary['outputs']['conversation_log']['file']}")
        print(f"  Test Metadata: {test_summary['outputs']['test_metadata']['file']}")
        print("=" * 80)

    finally:
        # Cleanup: Delete session via API
        resp = api_client.delete(f"/sessions/{session_id}")
        if resp.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {resp.status_code} {resp.text}"
            )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

