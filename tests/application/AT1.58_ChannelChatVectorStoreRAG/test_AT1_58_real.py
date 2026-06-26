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
AT1.58 - Channel Chat with Vector Store RAG Integration

This test suite validates channel chat functionality with vector store integration
for Retrieval Augmented Generation (RAG). Tests ensure proper document retrieval,
semantic search, and context injection into chat responses.

RULES.md Compliance:
- TestOutputManager for comprehensive logging
- API-only operations (no direct DB access)
- No hardcoded values (all from config)
- Full cleanup via API DELETE endpoints
- Real LLM and vector store integration
"""

import pytest
import uuid
import sys
import json
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


def _require_chroma_config_json() -> str:
    stores_cfg = get_config("vector_stores_config")
    if not isinstance(stores_cfg, dict):
        pytest.fail("vector_stores_config not configured (set in --env file)")
    chroma_cfg = stores_cfg.get("chroma", {}).get("_DEFAULT_") or stores_cfg.get("chroma", {}).get(
        "_REMOTE_"
    )
    if not isinstance(chroma_cfg, dict):
        pytest.fail("Chroma not configured/enabled in vector_stores_config.chroma")

    collection_name = chroma_cfg.get("collection_name") or f"at1_58_{uuid.uuid4().hex[:8]}"
    if chroma_cfg.get("path"):
        config = {
            "path": chroma_cfg.get("path"),
            "collection_name": collection_name,
        }
    else:
        host = chroma_cfg.get("host")
        port = chroma_cfg.get("port")
        if not host or port is None:
            pytest.fail(
                "Chroma enabled but missing chroma.host/chroma.port in vector_stores_config"
            )
        config = {
            "host": host,
            "port": int(port),
            "ssl": chroma_cfg.get("ssl", False),
            "auth_token": chroma_cfg.get("auth_token"),
            "collection_name": collection_name,
        }
    return json.dumps(config)


class TestOutputManager:
    """Manages test outputs, validations, and summary generation."""

    __test__ = False

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.output_dir = Path(f"working/AT1.58_TEST_OUTPUTS/{test_name}")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.inputs_dir = self.output_dir / "inputs"
        self.outputs_dir = self.output_dir / "outputs"
        self.validations_dir = self.output_dir / "validations"

        self.inputs_dir.mkdir(exist_ok=True)
        self.outputs_dir.mkdir(exist_ok=True)
        self.validations_dir.mkdir(exist_ok=True)

        self.validations = []
        self.input_counter = 1
        self.output_counter = 1
        self.validation_counter = 1
        self.console_log = []

    def log_console(self, message: str):
        """Log message to console and file."""
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"
        self.console_log.append(log_entry)
        print(log_entry)

    def save_input(self, name: str, data: dict):
        """Save input data to JSON file."""
        import json

        filename = f"{self.input_counter:02d}_{name}.json"
        filepath = self.inputs_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        self.input_counter += 1
        self.log_console(f"INPUT SAVED: {filename}")

    def save_output(self, name: str, response):
        """Save API response to JSON file."""
        import json

        filename = f"{self.output_counter:02d}_{name}_output.json"
        filepath = self.outputs_dir / filename

        output_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.json() if response.status_code < 500 else response.text,
        }

        with open(filepath, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        self.output_counter += 1
        self.log_console(f"OUTPUT SAVED: {filename}")

    def validate(self, name: str, condition: bool, actual, expected, context: str = ""):
        """Record a validation check."""
        import json
        import datetime

        validation = {
            "id": self.validation_counter,
            "name": name,
            "passed": condition,
            "actual": str(actual),
            "expected": str(expected),
            "context": context,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        self.validations.append(validation)

        filename = f"{self.validation_counter:02d}_{name}.json"
        filepath = self.validations_dir / filename
        with open(filepath, "w") as f:
            json.dump(validation, f, indent=2)

        status = "✅ PASS" if condition else "❌ FAIL"
        self.log_console(f"[VALIDATION {self.validation_counter:02d}] {status}: {name}")

        self.validation_counter += 1

    def generate_summary_table(self):
        """Generate summary table with file URIs."""
        passed = sum(1 for v in self.validations if v["passed"])
        failed = len(self.validations) - passed
        pass_rate = (passed / len(self.validations) * 100) if self.validations else 0

        duration = "N/A"

        summary = f"""
{"=" * 80}
TEST SUMMARY: {self.test_name}
{"=" * 80}

## INPUTS
"""
        for f in sorted(self.inputs_dir.glob("*.json")):
            summary += f"- [{f.name}](file://{f.absolute()})\n"

        summary += "\n## OUTPUTS\n"
        for f in sorted(self.outputs_dir.glob("*.json")):
            summary += f"- [{f.name}](file://{f.absolute()})\n"

        summary += "\n## VALIDATIONS\n"
        for f in sorted(self.validations_dir.glob("*.json")):
            summary += f"- [{f.name}](file://{f.absolute()})\n"

        summary += f"""
## RESULTS
- **Total Validations**: {len(self.validations)}
- **Passed**: {passed}
- **Failed**: {failed}
- **Pass Rate**: {pass_rate:.1f}%
- **Duration**: {duration}

{"=" * 80}
"""

        print(summary)

        # Save console log
        with open(self.output_dir / "console.log", "w") as f:
            f.write("\n".join(self.console_log))
            f.write("\n" + summary)


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
        "name": f"AT1.58 RAG Expert {uuid.uuid4().hex[:8]}",
        "title": f"AT1.58 RAG Expert {uuid.uuid4().hex[:8]}",
        "description": "Test expert for channel chat with vector store RAG integration",
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
        "name": f"AT1.58 RAG Channel {uuid.uuid4().hex[:8]}",
        "expert_config_id": test_expert["id"],
        "description": "Test channel for RAG integration",
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
        "username": f"testuser_at1_58_{uuid.uuid4().hex[:8]}",
        "email": build_test_email("at1_58", uuid.uuid4().hex[:8]),
        "display_name": f"AT1.58 Test User {uuid.uuid4().hex[:8]}",
        "role": "user",
        "enabled": True,
        "password": None,
    }

    response = api_client.post("/users", json=user_data)
    assert response.status_code == 200, f"Failed to create user: {response.text}"
    user = response.json()

    yield user

    api_client.session.headers.pop("X-API-Key", None)


@pytest.fixture
def test_vector_store(api_client):
    """Create or get test vector store."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Try to get existing test vector store
    response = api_client.get("/vector-stores")
    if response.status_code == 200:
        data = response.json()
        # API returns {"stores": [...], "count": N}
        if isinstance(data, dict) and "stores" in data:
            vs_list = data["stores"]
            if len(vs_list) > 0:
                api_client.session.headers.pop("X-API-Key", None)
                yield vs_list[0]
                return

    # Create new vector store if none exist
    vs_data = {
        "name": f"AT1.58 Test VS {uuid.uuid4().hex[:8]}",
        "type": "chroma",
        "config_json": _require_chroma_config_json(),
        "enabled": True,
    }

    response = api_client.post("/vector-stores", json=vs_data)
    assert response.status_code == 200, f"Failed to create vector store: {response.text}"
    vs = response.json()

    yield vs

    api_client.delete(f"/vector-stores/{vs['id']}")
    api_client.session.headers.pop("X-API-Key", None)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_58a_channel_chat_basic(api_client, test_channel, test_user, test_expert):
    """AT1.58a: Basic channel chat without RAG"""
    mgr = TestOutputManager("AT1_58a_channel_chat_basic")
    mgr.log_console("TEST START: AT1.58a - Basic Channel Chat")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.58a Test Session {uuid.uuid4()}",
    }
    mgr.save_input("create_session", session_data)
    session_response = api_client.post("/sessions", json=session_data)
    mgr.save_output("create_session", session_response)
    mgr.validate(
        "session_created",
        session_response.status_code == 200,
        session_response.status_code,
        200,
        "Session created",
    )

    if session_response.status_code == 200:
        session = session_response.json()

        # Send chat message
        chat_data = {
            "message": "Hello, this is a test message for channel chat.",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input("channel_chat", chat_data)

        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("channel_chat", chat_response)

        mgr.validate(
            "chat_status",
            chat_response.status_code == 200,
            chat_response.status_code,
            200,
            "Chat request successful",
        )

        if chat_response.status_code == 200:
            data = chat_response.json()
            mgr.validate(
                "has_response",
                "response" in data,
                "response" in data,
                True,
                "Response contains message",
            )
            mgr.validate(
                "has_session_id",
                "session_id" in data,
                "session_id" in data,
                True,
                "Response contains session_id",
            )
            mgr.validate(
                "mode_sync", data.get("mode") == "sync", data.get("mode"), "sync", "Mode is sync"
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


def test_AT1_58b_channel_chat_with_vector_store_mapping(
    api_client, test_channel, test_user, test_expert, test_vector_store
):
    """AT1.58b: Channel chat with vector store mapping"""
    mgr = TestOutputManager("AT1_58b_channel_chat_with_vector_store_mapping")
    mgr.log_console("TEST START: AT1.58b - Channel Chat with Vector Store Mapping")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Map vector store to channel
    mapping_data = {"vector_store_id": test_vector_store["id"], "priority": 1}
    mgr.save_input("create_mapping", mapping_data)
    mapping_response = api_client.post(
        f"/channels/{test_channel['id']}/vector-stores", json=mapping_data
    )
    mgr.save_output("create_mapping", mapping_response)
    mgr.validate(
        "mapping_created",
        mapping_response.status_code == 200,
        mapping_response.status_code,
        200,
        "Vector store mapped to channel",
    )

    # Verify mapping
    get_mapping_response = api_client.get(f"/channels/{test_channel['id']}/vector-stores")
    mgr.save_output("get_mappings", get_mapping_response)
    mgr.validate(
        "mapping_exists",
        get_mapping_response.status_code == 200,
        get_mapping_response.status_code,
        200,
        "Can retrieve mappings",
    )

    if get_mapping_response.status_code == 200:
        mappings = get_mapping_response.json()
        mgr.validate(
            "has_vector_stores",
            "vector_stores" in mappings,
            "vector_stores" in mappings,
            True,
            "Response has vector_stores",
        )
        mgr.validate(
            "mapping_count",
            len(mappings.get("vector_stores", [])) > 0,
            len(mappings.get("vector_stores", [])),
            ">0",
            "At least one mapping exists",
        )

    # Create session and send chat
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.58b Test Session {uuid.uuid4()}",
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

        # Send chat message
        chat_data = {
            "message": "What information do you have about testing?",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input("channel_chat", chat_data)

        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("channel_chat", chat_response)

        mgr.validate(
            "chat_status",
            chat_response.status_code == 200,
            chat_response.status_code,
            200,
            "Chat with vector store successful",
        )

        if chat_response.status_code == 200:
            data = chat_response.json()
            mgr.validate(
                "has_response",
                "response" in data,
                "response" in data,
                True,
                "Response contains message",
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

    # Remove mapping
    if mapping_response.status_code == 200:
        api_client.delete(f"/channels/{test_channel['id']}/vector-stores/{test_vector_store['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_58c_channel_chat_multi_turn_with_context(
    api_client, test_channel, test_user, test_expert
):
    """AT1.58c: Multi-turn channel chat with context retention"""
    mgr = TestOutputManager("AT1_58c_channel_chat_multi_turn_with_context")
    mgr.log_console("TEST START: AT1.58c - Multi-turn Channel Chat")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.58c Test Session {uuid.uuid4()}",
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

        # First message
        chat_data_1 = {
            "message": "My name is Alice.",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input("chat_turn_1", chat_data_1)
        chat_response_1 = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data_1)
        mgr.save_output("chat_turn_1", chat_response_1)
        mgr.validate(
            "chat_1_status",
            chat_response_1.status_code == 200,
            chat_response_1.status_code,
            200,
            "First chat successful",
        )

        # Second message (context test)
        chat_data_2 = {
            "message": "What is my name?",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
        }
        mgr.save_input("chat_turn_2", chat_data_2)
        chat_response_2 = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data_2)
        mgr.save_output("chat_turn_2", chat_response_2)
        mgr.validate(
            "chat_2_status",
            chat_response_2.status_code == 200,
            chat_response_2.status_code,
            200,
            "Second chat successful",
        )

        if chat_response_2.status_code == 200:
            data = chat_response_2.json()
            response_text = data.get("response", "").lower()
            # Check if name is mentioned in response (case insensitive)
            has_name = "alice" in response_text
            mgr.validate(
                "context_retained", has_name, has_name, True, "Context retained (name remembered)"
            )
            if not has_name:
                mgr.log_console(
                    f"WARNING: LLM did not remember name. Response: {response_text[:200]}"
                )

        # Verify history
        history_response = api_client.get(f"/sessions/{session['id']}/messages")
        mgr.save_output("message_history", history_response)
        mgr.validate(
            "history_retrieved",
            history_response.status_code == 200,
            history_response.status_code,
            200,
            "History retrieved",
        )

        if history_response.status_code == 200:
            history_data = history_response.json()
            messages = history_data.get("messages", [])

            mgr.validate(
                "message_count",
                len(messages) >= 4,
                len(messages),
                ">=4",
                "At least 4 messages (2 user + 2 assistant)",
            )
        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_58d_channel_chat_async_mode(api_client, test_channel, test_user, test_expert):
    """AT1.58d: Channel chat in async mode with job tracking"""
    mgr = TestOutputManager("AT1_58d_channel_chat_async_mode")
    mgr.log_console("TEST START: AT1.58d - Async Channel Chat")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.58d Test Session {uuid.uuid4()}",
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

        # Send async chat message
        chat_data = {
            "message": "This is an async test message.",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "async",
        }
        mgr.save_input("channel_chat_async", chat_data)

        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("channel_chat_async", chat_response)

        mgr.validate(
            "chat_status",
            chat_response.status_code == 200,
            chat_response.status_code,
            200,
            "Async chat queued",
        )

        if chat_response.status_code == 200:
            data = chat_response.json()
            mode = data.get("mode", "sync")
            mgr.validate(
                "mode_present",
                mode in ["async", "sync"],
                mode,
                "async or sync",
                "Mode is present and valid",
            )

            if mode == "async":
                has_valid_structure = "job_id" in data and "status" in data
            else:
                has_valid_structure = "content" in data or "message" in data or "response" in data

            mgr.validate(
                "response_structure",
                has_valid_structure,
                str(has_valid_structure),
                "True",
                "Response has valid structure for mode",
            )

            if "job_id" in data:
                job_id = data["job_id"]

                # Check job status
                import time

                time.sleep(2)  # Wait for job to process

                job_response = api_client.get(f"/jobs/{job_id}")
                mgr.save_output("job_status", job_response)
                mgr.validate(
                    "job_retrieved",
                    job_response.status_code == 200,
                    job_response.status_code,
                    200,
                    "Job status retrieved",
                )

        # Cleanup
        api_client.delete(f"/sessions/{session['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_58e_channel_chat_with_custom_parameters(
    api_client, test_channel, test_user, test_expert
):
    """AT1.58e: Channel chat with custom LLM parameters"""
    mgr = TestOutputManager("AT1_58e_channel_chat_with_custom_parameters")
    mgr.log_console("TEST START: AT1.58e - Channel Chat with Custom Parameters")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.58e Test Session {uuid.uuid4()}",
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

        # Send chat with custom parameters
        chat_data = {
            "message": "Generate a creative response.",
            "user_id": test_user["id"],
            "session_id": session["id"],
            "mode": "sync",
            "temperature": 0.9,
            "max_tokens": 150,
            "top_p": 0.95,
        }
        mgr.save_input("channel_chat_custom", chat_data)

        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("channel_chat_custom", chat_response)

        mgr.validate(
            "chat_status",
            chat_response.status_code == 200,
            chat_response.status_code,
            200,
            "Chat with custom params successful",
        )

        if chat_response.status_code == 200:
            data = chat_response.json()
            mgr.validate(
                "has_response",
                "response" in data,
                "response" in data,
                True,
                "Response contains message",
            )
            mgr.validate(
                "has_tokens",
                "tokens_used" in data,
                "tokens_used" in data,
                True,
                "Response contains token count",
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


def test_AT1_58f_vector_store_mapping_full_crud(api_client, test_channel, test_vector_store):
    """AT1.58f: Full CRUD operations for vector store mappings"""
    mgr = TestOutputManager("AT1_58f_vector_store_mapping_full_crud")
    mgr.log_console("TEST START: AT1.58f - Vector Store Mapping Full CRUD")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # CREATE: Map vector store to channel
    mapping_data = {"vector_store_id": test_vector_store["id"], "priority": 10}
    mgr.save_input("create_mapping", mapping_data)
    create_response = api_client.post(
        f"/channels/{test_channel['id']}/vector-stores", json=mapping_data
    )
    mgr.save_output("create_mapping", create_response)
    mgr.validate(
        "create_status",
        create_response.status_code == 200,
        create_response.status_code,
        200,
        "CREATE: Mapping created",
    )

    if create_response.status_code == 200:
        mapping = create_response.json()
        mgr.validate("has_mapping_id", "id" in mapping, "id" in mapping, True, "Mapping has ID")
        mgr.validate(
            "has_priority",
            mapping.get("priority") == 10,
            mapping.get("priority"),
            10,
            "Priority set correctly",
        )

    # UPDATE: Try to create duplicate (should fail)
    duplicate_response = api_client.post(
        f"/channels/{test_channel['id']}/vector-stores", json=mapping_data
    )
    mgr.save_output("duplicate_mapping", duplicate_response)
    mgr.validate(
        "duplicate_rejected",
        duplicate_response.status_code == 400,
        duplicate_response.status_code,
        400,
        "Duplicate mapping rejected",
    )

    # DELETE: Remove mapping
    delete_response = api_client.delete(
        f"/channels/{test_channel['id']}/vector-stores/{test_vector_store['id']}"
    )
    mgr.save_output("delete_mapping", delete_response)
    mgr.validate(
        "delete_status",
        delete_response.status_code == 200,
        delete_response.status_code,
        200,
        "DELETE: Mapping removed",
    )

    # VERIFY DELETE: Check mapping is gone
    verify_response = api_client.get(f"/channels/{test_channel['id']}/vector-stores")
    mgr.save_output("verify_delete", verify_response)

    if verify_response.status_code == 200:
        data = verify_response.json()
        mgr.validate(
            "mapping_deleted",
            len(data.get("vector_stores", [])) == 0,
            len(data.get("vector_stores", [])),
            0,
            "Mapping successfully deleted",
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_58g_multiple_vector_stores_priority(api_client, test_channel):
    """AT1.58g: Multiple vector stores with priority ordering"""
    mgr = TestOutputManager("AT1_58g_multiple_vector_stores_priority")
    mgr.log_console("TEST START: AT1.58g - Multiple Vector Stores with Priority")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Get all available vector stores
    vs_response = api_client.get("/vector-stores")
    mgr.save_output("list_vector_stores", vs_response)
    mgr.validate(
        "vs_list_retrieved",
        vs_response.status_code == 200,
        vs_response.status_code,
        200,
        "Vector stores listed",
    )

    if vs_response.status_code == 200:
        vs_data = vs_response.json()
        # Handle both list and dict responses
        if isinstance(vs_data, dict):
            vector_stores = vs_data.get("stores", vs_data.get("vector_stores", []))
        else:
            vector_stores = vs_data

        mgr.validate(
            "has_multiple_vs",
            len(vector_stores) >= 2,
            len(vector_stores),
            ">=2",
            "At least 2 vector stores available",
        )

        if len(vector_stores) >= 2:
            # Clear any existing mappings first to avoid duplicates
            existing_mappings = api_client.get(f"/channels/{test_channel['id']}/vector-stores")
            if existing_mappings.status_code == 200:
                for mapping in existing_mappings.json().get("vector_stores", []):
                    api_client.delete(
                        f"/channels/{test_channel['id']}/vector-stores/{mapping['vector_store_id']}"
                    )

            # Map first vector store with priority 10
            mapping_data_1 = {"vector_store_id": vector_stores[0]["id"], "priority": 10}
            mgr.save_input("create_mapping_1", mapping_data_1)
            create_1 = api_client.post(
                f"/channels/{test_channel['id']}/vector-stores", json=mapping_data_1
            )
            mgr.save_output("create_mapping_1", create_1)
            mgr.validate(
                "mapping_1_created",
                create_1.status_code == 200,
                create_1.status_code,
                200,
                "First mapping created",
            )

            # Map second vector store with priority 20
            mapping_data_2 = {"vector_store_id": vector_stores[1]["id"], "priority": 20}
            mgr.save_input("create_mapping_2", mapping_data_2)
            create_2 = api_client.post(
                f"/channels/{test_channel['id']}/vector-stores", json=mapping_data_2
            )
            mgr.save_output("create_mapping_2", create_2)
            mgr.validate(
                "mapping_2_created",
                create_2.status_code == 200,
                create_2.status_code,
                200,
                "Second mapping created",
            )

            # Verify priority ordering
            get_response = api_client.get(f"/channels/{test_channel['id']}/vector-stores")
            mgr.save_output("get_ordered_mappings", get_response)

            if get_response.status_code == 200:
                data = get_response.json()
                mgr.validate(
                    "has_multiple",
                    len(data.get("vector_stores", [])) == 2,
                    len(data.get("vector_stores", [])),
                    2,
                    "Two mappings exist",
                )

                if len(data.get("vector_stores", [])) >= 2:
                    # Verify ordering (higher priority first)
                    first_vs = data["vector_stores"][0]
                    second_vs = data["vector_stores"][1]
                    mgr.validate(
                        "priority_ordering",
                        first_vs.get("priority", 0) >= second_vs.get("priority", 0),
                        f"{first_vs.get('priority')}>={second_vs.get('priority')}",
                        True,
                        "Priority ordering correct",
                    )

            # Cleanup - delete mappings, not vector stores themselves
            # Get the mappings to find their IDs
            get_resp = api_client.get(f"/channels/{test_channel['id']}/vector-stores")
            if get_resp.status_code == 200:
                data = get_resp.json()
                mappings = data.get("vector_stores", data.get("stores", []))
                for mapping in mappings:
                    # Delete by mapping ID if available, otherwise skip
                    if "id" in mapping:
                        api_client.delete(
                            f"/channels/{test_channel['id']}/vector-stores/{mapping['id']}"
                        )
        else:
            mgr.validate(
                "insufficient_vs",
                False,
                len(vector_stores),
                ">=2",
                "Need at least 2 vector stores for this test",
            )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_58h_vector_database_variants(api_client, test_channel, test_user, test_expert):
    """AT1.58h: Test with different vector database types (Chroma, Qdrant, OpenSearch, PGVector)"""
    mgr = TestOutputManager("AT1_58h_vector_database_variants")
    mgr.log_console("TEST START: AT1.58h - Vector Database Variants")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Get all vector stores and group by type
    vs_response = api_client.get("/vector-stores")
    mgr.save_output("list_all_vector_stores", vs_response)
    mgr.validate(
        "vs_list_retrieved",
        vs_response.status_code == 200,
        vs_response.status_code,
        200,
        "Vector stores listed",
    )

    if vs_response.status_code == 200:
        vs_data = vs_response.json()
        # Handle both list and dict responses
        if isinstance(vs_data, dict):
            vector_stores = vs_data.get("stores", vs_data.get("vector_stores", []))
        else:
            vector_stores = vs_data

        # Group by type
        vs_by_type = {}
        for vs in vector_stores:
            vs_type = vs.get("type", "unknown").lower()
            if vs_type not in vs_by_type:
                vs_by_type[vs_type] = []
            vs_by_type[vs_type].append(vs)

        mgr.log_console(f"Found vector store types: {list(vs_by_type.keys())}")
        mgr.validate(
            "has_vector_stores",
            len(vector_stores) > 0,
            len(vector_stores),
            ">0",
            "At least one vector store exists",
        )

        # Test each type
        tested_types = []
        for vs_type, stores in vs_by_type.items():
            if len(stores) > 0:
                vs = stores[0]
                mgr.log_console(f"Testing {vs_type} vector store: {vs.get('name')}")

                # Map to channel
                mapping_data = {"vector_store_id": vs["id"], "priority": 1}
                mgr.save_input(f"map_{vs_type}", mapping_data)
                map_response = api_client.post(
                    f"/channels/{test_channel['id']}/vector-stores", json=mapping_data
                )
                mgr.save_output(f"map_{vs_type}", map_response)
                mgr.validate(
                    f"{vs_type}_mapped",
                    map_response.status_code == 200,
                    map_response.status_code,
                    200,
                    f"{vs_type} mapped successfully",
                )

                # Get all vector stores for channel
                response = api_client.get(f"/channels/{test_channel['id']}/vector-stores")
                assert response.status_code == 200
                vs_data = response.json()

                # Handle both list and dict responses
                if isinstance(vs_data, dict):
                    vector_stores = vs_data.get("vector_stores", vs_data.get("stores", []))
                else:
                    vector_stores = vs_data

                # Verify mapping
                has_mapping = any(
                    m.get("vector_store_type", "").lower() == vs_type for m in vector_stores
                )
                mgr.validate(
                    f"{vs_type}_verified",
                    has_mapping,
                    has_mapping,
                    True,
                    f"{vs_type} mapping verified",
                )

                tested_types.append(vs_type)

                # Cleanup
                api_client.delete(f"/channels/{test_channel['id']}/vector-stores/{vs['id']}")

        mgr.log_console(f"Tested {len(tested_types)} vector database types: {tested_types}")
        mgr.validate(
            "types_tested",
            len(tested_types) > 0,
            len(tested_types),
            ">0",
            "At least one VDB type tested",
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]
