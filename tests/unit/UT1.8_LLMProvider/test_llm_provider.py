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
Unit Test: UT1.8 - LLM Provider Initialization and Generation

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for LLM provider initialization and generation

Related Requirements: FR1.1
Related Tasks: T008
Related Architecture: IP1.1.1
Related Tests: UT1.8

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.llm.manager import LLMManager
from src.core.llm.providers import OllamaProvider
from src.config.loader import load_config
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_manager_initialization():
    """Test LLM manager can be initialized."""
    load_config.cache_clear()
    manager = LLMManager()

    initialized = await manager.initialize()

    # May fail if LLM not available, but should not raise exception
    assert isinstance(initialized, bool)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_manager_health_check():
    """Test LLM manager health check."""
    load_config.cache_clear()
    manager = LLMManager()

    await manager.initialize()
    healthy = await manager.health_check()

    # Health check should return boolean
    assert isinstance(healthy, bool)

    await manager.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_generate_basic():
    """Test basic LLM generation."""
    import httpx

    load_config.cache_clear()
    manager = LLMManager()

    try:
        initialized = await manager.initialize()
        if not initialized:
            pytest.fail("LLM not available for test_llm_generate_basic")

        messages = [{"role": "user", "content": "Say hello"}]

        try:
            response = await manager.generate(messages, max_tokens=20)

            assert response is not None
            assert "content" in response
            assert isinstance(response["content"], str)
        except (
            httpx.ConnectError,
            httpx.RequestError,
            httpx.HTTPStatusError,
            ConnectionError,
        ) as e:
            pytest.fail(f"LLM service not available: {e}")
        except Exception as e:
            # Other exceptions - check if it's a connection issue
            if "connection" in str(e).lower() or "connect" in str(e).lower():
                pytest.fail(f"LLM service not available: {e}")
            raise

    finally:
        await manager.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_generate_with_system_prompt():
    """Test LLM generation with system prompt."""
    import httpx

    load_config.cache_clear()
    manager = LLMManager()

    try:
        initialized = await manager.initialize()
        if not initialized:
            pytest.fail("LLM not available for test_llm_generate_with_system_prompt")

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2?"},
        ]

        try:
            response = await manager.generate(messages, max_tokens=20)

            assert response is not None
            assert "content" in response
        except (
            httpx.ConnectError,
            httpx.RequestError,
            httpx.HTTPStatusError,
            ConnectionError,
        ) as e:
            pytest.fail(f"LLM service not available: {e}")
        except Exception as e:
            # Other exceptions - check if it's a connection issue
            if "connection" in str(e).lower() or "connect" in str(e).lower():
                pytest.fail(f"LLM service not available: {e}")
            raise

    finally:
        await manager.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_ollama_provider_direct():
    """Test Ollama provider directly."""
    load_config.cache_clear()
    from src.config.loader import get_config

    base_url = get_config("llm.base_url")
    model = get_config("llm.model")
    timeout = get_config("llm.timeout")
    if not base_url or not model or timeout is None:
        pytest.fail("Missing llm.base_url/llm.model/llm.timeout in config")
    provider = OllamaProvider(base_url=str(base_url), model=str(model), timeout=int(timeout))

    try:
        healthy = await provider.health_check()
        if not healthy:
            pytest.fail("Ollama not available for test_ollama_provider_direct")

        messages = [{"role": "user", "content": "Hi"}]
        response = await provider.generate(messages, max_tokens=10)

        assert response is not None
        assert "content" in response

    finally:
        await provider.close()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.llm, pytest.mark.fast]

