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
System Test: ST1.46 - File Ingest -> Vector Store -> Query

License: Apache 2.0
Ownership: Cloud Dog
Copyright:
  (C) Cloud-Dog, Viewdeck Engineering Ltd.

Description:
Validates the REST file ingest pipeline against a running API server:
1) Create a vector store configuration (no embedded secrets; runtime secrets come from env profiles)
2) Upload a UTF-8 text file via /files/upload_base64
3) Ingest the file into the vector store via /files/{id}/ingest_to_vector_store
4) Query the vector store via /vector-stores/{id}/query and confirm results

Rules alignment:
- No mocks/stubs/TestClient.
- Uses config via get_config (--env) and requires real running API server.
- Fails hard if the configured vector backend is unreachable.
"""

import base64
import time
import uuid
from typing import Any, Dict, Tuple

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.system


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_api_base_url() -> str:
    host = get_config("api_server.host")
    port = get_config("api_server.port")
    if not host or port is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{host}:{int(port)}"


def _wait_for_health(session: requests.Session, base_url: str, timeout: float) -> None:
    last_error = None
    for _ in range(20):
        try:
            r = session.get(f"{base_url}/health", timeout=timeout)
            if r.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"API server not healthy at {base_url}/health. last_error={last_error}")


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

        # Normalized, minimal contract used for persisted VectorStore.config_json.
        if store_type == "qdrant":
            host = cfg.get("host")
            port = cfg.get("port")
            collection = cfg.get("collection_name")
            if host and port and collection:
                return str(name), {
                    "host": str(host),
                    "port": int(port),
                    "collection_name": str(collection),
                }
        elif store_type == "chroma":
            # Accept either local path or remote-style host/port.
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
        else:
            # Keep strict for system-level verification: require a known store type.
            continue

    pytest.fail(f"No enabled usable profile found for vector store type '{store_type}'")


@pytest.fixture
def api_client(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    base_url = _require_api_base_url()
    s = requests.Session()
    s.headers.update({"X-API-Key": str(api_key)})
    _wait_for_health(s, base_url, timeout)
    s.base_url = base_url
    s.timeout_seconds = timeout
    return s
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_file_ingest_to_vector_store_then_query(api_client):
    store_type = get_config("vector.store.type")
    if not store_type:
        pytest.fail("vector.store.type not configured")

    profile_name, persisted_cfg = _pick_vector_profile(str(store_type))
    unique = uuid.uuid4().hex[:8]
    vector_store_name = f"st146_{profile_name}_{unique}"

    created = api_client.post(
        f"{api_client.base_url}/vector-stores",
        json={
            "name": vector_store_name,
            "store_type": str(store_type),
            "config": persisted_cfg,
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert created.status_code == 200, created.text
    store_id = int(created.json()["id"])

    try:
        health = api_client.get(
            f"{api_client.base_url}/vector-stores/{store_id}/health",
            timeout=api_client.timeout_seconds,
        )
        assert health.status_code == 200, health.text

        token = f"ST146_TOKEN_{unique}"
        original_text = f"File ingest token {token}\nSecond line.\n"
        upload = api_client.post(
            f"{api_client.base_url}/files/upload_base64",
            json={
                "filename": f"st146_{unique}.txt",
                "content_base64": base64.b64encode(original_text.encode("utf-8")).decode("ascii"),
                "metadata": {"st": True, "token": token},
            },
            timeout=api_client.timeout_seconds,
        )
        assert upload.status_code == 200, upload.text
        file_id = int(upload.json()["file"]["id"])

        try:
            ingested = api_client.post(
                f"{api_client.base_url}/files/{file_id}/ingest_to_vector_store",
                json={
                    "vector_store_id": store_id,
                    "collection": persisted_cfg.get("collection_name")
                    or persisted_cfg.get("index_name"),
                    "metadata": {"token": token},
                },
                timeout=api_client.timeout_seconds,
            )
            assert ingested.status_code == 200, ingested.text
            assert ingested.json().get("success") is True

            query = api_client.post(
                f"{api_client.base_url}/vector-stores/{store_id}/query",
                json={
                    "collection": persisted_cfg.get("collection_name")
                    or persisted_cfg.get("index_name"),
                    "query": token,
                    "n_results": 3,
                },
                timeout=api_client.timeout_seconds,
            )
            assert query.status_code == 200, query.text
            data = query.json()
            assert data.get("count", 0) >= 1
            results = data.get("results") or []
            # Best-effort: ensure the metadata from ingest is present.
            assert any(str(r.get("metadata", {}).get("file_id")) == str(file_id) for r in results)
        finally:
            api_client.delete(
                f"{api_client.base_url}/files/{file_id}",
                timeout=api_client.timeout_seconds,
            )
    finally:
        api_client.delete(
            f"{api_client.base_url}/vector-stores/{store_id}",
            timeout=api_client.timeout_seconds,
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.vdb, pytest.mark.slow, pytest.mark.heavy]

