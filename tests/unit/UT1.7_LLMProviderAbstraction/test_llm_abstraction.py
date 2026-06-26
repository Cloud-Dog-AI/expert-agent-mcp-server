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
Unit Test: UT1.7 - LLM Provider Abstraction Interface

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for LLM provider abstraction interface

Related Requirements: FR1.1
Related Tasks: T007
Related Architecture: CC3.1.2
Related Tests: UT1.7

Recent Changes:
- Initial implementation
"""

import pytest
from src.config.loader import get_config
from src.core.llm.manager import LLMManager
from src.core.llm.providers import LLMProvider, OllamaProvider, OpenAIProvider, OpenRouterProvider
from src.common.llm_client import LLMClient
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_llm_provider_interface():
    """Test that LLMProvider is an abstract base class."""
    # Should not be able to instantiate directly
    with pytest.raises(TypeError):
        LLMProvider()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_ollama_provider_initialization():
    """Test Ollama provider initialization."""
    base_url = get_config("test.llm_providers.ollama.base_url")
    model = get_config("test.llm_providers.ollama.model")
    timeout = get_config("test.llm_timeout_seconds")
    if not base_url or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.ollama.* or test.llm_timeout_seconds in config")
    provider = OllamaProvider(str(base_url), str(model), int(timeout))

    assert provider.base_url == str(base_url)
    assert provider.model == str(model)
    assert provider.timeout == int(timeout)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_openai_provider_initialization():
    """Test OpenAI provider initialization."""
    base_url = get_config("test.llm_providers.openai.base_url")
    api_key = get_config("test.llm_providers.openai.api_key")
    model = get_config("test.llm_providers.openai.model")
    timeout = get_config("test.llm_timeout_seconds")
    if not base_url or not api_key or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.openai.* or test.llm_timeout_seconds in config")
    provider = OpenAIProvider(str(base_url), str(api_key), str(model), int(timeout))

    assert provider.base_url == str(base_url)
    assert provider.api_key == str(api_key)
    assert provider.model == str(model)
    assert provider.timeout == int(timeout)


    # Covers: FR1.18
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")
def test_openrouter_provider_initialization():
    """Test OpenRouter provider initialization."""
    api_key = get_config("test.llm_providers.openrouter.api_key")
    model = get_config("test.llm_providers.openrouter.model")
    timeout = get_config("test.llm_timeout_seconds")
    if not api_key or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.openrouter.* or test.llm_timeout_seconds in config")
    provider = OpenRouterProvider(str(api_key), str(model), int(timeout))

    assert provider.api_key == str(api_key)
    assert provider.model == str(model)
    assert provider.timeout == int(timeout)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_manager_provider_abstraction():
    """Test LLM manager uses provider abstraction correctly."""
    manager = LLMManager()
    base_url = get_config("test.llm_providers.ollama.base_url")
    model = get_config("test.llm_providers.ollama.model")
    if not base_url or not model:
        pytest.fail("Missing test.llm_providers.ollama.* in config")

    # Test initialization with Ollama
    await manager.initialize(provider="ollama", base_url=str(base_url), model=str(model))

    # Should have a client instance
    assert manager.client is not None
    assert isinstance(manager.client, LLMClient)
    assert manager.client.provider == "ollama"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_manager_provider_switching():
    """Test switching between different providers."""
    manager = LLMManager()
    ollama_url = get_config("test.llm_providers.ollama.base_url")
    ollama_model = get_config("test.llm_providers.ollama.model")
    openai_url = get_config("test.llm_providers.openai.base_url")
    openai_key = get_config("test.llm_providers.openai.api_key")
    openai_model = get_config("test.llm_providers.openai.model")
    if not ollama_url or not ollama_model or not openai_url or not openai_key or not openai_model:
        pytest.fail("Missing test.llm_providers.* config for ollama/openai")

    # Initialize with Ollama
    await manager.initialize(provider="ollama", base_url=str(ollama_url), model=str(ollama_model))

    provider1 = manager.client.provider

    await manager.initialize(
        provider="openai",
        base_url=str(openai_url),
        api_key=str(openai_key),
        model=str(openai_model),
    )
    provider2 = manager.client.provider
    assert provider1 != provider2
    assert provider2 == "openai"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_llm_provider_health_check_interface():
    """Test that all providers implement health_check method."""
    base_url = get_config("test.llm_providers.ollama.base_url")
    model = get_config("test.llm_providers.ollama.model")
    timeout = get_config("test.llm_timeout_seconds")
    if not base_url or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.ollama.* or test.llm_timeout_seconds in config")
    ollama = OllamaProvider(str(base_url), str(model), int(timeout))
    assert hasattr(ollama, "health_check")
    assert callable(ollama.health_check)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_provider_generate_interface():
    """Test that all providers implement generate method."""
    base_url = get_config("test.llm_providers.ollama.base_url")
    model = get_config("test.llm_providers.ollama.model")
    timeout = get_config("test.llm_timeout_seconds")
    if not base_url or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.ollama.* or test.llm_timeout_seconds in config")
    ollama = OllamaProvider(str(base_url), str(model), int(timeout))
    assert hasattr(ollama, "generate")
    assert callable(ollama.generate)

    # Should accept messages parameter
    import inspect

    sig = inspect.signature(ollama.generate)
    assert "messages" in sig.parameters
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_llm_provider_error_handling():
    """Test provider error handling for invalid configuration."""
    # Ollama provider should handle invalid URLs
    invalid_url = get_config("test.llm_invalid_base_url")
    model = get_config("test.llm_providers.ollama.model")
    timeout = get_config("test.llm_timeout_seconds")
    if not invalid_url or not model or timeout is None:
        pytest.fail("Missing test.llm_invalid_base_url or test.llm_timeout_seconds in config")
    provider = OllamaProvider(str(invalid_url), str(model), int(timeout))
    assert provider.base_url == str(invalid_url)

    # OpenAI provider initialization doesn't validate API key at init time
    # It will fail during generate() or health_check()
    base_url = get_config("test.llm_providers.openai.base_url")
    model = get_config("test.llm_providers.openai.model")
    timeout = get_config("test.llm_timeout_seconds")
    if not base_url or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.openai.* or test.llm_timeout_seconds in config")
    provider = OpenAIProvider(str(base_url), "", str(model), int(timeout))
    assert provider.api_key == ""
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_llm_manager_unsupported_provider():
    """Test LLM manager handles unsupported providers."""
    manager = LLMManager()

    # Manager catches ValueError and returns False
    result = await manager.initialize(provider="unsupported_provider")
    assert result is False
    assert manager.client is None

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.llm, pytest.mark.fast]
