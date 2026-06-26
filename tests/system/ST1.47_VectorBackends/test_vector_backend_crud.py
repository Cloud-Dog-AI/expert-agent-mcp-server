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
System Test: ST1.30 - Vector Backend CRUD (via real API server)

Rules alignment:
- Uses requests to hit real running API server.
- No mocks/stubs/TestClient.
- Uses configuration via src.config.loader.get_config (loaded from --env).
"""

import uuid
import time
import pytest
import requests

from src.config.loader import get_config


@pytest.fixture
def api_client(test_env_file):
    host = get_config("api_server.host")
    port = get_config("api_server.port")
    if not host or port is None:
        pytest.fail("Missing api_server.host/api_server.port in config (--env)")

    base_url = f"http://{host}:{int(port)}"
    s = requests.Session()
    s.base_url = base_url
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    s.timeout_seconds = float(timeout)
    api_key = (
        get_config("api_server.api_key")
        or get_config("test.api_key")
        or get_config("expert.test.api_key")
    )
    if not api_key:
        pytest.fail("Missing api_server.api_key/test.api_key in config (--env)")
    s.headers.update({"X-API-Key": str(api_key)})

    # Ensure server is reachable
    for _ in range(10):
        try:
            r = s.get(f"{base_url}/health", timeout=s.timeout_seconds)
            if r.status_code == 200:
                return s
        except Exception:
            pass
    pytest.fail(
        f"API server not reachable at {base_url}. Start it with: ./server_control.sh --env <env-file> start"
    )


def _pick_config(store_type: str, prefer_profile: str = "_DEFAULT_"):
    """Return store config dict from config system."""
    # Prefer canonical vector_stores_config; fall back to vector_stores defaults.
    for base in ("vector_stores_config", "vector_stores"):
        cfg = get_config(f"{base}.{store_type}.{prefer_profile}")
        if isinstance(cfg, dict) and cfg:
            return cfg
    return {}


@pytest.mark.parametrize(
    "store_type, profile",
    [
        ("chroma", "_DEFAULT_"),  # local persistent
        ("chroma", "_REMOTE_"),  # remote http
        ("qdrant", "_DEFAULT_"),
        ("weaviate", "_DEFAULT_"),
        ("opensearch", "_TEST_"),
        ("pgvector", "_TEST_"),
    ],
)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")
def test_vector_backend_crud_via_api(api_client, store_type: str, profile: str):
    cfg = _pick_config(store_type, profile)
    if not cfg:
        pytest.fail(f"Missing config for {store_type}.{profile} (check your --env)")

    # Build isolated create payload config per provider expectations.
    # Always use unique names to avoid backend schema/index dimension collisions.
    unique = uuid.uuid4().hex[:8]
    profile_slug = profile.lower().strip("_")
    create_cfg = dict(cfg)
    if store_type == "weaviate":
        # Weaviate class/collection names are safest in alnum/PascalCase form.
        collection = f"StVector{store_type.capitalize()}{profile_slug.capitalize()}{unique}"
    elif store_type == "opensearch":
        base_collection = cfg.get("collection_name")
        if not base_collection:
            pytest.fail("OpenSearch requires opensearch._TEST_.collection_name")
        # This environment is at the shard/index limit, so reuse the shared
        # configured index rather than forcing per-test index creation.
        collection = str(base_collection)
    else:
        collection = f"expert_agent_st_{store_type}_{profile_slug}_{unique}"

    create_cfg["collection_name"] = collection
    if store_type == "opensearch":
        # OpenSearch provider supports index_name alias; keep both explicit.
        create_cfg["index_name"] = collection

    # Basic required fields per backend
    if store_type == "chroma":
        # Local chroma uses path; remote chroma uses host/port
        if profile == "_DEFAULT_":
            if not create_cfg.get("path"):
                pytest.fail("Chroma local requires chroma._DEFAULT_.path")
        else:
            if not create_cfg.get("host") or create_cfg.get("port") is None:
                pytest.fail("Chroma remote requires chroma._REMOTE_.host/port")
            # Ensure ssl is bool if provided
            if "ssl" in create_cfg:
                create_cfg["ssl"] = bool(create_cfg["ssl"])
    elif store_type == "qdrant":
        if not create_cfg.get("host") or create_cfg.get("port") is None:
            pytest.fail("Qdrant requires qdrant._DEFAULT_.host/port")
        # api_key may be empty string if not required, but must exist as key for consistency
        if "api_key" not in create_cfg:
            pytest.fail(
                "Qdrant requires qdrant._DEFAULT_.api_key (use empty string if not required)"
            )
    elif store_type == "weaviate":
        if not create_cfg.get("url") and not create_cfg.get("server_url"):
            pytest.fail("Weaviate requires weaviate._DEFAULT_.url or weaviate._DEFAULT_.server_url")
        if not create_cfg.get("server_url") and create_cfg.get("url"):
            create_cfg["server_url"] = create_cfg.get("url")
        if "api_key" not in create_cfg:
            pytest.fail(
                "Weaviate requires weaviate._DEFAULT_.api_key (use empty string if not required)"
            )
    elif store_type == "opensearch":
        if not create_cfg.get("host") or create_cfg.get("port") is None:
            pytest.fail("OpenSearch requires opensearch._TEST_.host/port")
        if not create_cfg.get("username") or "password" not in create_cfg:
            pytest.fail("OpenSearch requires opensearch._TEST_.username/password")
    elif store_type == "pgvector":
        if not create_cfg.get("database_uri") and (
            not create_cfg.get("host") or create_cfg.get("port") is None
        ):
            pytest.fail(
                "PGVector requires pgvector._TEST_.database_uri or host/port/database/username/password"
            )

    # 1) Create vector store
    store_name = f"st_vector_{store_type}_{profile.lower()}_{unique}"
    r_create = api_client.post(
        f"{api_client.base_url}/vector-stores",
        json={"name": store_name, "store_type": store_type, "config": create_cfg, "enabled": True},
        timeout=api_client.timeout_seconds,
    )
    if r_create.status_code != 200:
        pytest.fail(f"{store_type} create failed: {r_create.status_code} {r_create.text}")
    store = r_create.json()
    store_id = store["id"]

    doc_id = str(uuid.uuid4())
    try:
        # 2) Add document
        r_add = api_client.post(
            f"{api_client.base_url}/vector-stores/{store_id}/documents",
            json={
                "collection": collection,
                "document": f"System test document {unique} for {store_type}",
                "metadata": {"st": True, "store_type": store_type, "unique": unique},
                "id": doc_id,
            },
            timeout=api_client.timeout_seconds,
        )
        if r_add.status_code != 200:
            pytest.fail(f"{store_type} add failed: {r_add.status_code} {r_add.text}")

        # 3) Query
        # Some providers (notably PGVector) can be briefly eventually-consistent
        # right after insert; allow a short retry window before failing.
        data = {}
        max_attempts = 6
        sleep_seconds = 0.5
        if store_type == "pgvector":
            # PGVector can show transient empty-search behavior immediately after insert
            # under load or cold connections. Extend retry window to reduce flakes,
            # but still hard-fail if it never returns the inserted document.
            max_attempts = 60  # 30s total
        for attempt in range(max_attempts):
            r_q = api_client.post(
                f"{api_client.base_url}/vector-stores/{store_id}/query",
                json={"collection": collection, "query": "System test document", "n_results": 5},
                timeout=api_client.timeout_seconds,
            )
            if r_q.status_code != 200:
                pytest.fail(f"{store_type} query failed: {r_q.status_code} {r_q.text}")
            data = r_q.json()
            if isinstance(data.get("results"), list) and data.get("count", 0) >= 1:
                break
            if attempt < (max_attempts - 1):
                time.sleep(sleep_seconds)
        if not isinstance(data.get("results"), list):
            pytest.fail(
                f"{store_type} query response missing results list. store_id={store_id} collection={collection}"
            )
        if data.get("count", 0) < 1:
            pytest.fail(
                f"{store_type} query returned no results after {max_attempts} attempts. store_id={store_id} collection={collection}"
            )

        # 4) Update
        r_upd = api_client.put(
            f"{api_client.base_url}/vector-stores/{store_id}/documents/{doc_id}",
            params={"collection": collection},
            json={
                "document": f"Updated system test document {unique} for {store_type}",
                "metadata": {"updated": True},
            },
            timeout=api_client.timeout_seconds,
        )
        assert r_upd.status_code == 200, (
            f"{store_type} update failed: {r_upd.status_code} {r_upd.text}"
        )

        # 5) Delete
        r_del = api_client.delete(
            f"{api_client.base_url}/vector-stores/{store_id}/documents/{doc_id}",
            params={"collection": collection},
            timeout=api_client.timeout_seconds,
        )
        assert r_del.status_code == 200, (
            f"{store_type} delete failed: {r_del.status_code} {r_del.text}"
        )
        assert r_del.json().get("success") is True
    finally:
        # Always delete store config
        api_client.delete(
            f"{api_client.base_url}/vector-stores/{store_id}",
            timeout=api_client.timeout_seconds,
        )
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_redis_connectivity_ping():
    """
    Redis is an external dependency; verify connectivity directly using configured values.
    """
    redis_host = get_config("redis.host")
    redis_port = get_config("redis.port")
    redis_db = get_config("redis.db")
    redis_username = get_config("redis.username")
    redis_password = get_config("redis.password")
    socket_connect_timeout = get_config("redis.socket_connect_timeout_seconds")

    if redis_host is None or redis_port is None or redis_db is None:
        pytest.fail("Redis not configured (redis.host/redis.port/redis.db)")
    if redis_username is None or redis_password is None:
        pytest.fail("Redis credentials not configured (redis.username/redis.password)")
    if socket_connect_timeout is None:
        pytest.fail("Redis socket timeout not configured (redis.socket_connect_timeout_seconds)")

    import redis

    kwargs = {
        "host": redis_host,
        "port": int(redis_port),
        "db": int(redis_db),
        "socket_connect_timeout": float(socket_connect_timeout),
        "decode_responses": True,
    }
    if redis_username:
        kwargs["username"] = redis_username
    if redis_password:
        kwargs["password"] = redis_password

    client = redis.Redis(**kwargs)
    assert client.ping() is True

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.vdb, pytest.mark.db, pytest.mark.slow, pytest.mark.heavy]
