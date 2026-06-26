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
Integration Test: IT2.37 - File Ingest -> Vector Store -> MCP Vector Search

License: Apache 2.0
Ownership: Cloud Dog
Copyright:
  (C) Cloud-Dog, Viewdeck Engineering Ltd.

Description:
Validates a cross-interface workflow using real servers:
1) Create vector store via REST API
2) Upload text file via REST API
3) Ingest file into vector store via REST API
4) Query via MCP tool call (streamable HTTP JSON-RPC): tools/call -> vector_search

Rules alignment:
- No mocks/stubs/TestClient.
- Uses config via get_config (--env) and requires real running API + MCP servers.
- Fails hard if configured vector backend is unreachable.
"""

import base64
import json
import time
import uuid
from typing import Any, Dict, Tuple

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.integration


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_base_url(section: str) -> str:
    base = get_config(f"{section}.base_url")
    if base:
        return str(base).rstrip("/")
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    if not host or port is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{host}:{int(port)}"


def _mcp_health_url(base_url: str) -> str:
    return f"{base_url}/health" if base_url.endswith("/mcp") else f"{base_url}/mcp/health"


def _mcp_rpc_url(base_url: str) -> str:
    return base_url if base_url.endswith("/mcp") else f"{base_url}/mcp"


def _require_health(session: requests.Session, url: str, timeout: float, label: str) -> None:
    last_status = None
    last_error = None
    for attempt in range(6):
        try:
            response = session.get(url, timeout=timeout)
            last_status = response.status_code
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = exc
        if attempt < 5:
            time.sleep(0.5)
    if last_status is not None:
        pytest.fail(f"{label} not healthy at {url} (status {last_status})")
    pytest.fail(f"{label} not reachable at {url}: {last_error}")


def _pick_vector_profile(store_type: str) -> Tuple[str, Dict[str, Any]]:
    profiles = get_config(f"vector_stores_config.{store_type}")
    if not isinstance(profiles, dict) or not profiles:
        pytest.fail(f"vector_stores_config.{store_type} not configured")

    for name, cfg in profiles.items():
        if not isinstance(cfg, dict):
            continue
        enabled = cfg.get("enabled")
        if enabled is False:
            continue

        if store_type == "qdrant":
            host = cfg.get("host")
            port = cfg.get("port")
            collection = cfg.get("collection_name")
            if host and port and collection:
                out = {
                    "host": str(host),
                    "port": int(port),
                    "collection_name": str(collection),
                }
                if cfg.get("api_key"):
                    out["api_key"] = str(cfg.get("api_key"))
                return str(name), out
        elif store_type == "chroma":
            path = cfg.get("path")
            server_url = cfg.get("server_url")
            host = cfg.get("host")
            if path or server_url or host:
                out = {}
                if path:
                    out["path"] = str(path)
                if server_url:
                    out["server_url"] = str(server_url)
                if host:
                    out["host"] = str(host)
                if cfg.get("port") is not None:
                    out["port"] = int(cfg.get("port"))
                if cfg.get("collection_name"):
                    out["collection_name"] = str(cfg.get("collection_name"))
                return str(name), out

    pytest.fail(f"No enabled usable profile found for vector store type '{store_type}'")


def _mcp_initialize(mcp_session: requests.Session, base_url: str, timeout: float) -> str:
    req_id = uuid.uuid4().hex[:8]
    r = mcp_session.post(
        _mcp_rpc_url(base_url),
        json={
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "it2.37", "version": "0.1"},
            },
        },
        timeout=timeout,
    )
    assert r.status_code == 200, r.text
    session_id = r.headers.get("Mcp-Session-Id")
    if not session_id:
        pytest.fail("MCP initialize did not return Mcp-Session-Id header")
    return str(session_id)


def _mcp_tool_call(
    mcp_session: requests.Session,
    base_url: str,
    session_id: str,
    timeout: float,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    req_id = uuid.uuid4().hex[:8]
    r = mcp_session.post(
        _mcp_rpc_url(base_url),
        headers={"Mcp-Session-Id": session_id},
        json={
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
        timeout=timeout,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    if data.get("error"):
        pytest.fail(f"MCP tools/call error: {data['error']}")
    result = data.get("result")
    if not isinstance(result, dict):
        pytest.fail("MCP tools/call missing result dict")
    return result


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api_url = _require_base_url("api_server")
    mcp_url = _require_base_url("mcp_server")

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    _require_health(api, f"{api_url}/health", timeout, "API server")

    mcp = requests.Session()
    mcp.headers.update({"X-API-Key": str(api_key)})  # MCP tool calls are auth-gated (W28C-1704)
    _require_health(mcp, _mcp_health_url(mcp_url), timeout, "MCP server")

    return {"api": api, "mcp": mcp, "api_url": api_url, "mcp_url": mcp_url, "timeout": timeout}
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_file_ingest_then_mcp_vector_search(clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = clients["timeout"]

    store_type = get_config("vector.store.type")
    if not store_type:
        pytest.fail("vector.store.type not configured")
    profile_name, persisted_cfg = _pick_vector_profile(str(store_type))

    unique = uuid.uuid4().hex[:8]
    vector_store_name = f"it237_{profile_name}_{unique}"
    create_cfg = dict(persisted_cfg)
    collection_name = create_cfg.get("collection_name") or create_cfg.get("index_name")
    if collection_name:
        isolated_collection = f"{collection_name}_{unique}"
        if "collection_name" in create_cfg:
            create_cfg["collection_name"] = isolated_collection
        if "index_name" in create_cfg:
            create_cfg["index_name"] = isolated_collection
        collection_name = isolated_collection

    created = api.post(
        f"{api_url}/vector-stores",
        json={
            "name": vector_store_name,
            "store_type": str(store_type),
            "config": create_cfg,
            "enabled": True,
        },
        timeout=timeout,
    )
    assert created.status_code == 200, created.text
    store_id = int(created.json()["id"])

    try:
        health = api.get(f"{api_url}/vector-stores/{store_id}/health", timeout=timeout)
        assert health.status_code == 200, health.text

        token = f"IT237_TOKEN_{unique}"
        text = f"Integration token {token}\n"
        uploaded = api.post(
            f"{api_url}/files/upload_base64",
            json={
                "filename": f"it237_{unique}.txt",
                "content_base64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                "metadata": {"it": True, "token": token},
            },
            timeout=timeout,
        )
        assert uploaded.status_code == 200, uploaded.text
        file_id = int(uploaded.json()["file"]["id"])

        try:
            ingested = api.post(
                f"{api_url}/files/{file_id}/ingest_to_vector_store",
                json={
                    "vector_store_id": store_id,
                    "collection": collection_name,
                    "metadata": {"token": token},
                },
                timeout=timeout,
            )
            assert ingested.status_code == 200, ingested.text
            assert ingested.json().get("success") is True

            mcp = clients["mcp"]
            mcp_url = clients["mcp_url"]
            mcp_session_id = _mcp_initialize(mcp, mcp_url, timeout)
            try:
                result = _mcp_tool_call(
                    mcp,
                    mcp_url,
                    mcp_session_id,
                    timeout,
                    "vector_search",
                    {
                        "query": token,
                        "collection": collection_name,
                        "n_results": 3,
                        "vector_store_name": vector_store_name,
                    },
                )
                # Streamable HTTP tool results follow MCP "content" contract. Our server also
                # attaches structuredContent for testability; accept either.
                payload = result.get("structuredContent")
                if payload is None:
                    content = result.get("content") or []
                    if not content or not isinstance(content, list) or not content[0].get("text"):
                        pytest.fail("MCP tools/call missing content text")
                    payload = json.loads(content[0]["text"])

                assert int(payload.get("count", 0)) >= 1
                results = payload.get("results") or []
                assert any(
                    str(r.get("metadata", {}).get("file_id")) == str(file_id) for r in results
                )
            finally:
                # Terminate MCP session explicitly.
                mcp.delete(
                    _mcp_rpc_url(mcp_url),
                    headers={"Mcp-Session-Id": mcp_session_id},
                    timeout=timeout,
                )
        finally:
            api.delete(f"{api_url}/files/{file_id}", timeout=timeout)
    finally:
        api.delete(f"{api_url}/vector-stores/{store_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.vdb, pytest.mark.mcp, pytest.mark.heavy]
