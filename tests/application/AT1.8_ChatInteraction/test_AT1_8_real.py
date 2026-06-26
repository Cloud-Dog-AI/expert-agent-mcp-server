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
AT1.8 - Chat Interaction Tests (RULES.md Compliant)
100% API-only, TestOutputManager, no hardcoded values
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import APIClient
import pytest
import uuid
import json
from datetime import datetime
from src.config.loader import get_config


class TestOutputManager:
    __test__ = False

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working/AT1.8_TEST_OUTPUTS") / test_name
        self.inputs_dir = self.base_dir / "inputs"
        self.outputs_dir = self.base_dir / "outputs"
        self.validations_dir = self.base_dir / "validations"
        self.console_log = []
        self.validations = []
        self.start_time = datetime.now()
        for d in [self.inputs_dir, self.outputs_dir, self.validations_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def log_console(self, message: str):
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")[:-3]
        log_entry = f"{timestamp} {message}"
        self.console_log.append(log_entry)
        print(log_entry)

    def save_input(self, name: str, data):
        counter = len([f for f in self.inputs_dir.glob("*.json")]) + 1
        filepath = self.inputs_dir / f"{counter:02d}_{name}_input.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        self.log_console(f"Input saved: {name}")

    def save_output(self, name: str, response):
        counter = len([f for f in self.outputs_dir.glob("*.json")]) + 1
        filepath = self.outputs_dir / f"{counter:02d}_{name}_output.json"
        output_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text,
        }
        with open(filepath, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        self.log_console(f"Output saved: {name}")

    def validate(self, name: str, condition: bool, actual, expected, context: str = ""):
        validation_num = len(self.validations) + 1
        passed = bool(condition)
        validation = {
            "number": validation_num,
            "name": name,
            "passed": passed,
            "actual": str(actual),
            "expected": str(expected),
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }
        self.validations.append(validation)
        filepath = self.validations_dir / f"{validation_num:02d}_{name}.json"
        with open(filepath, "w") as f:
            json.dump(validation, f, indent=2)
        status = "✅ PASS" if passed else "❌ FAIL"
        self.log_console(f"[VALIDATION {validation_num:02d}] {status}: {name}")
        if not passed:
            self.log_console(f"  Expected: {expected}, Actual: {actual}")

    def generate_summary_table(self):
        duration = (datetime.now() - self.start_time).total_seconds()
        passed = sum(1 for v in self.validations if v["passed"])
        failed = len(self.validations) - passed
        rate = (passed / len(self.validations) * 100) if self.validations else 0
        console_path = self.base_dir / "console.log"
        with open(console_path, "w") as f:
            f.write("\n".join(self.console_log))
        summary = f"\n{'=' * 80}\nTEST SUMMARY: {self.test_name}\n{'=' * 80}\nValidations: {len(self.validations)} | Passed: {passed} | Failed: {failed} | Rate: {rate:.1f}%\nDuration: {duration:.2f}s\n{'=' * 80}\n"
        summary_path = self.base_dir / "SUMMARY.md"
        with open(summary_path, "w") as f:
            f.write(summary)
        print(summary)
        return summary


@pytest.fixture(scope="module")
def api_client():
    api_host = get_config("api_server.host")
    api_port = get_config("api_server.port")
    if not api_host or api_port is None:
        pytest.fail("Missing api_server.host/api_server.port in config (--env)")
    base_url = f"http://{api_host}:{int(api_port)}"
    client = APIClient(base_url)
    response = client.get("/health")
    if response.status_code != 200:
        pytest.fail(f"API server not healthy at {base_url}/health")
    return client


def get_admin_api_key():
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set in secrets env file)")
    return str(api_key)


@pytest.fixture
def test_user(api_client):
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")
    if not base_username or not base_email or not base_password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    unique_id = str(uuid.uuid4())[:8]
    username = f"{base_username}_at18_{unique_id}"
    email = f"at18_{unique_id}@{base_email.split('@')[1]}"
    response = api_client.post(
        "/users",
        json={
            "username": username,
            "email": email,
            "password": base_password,
            "display_name": f"AT1.8 User {unique_id}",
            "role": "user",
        },
    )
    assert response.status_code == 200, f"Failed to create user: {response.text}"
    user_data = response.json()
    user_data["password"] = base_password
    api_client.session.headers.pop("X-API-Key", None)
    yield user_data
    api_client.session.headers["X-API-Key"] = admin_key
    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass
    finally:
        api_client.session.headers.pop("X-API-Key", None)


@pytest.fixture
def test_expert(api_client):
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at18_{unique_id}",
        "title": f"AT1.8 Expert {unique_id}",
        "description": f"Test expert for AT1.8 chat interaction testing with unique identifier {unique_id}",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }
    expert_data["llm_base_url"] = llm_base_url
    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create expert: {response.text}"
    expert = response.json()
    api_client.session.headers.pop("X-API-Key", None)
    yield expert
    api_client.session.headers["X-API-Key"] = admin_key
    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass
    finally:
        api_client.session.headers.pop("X-API-Key", None)


@pytest.fixture
def test_session(api_client, test_user, test_expert):
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )
    unique_id = str(uuid.uuid4())[:8]
    response = api_client.post(
        "/sessions",
        json={
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": f"AT1.8 Session {unique_id}",
            "context_window": int(context_window),
            "history_retention_days": int(history_retention_days),
        },
    )
    assert response.status_code == 200, f"Failed to create session: {response.text}"
    session_data = response.json()
    # Session creation should already return an active session; no direct DB access permitted in AT tests.
    yield session_data
    api_client.session.headers["X-API-Key"] = admin_key
    try:
        api_client.delete(f"/sessions/{session_data['id']}")
    except Exception:
        pass
    finally:
        api_client.session.headers.pop("X-API-Key", None)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_8a_message_creation_success(api_client, test_session):
    """AT1.8a: Message creation with valid data"""
    mgr = TestOutputManager("AT1_8a_message_creation_success")
    mgr.log_console("TEST START: AT1.8a - Message Creation Success")
    session_id = test_session["id"]
    unique_id = str(uuid.uuid4())[:8]
    content = f"Test message {unique_id}"
    mgr.save_input("create_message", {"session_id": session_id, "role": "user", "content": content})
    response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": content}
    )
    mgr.save_output("create_message", response)
    mgr.validate(
        "status_code",
        response.status_code == 200,
        response.status_code,
        200,
        "POST /sessions/{id}/messages",
    )
    if response.status_code == 200:
        msg = response.json()
        mgr.validate("has_id", "id" in msg, "id" in msg, True, "Has ID")
        mgr.validate("has_role", "role" in msg, "role" in msg, True, "Has role")
        mgr.validate(
            "role_correct", msg.get("role") == "user", msg.get("role"), "user", "Role matches"
        )
        mgr.validate("has_content", "content" in msg, "content" in msg, True, "Has content")
        mgr.validate(
            "content_correct",
            msg.get("content") == content,
            len(msg.get("content", "")),
            len(content),
            "Content matches",
        )
        mgr.validate("has_timestamp", "timestamp" in msg, "timestamp" in msg, True, "Has timestamp")
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_8b_get_messages_success(api_client, test_session):
    """AT1.8b: Retrieve messages"""
    mgr = TestOutputManager("AT1_8b_get_messages_success")
    mgr.log_console("TEST START: AT1.8b - Get Messages")
    session_id = test_session["id"]
    unique_id = str(uuid.uuid4())[:8]
    create_resp = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": f"Msg {unique_id}"}
    )
    mgr.save_output("create_message", create_resp)
    response = api_client.get(f"/sessions/{session_id}/messages")
    mgr.save_output("get_messages", response)
    mgr.validate(
        "status_code", response.status_code == 200, response.status_code, 200, "GET messages"
    )
    if response.status_code == 200:
        data = response.json()
        mgr.validate("has_messages", "messages" in data, "messages" in data, True, "Has messages")
        mgr.validate("has_count", "count" in data, "count" in data, True, "Has count")
        mgr.validate(
            "is_list",
            isinstance(data.get("messages"), list),
            type(data.get("messages")).__name__,
            "list",
            "Messages is list",
        )
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_8c_invalid_session_404(api_client):
    """AT1.8c: Invalid session returns 404"""
    mgr = TestOutputManager("AT1_8c_invalid_session_404")
    mgr.log_console("TEST START: AT1.8c - Invalid Session 404")
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key
    response = api_client.post(
        "/sessions/999999/messages", json={"role": "user", "content": "fail"}
    )
    mgr.save_output("invalid_session", response)
    api_client.session.headers.pop("X-API-Key", None)
    mgr.validate(
        "status_code", response.status_code == 404, response.status_code, 404, "Returns 404"
    )
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
