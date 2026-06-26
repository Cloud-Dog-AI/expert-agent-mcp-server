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
Integration Tests for External Services

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests connectivity and functionality of external services (LLM, Qdrant, Redis)

Related Requirements: FR1.1, FR1.3, NF1.6
Related Tasks: T007, T014, T064
Related Architecture: CC3.1.2, CC4.1.1
Related Tests: IT2.4, IT2.6

Recent Changes:
- Initial implementation for external service connectivity tests
"""

import asyncio
import uuid

import pytest

from src.common.llm_client import get_llm_client
from src.config.loader import get_config, load_config
from src.core.vector.providers import QdrantProvider
from src.utils.logger import get_logger

logger = get_logger(__name__)


pytestmark = pytest.mark.integration


async def _init_qdrant_with_retry(provider: QdrantProvider, config: dict, attempts: int = 5) -> bool:
    """Retry Qdrant initialization to handle transient backend readiness blips."""
    for attempt in range(attempts):
        if await provider.initialize(config):
            return True
        if attempt < (attempts - 1):
            await asyncio.sleep(0.5)
    return False


def _require_llm_config() -> float:
    provider = get_config("llm.provider")
    model = get_config("llm.model")
    base_url = get_config("llm.base_url")
    timeout = get_config("test.llm_http_timeout_seconds") or get_config("llm.timeout")
    if not provider or not model or not base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    if timeout is None:
        pytest.fail("llm.timeout or test.llm_http_timeout_seconds not configured")
    return float(timeout)


def _require_qdrant_config() -> dict:
    qdrant_config = get_config("vector_stores_config.qdrant._DEFAULT_")
    if not isinstance(qdrant_config, dict):
        pytest.fail("Qdrant config not available (vector_stores_config.qdrant._DEFAULT_)")
    qdrant_host = qdrant_config.get("host")
    qdrant_port = qdrant_config.get("port")
    qdrant_api_key = qdrant_config.get("api_key")
    collection_name = qdrant_config.get("collection_name")
    if not qdrant_host or qdrant_port is None or qdrant_api_key is None or not collection_name:
        pytest.fail("Qdrant host/port/api_key/collection_name not configured")
    return qdrant_config


def _build_qdrant_config(qdrant_config: dict, collection_name: str) -> dict:
    config = {
        "host": qdrant_config.get("host"),
        "port": qdrant_config.get("port"),
        "api_key": qdrant_config.get("api_key"),
        "collection_name": collection_name,
    }
    if qdrant_config.get("ssl") is not None:
        config["ssl"] = qdrant_config.get("ssl")
    if qdrant_config.get("timeout") is not None:
        config["timeout"] = qdrant_config.get("timeout")
    return config
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_connectivity(test_env_file):
    """Test LLM connectivity using common LLM client."""
    load_config.cache_clear()
    timeout = _require_llm_config()

    async with get_llm_client() as client:
        ok = await asyncio.wait_for(client.health_check(), timeout=min(5.0, timeout))
        if not ok:
            pytest.fail("LLM health check failed - service not reachable")
        logger.info("✓ LLM health check succeeded")
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_health_check(test_env_file):
    """Test LLM health check using common LLM client."""
    load_config.cache_clear()
    _require_llm_config()
    async with get_llm_client() as client:
        health = await asyncio.wait_for(client.health_check(), timeout=5.0)
        assert health is True, "LLM health check returned False"
        logger.info("✓ LLM health check returned healthy")
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_generate(test_env_file):
    """Test LLM text generation."""
    load_config.cache_clear()
    timeout = _require_llm_config()
    messages = [{"role": "user", "content": "Say 'Hello, World!' and nothing else."}]
    async with get_llm_client() as client:
        result = await asyncio.wait_for(
            client.chat(messages=messages, temperature=0.1, max_tokens=50),
            timeout=timeout,
        )

        assert result is not None, "LLM generation returned None"
        assert "content" in result, "LLM result missing 'content' field"
        content = result.get("content", "")
        assert isinstance(content, str), "LLM result content is not a string"
        assert "model" in result, "LLM result missing 'model' field"
        logger.info("✓ LLM generation succeeded")
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_qdrant_connectivity(test_env_file):
    """Test Qdrant connectivity."""
    load_config.cache_clear()
    qdrant_config = _require_qdrant_config()
    provider = QdrantProvider()
    try:
        config = _build_qdrant_config(qdrant_config, qdrant_config["collection_name"])
        initialized = await _init_qdrant_with_retry(provider, config)
        assert initialized, "Qdrant provider initialization failed"
        health = await provider.health_check()
        assert health, "Qdrant health check failed"
        logger.info("✓ Qdrant service is reachable")
    finally:
        await provider.embedding_manager.close()
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_qdrant_collection_crud(test_env_file):
    """Test CRUD operations on Qdrant collection."""
    load_config.cache_clear()
    qdrant_config = _require_qdrant_config()
    collection_name = qdrant_config["collection_name"]
    unique = uuid.uuid4().hex[:8]
    provider = QdrantProvider()
    try:
        config = _build_qdrant_config(qdrant_config, collection_name)
        initialized = await _init_qdrant_with_retry(provider, config)
        if not initialized:
            pytest.fail("Qdrant provider initialization failed")

        documents = [
            f"Integration CRUD alpha {unique}",
            f"Integration CRUD beta {unique}",
        ]
        metadatas = [{"tag": "alpha"}, {"tag": "beta"}]
        ids = await provider.add_documents(collection_name, documents, metadatas=metadatas)
        assert len(ids) == 2

        results = await provider.search(collection_name, f"alpha {unique}", n_results=2)
        assert results, "Search results should not be empty"

        updated = await provider.update_document(
            collection_name,
            ids[0],
            f"Integration CRUD updated {unique}",
            metadata={"tag": "updated"},
        )
        assert updated is True

        updated_results = await provider.search(collection_name, f"updated {unique}", n_results=2)
        assert updated_results, "Updated document should be searchable"

        deleted = await provider.delete_document(collection_name, ids[0])
        assert deleted is True
    finally:
        # Best-effort cleanup of test documents without removing the collection.
        if "ids" in locals():
            for doc_id in ids:
                try:
                    await provider.delete_document(collection_name, doc_id)
                except Exception:
                    pass
        await provider.embedding_manager.close()
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_redis_connectivity(test_env_file):
    """Test Redis/Valkey connectivity."""
    load_config.cache_clear()

    redis_host = get_config("redis.host")
    redis_port = get_config("redis.port")
    redis_db = get_config("redis.db")
    redis_username = get_config("redis.username")
    redis_password = get_config("redis.password")
    socket_timeout = get_config("redis.socket_connect_timeout_seconds")
    if (
        redis_host is None
        or redis_port is None
        or redis_db is None
        or redis_username is None
        or redis_password is None
        or socket_timeout is None
    ):
        pytest.fail("Redis config not fully configured")

    logger.info(f"Testing Redis/Valkey connectivity to {redis_host}:{redis_port} (db: {redis_db})")

    try:
        import redis.asyncio as redis

        # Build connection parameters
        conn_params = {
            "host": redis_host,
            "port": redis_port,
            "db": redis_db,
            "decode_responses": True,
            "socket_connect_timeout": float(socket_timeout),
        }

        if redis_username:
            conn_params["username"] = redis_username
        if redis_password:
            conn_params["password"] = redis_password

        # Test connection
        r = redis.Redis(**conn_params)
        await r.ping()
        logger.info(f"✓ Redis/Valkey service is reachable at {redis_host}:{redis_port}")

        # Test basic operations
        test_key = "expert_agent_test_key"
        test_value = "test_value_123"
        await r.set(test_key, test_value, ex=10)  # Expire in 10 seconds
        retrieved = await r.get(test_key)
        assert retrieved == test_value, (
            f"Redis get/set test failed: expected {test_value}, got {retrieved}"
        )
        await r.delete(test_key)
        logger.info("✓ Redis/Valkey basic operations working")

        await r.aclose()
    except ImportError:
        pytest.fail("redis library not installed - install with: pip install redis")
    except redis.ConnectionError as e:
        pytest.fail(f"Redis/Valkey service not reachable: {e}")
    except redis.AuthenticationError as e:
        pytest.fail(f"Redis/Valkey authentication failed: {e}")
    except Exception as e:
        pytest.fail(f"Redis/Valkey connectivity test failed: {e}")
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_redis_token_usage(test_env_file):
    """Test Redis token is configured and Redis connectivity works."""
    load_config.cache_clear()

    redis_token = get_config("redis.token")
    redis_host = get_config("redis.host")
    redis_port = get_config("redis.port")
    redis_db = get_config("redis.db")
    redis_username = get_config("redis.username")
    redis_password = get_config("redis.password")
    socket_timeout = get_config("redis.socket_connect_timeout_seconds")
    if redis_token is None or not str(redis_token).strip():
        pytest.fail("redis.token not configured (required in this environment)")
    if (
        redis_host is None
        or redis_port is None
        or redis_db is None
        or redis_username is None
        or redis_password is None
        or socket_timeout is None
    ):
        pytest.fail("Redis config not fully configured")

    logger.info("Testing Redis token usage")

    try:
        import redis.asyncio as redis

        # Test with username/password (token is for application use, not direct auth)
        # The token is stored for application-level authentication, not Redis AUTH
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            username=redis_username if redis_username else None,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=float(socket_timeout),
        )

        await r.ping()
        logger.info("✓ Redis connection successful (token available for application use)")

        # Verify token is configured (even though we use password for connection)
        assert redis_token, "Redis token should be configured"
        logger.info("✓ Redis token configured")

        await r.aclose()
    except ImportError:
        pytest.fail("redis library not installed")
    except Exception as e:
        pytest.fail(f"Redis token test failed: {e}")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.llm, pytest.mark.vdb, pytest.mark.heavy]

