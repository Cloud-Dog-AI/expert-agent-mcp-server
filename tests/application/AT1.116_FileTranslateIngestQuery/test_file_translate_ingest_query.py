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
Application Test: AT1.116 - File Translate -> Download -> Upload -> Ingest -> Query (Real LLM)

License: Apache 2.0
Ownership: Cloud Dog
Copyright:
  (C) Cloud-Dog, Viewdeck Engineering Ltd.

Description:
Validates an end-to-end workflow against a real running API server using the configured LLM provider/model:
1) Create an expert configuration using llm.* from --env
2) Create a vector store configuration using vector.store.type and vector_stores_config profiles (no embedded secrets)
3) Upload a text file via /files/upload_base64
4) Translate it via /files/{id}/translate (LLM call) into Chinese
5) Download translated file and validate it:
   - not empty
   - contains a stable token that must be preserved
6) Upload translated file and ingest to vector store
7) Query vector store for the stable token and confirm results

Rules alignment:
- No mocks/stubs/TestClient.
- Uses real configured LLM and vector backend. If configured services fail, the test fails.
"""

import base64
import time
import uuid
from typing import Any, Dict, Tuple

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.application


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
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_translate_upload_ingest_query_round_trip(api_client):
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")

    store_type = get_config("vector.store.type")
    if not store_type:
        pytest.fail("vector.store.type not configured")
    profile_name, persisted_cfg = _pick_vector_profile(str(store_type))

    unique = uuid.uuid4().hex[:8]
    token = f"AT116_TOKEN_{unique}"
    source_text = (
        "Translate the following text to Chinese.\n"
        "Preserve this token exactly as-is: " + token + "\n"
        "Sentence: This is a simple test document.\n"
    )

    expert = api_client.post(
        f"{api_client.base_url}/experts",
        json={
            "name": f"at116_expert_{unique}",
            "title": f"AT1.116 Expert {unique}",
            "description": "AT1.116 file translate workflow validation",
            "llm_provider": str(llm_provider),
            "llm_model": str(llm_model),
            "llm_base_url": str(llm_base_url),
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert expert.status_code == 200, expert.text
    expert_id = int(expert.json()["id"])

    vector_store_name = f"at116_{profile_name}_{unique}"
    store = api_client.post(
        f"{api_client.base_url}/vector-stores",
        json={
            "name": vector_store_name,
            "store_type": str(store_type),
            "config": persisted_cfg,
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert store.status_code == 200, store.text
    store_id = int(store.json()["id"])

    try:
        health = api_client.get(
            f"{api_client.base_url}/vector-stores/{store_id}/health",
            timeout=api_client.timeout_seconds,
        )
        assert health.status_code == 200, health.text

        uploaded = api_client.post(
            f"{api_client.base_url}/files/upload_base64",
            json={
                "filename": f"at116_{unique}.txt",
                "content_base64": base64.b64encode(source_text.encode("utf-8")).decode("ascii"),
                "metadata": {"at": True, "token": token},
            },
            timeout=api_client.timeout_seconds,
        )
        assert uploaded.status_code == 200, uploaded.text
        source_file_id = int(uploaded.json()["file"]["id"])

        try:
            translated = api_client.post(
                f"{api_client.base_url}/files/{source_file_id}/translate",
                json={
                    "expert_config_id": expert_id,
                    "target_language": "Chinese",
                    "translated_filename": f"at116_{unique}.zh.txt",
                },
                timeout=api_client.timeout_seconds,
            )
            assert translated.status_code == 200, translated.text
            translated_file_id = int(translated.json()["translated_file"]["id"])

            try:
                downloaded = api_client.get(
                    f"{api_client.base_url}/files/{translated_file_id}/download",
                    timeout=api_client.timeout_seconds,
                )
                assert downloaded.status_code == 200, downloaded.text
                translated_text = downloaded.content.decode("utf-8").strip()
                assert translated_text
                assert token in translated_text

                # Upload the translated text as a new file record, then ingest.
                reupload = api_client.post(
                    f"{api_client.base_url}/files/upload_base64",
                    json={
                        "filename": f"at116_{unique}.zh.reupload.txt",
                        "content_base64": base64.b64encode(downloaded.content).decode("ascii"),
                        "metadata": {"at": True, "token": token, "translated": True},
                    },
                    timeout=api_client.timeout_seconds,
                )
                assert reupload.status_code == 200, reupload.text
                reupload_file_id = int(reupload.json()["file"]["id"])

                try:
                    ingested = api_client.post(
                        f"{api_client.base_url}/files/{reupload_file_id}/ingest_to_vector_store",
                        json={
                            "vector_store_id": store_id,
                            "collection": persisted_cfg.get("collection_name")
                            or persisted_cfg.get("index_name"),
                            "metadata": {"token": token, "language": "zh"},
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
                finally:
                    api_client.delete(
                        f"{api_client.base_url}/files/{reupload_file_id}",
                        timeout=api_client.timeout_seconds,
                    )
            finally:
                api_client.delete(
                    f"{api_client.base_url}/files/{translated_file_id}",
                    timeout=api_client.timeout_seconds,
                )
        finally:
            api_client.delete(
                f"{api_client.base_url}/files/{source_file_id}",
                timeout=api_client.timeout_seconds,
            )
    finally:
        api_client.delete(
            f"{api_client.base_url}/vector-stores/{store_id}",
            timeout=api_client.timeout_seconds,
        )
        api_client.delete(
            f"{api_client.base_url}/experts/{expert_id}",
            timeout=api_client.timeout_seconds,
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.vdb, pytest.mark.heavy]
