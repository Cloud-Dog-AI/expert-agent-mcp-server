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

import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from src.config.loader import get_config, load_config


def _base(section: str) -> str:
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"


class _WebhookServer:
    def __init__(self):
        self.requests = queue.Queue()
        self.server = None
        self.thread = None

    def start(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                parent.requests.put((self.path, dict(self.headers), body))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}/hook"

    def wait(self, timeout=20):
        try:
            return self.requests.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    if not key:
        pytest.fail("test.api_key not configured")
    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})
    s.timeout_seconds = timeout
    return {"api": s, "api_url": _base("api_server")}
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st127_channel_sync_async_webhook_contract(clients):
    api, api_url = clients["api"], clients["api_url"]
    u = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]

    user = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_st127_{u}",
            "email": f"st127_{u}@{domain}",
            "password": str(password),
            "display_name": f"ST127 {u}",
        },
        timeout=api.timeout_seconds,
    )
    assert user.status_code == 200, user.text
    user_id = int(user.json()["id"])

    expert = api.post(
        f"{api_url}/experts",
        json={
            "name": f"st127_expert_{u}",
            "title": f"ST127 Expert {u}",
            "description": f"ST1.27 sync/async webhook contract expert token {u}.",
            "llm_provider": str(get_config("llm.provider")),
            "llm_model": str(get_config("llm.model")),
            "llm_base_url": str(get_config("llm.base_url")),
            "llm_api_key": get_config("llm.api_key"),
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert expert.status_code == 200, expert.text
    expert_id = int(expert.json()["id"])

    channel = api.post(
        f"{api_url}/channels",
        json={
            "name": f"ST127 Channel {u}",
            "expert_config_id": expert_id,
            "description": f"sync async webhook contract {u}",
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert channel.status_code == 200, channel.text
    channel_id = int(channel.json()["id"])

    hook = _WebhookServer()
    hook.start()

    try:
        sync_resp = api.post(
            f"{api_url}/channels/{channel_id}/chat",
            json={"message": "sync readiness", "user_id": user_id, "async_mode": False},
            timeout=api.timeout_seconds,
        )
        assert sync_resp.status_code == 200, sync_resp.text
        sync_data = sync_resp.json()
        assert sync_data.get("mode") == "sync"
        assert "response" in sync_data

        async_resp = api.post(
            f"{api_url}/channels/{channel_id}/chat",
            json={
                "message": "async readiness",
                "user_id": user_id,
                "async_mode": True,
                "webhook_url": hook.url,
            },
            timeout=api.timeout_seconds,
        )
        assert async_resp.status_code == 200, async_resp.text
        async_data = async_resp.json()
        assert async_data.get("mode") == "async"
        job_id = int(async_data["job_id"])

        # Poll using environment timeout budget because real LLM backends can
        # legitimately take longer than a fixed 20s window in shared test rigs.
        final_status = None
        poll_budget_seconds = max(int(api.timeout_seconds), 20)
        poll_attempts = max(int(poll_budget_seconds / 0.5), 40)
        for _ in range(poll_attempts):
            job = api.get(f"{api_url}/jobs/{job_id}", timeout=api.timeout_seconds)
            assert job.status_code == 200, job.text
            status = job.json().get("status")
            if status in {"completed", "failed"}:
                final_status = status
                break
            time.sleep(0.5)
        assert final_status in {"completed", "failed"}

        delivered = hook.wait(timeout=30)
        assert delivered is not None, "Expected webhook callback delivery"
        _, _, body = delivered
        text = body.decode("utf-8")
        assert str(job_id) in text
        assert "status" in text
    finally:
        hook.stop()
        api.delete(f"{api_url}/channels/{channel_id}", timeout=api.timeout_seconds)
        api.delete(f"{api_url}/experts/{expert_id}", timeout=api.timeout_seconds)
        api.delete(f"{api_url}/users/{user_id}", timeout=api.timeout_seconds)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

