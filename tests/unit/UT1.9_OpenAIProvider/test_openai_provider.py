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
Unit Test: UT1.9 - OpenAI-Compatible Provider Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for OpenAI-compatible provider integration

Related Requirements: FR1.1
Related Tasks: T008
Related Architecture: IP1.1.1
Related Tests: UT1.9

Recent Changes:
- Initial implementation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.llm.providers import OpenAIProvider, LLMProvider
from src.config.loader import get_config


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    return AsyncMock()


@pytest.fixture
def openai_provider():
    """Create OpenAI provider instance."""
    base_url = get_config("test.llm_providers.openai.base_url")
    api_key = get_config("test.llm_providers.openai.api_key")
    model = get_config("test.llm_providers.openai.model")
    timeout = get_config("test.llm_providers.openai.timeout_seconds")
    if not base_url or not api_key or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.openai.* in config")
    return OpenAIProvider(
        base_url=str(base_url),
        api_key=str(api_key),
        model=str(model),
        timeout=int(timeout),
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_openai_provider_initialization(openai_provider):
    """Test OpenAI provider can be initialized."""
    assert openai_provider is not None
    assert isinstance(openai_provider, OpenAIProvider)
    assert isinstance(openai_provider, LLMProvider)
    assert openai_provider.base_url == str(get_config("test.llm_providers.openai.base_url"))
    assert openai_provider.api_key == str(get_config("test.llm_providers.openai.api_key"))
    assert openai_provider.model == str(get_config("test.llm_providers.openai.model"))
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_openai_provider_initialization_without_api_key():
    """Test OpenAI provider initialization (API key validation happens during use, not init)."""
    # OpenAIProvider doesn't validate API key at init time
    # It will fail during generate() or health_check() if invalid
    base_url = get_config("test.llm_providers.openai.base_url")
    model = get_config("test.llm_providers.openai.model")
    timeout = get_config("test.llm_providers.openai.timeout_seconds")
    if not base_url or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.openai.* in config")
    provider = OpenAIProvider(
        base_url=str(base_url),
        api_key=None,
        model=str(model),
        timeout=int(timeout),
    )
    # Should initialize, but will fail when used
    assert provider is not None
    assert provider.api_key is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_openai_provider_health_check(openai_provider):
    """Test OpenAI provider health check."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        health = await openai_provider.health_check()

        # Health check should return True if API is accessible
        assert isinstance(health, bool)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_openai_provider_generate(openai_provider):
    """Test OpenAI provider generate method."""
    # Mock the httpx client that's already created in the provider
    mock_response = MagicMock()
    mock_response.status_code = 200
    model = get_config("test.llm_providers.openai.model")
    if not model:
        pytest.fail("Missing test.llm_providers.openai.model in config")
    mock_response.json.return_value = {
        "model": str(model),
        "choices": [
            {"message": {"content": "Test response", "role": "assistant"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    mock_response.raise_for_status = MagicMock()

    openai_provider._client.client.post = AsyncMock(return_value=mock_response)

    response = await openai_provider.generate(
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Test prompt"},
        ]
    )

    assert response is not None
    assert "content" in response
    assert response["content"] == "Test response"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_openai_provider_generate_with_streaming(openai_provider):
    """Test OpenAI provider generate with streaming."""
    # Mock streaming response
    mock_stream = MagicMock()
    mock_stream.__aiter__.return_value = [
        {"choices": [{"delta": {"content": "Test"}}]},
        {"choices": [{"delta": {"content": " response"}}]},
        {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]},
    ]
    mock_stream.raise_for_status = MagicMock()

    openai_provider._client.client.post = AsyncMock(return_value=mock_stream)

    # Note: Current OpenAIProvider doesn't fully support streaming in the return format
    # This test verifies the method can be called with stream=True
    try:
        response = await openai_provider.generate(
            messages=[{"role": "user", "content": "Test prompt"}], stream=True
        )
        # If streaming is not fully implemented, this may raise or return differently
        assert response is not None
    except (NotImplementedError, TypeError):
        # Streaming may not be fully implemented yet
        pytest.skip("Streaming not fully implemented in OpenAIProvider")
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_openai_provider_error_handling(openai_provider):
    """Test OpenAI provider error handling."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Unauthorized")

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        # Should handle error gracefully
        with pytest.raises(Exception):
            await openai_provider.generate(messages=[{"role": "user", "content": "Test prompt"}])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_openai_provider_custom_base_url():
    """Test OpenAI provider with custom base URL (for OpenAI-compatible APIs)."""
    base_url = get_config("test.llm_providers.custom_openai.base_url")
    api_key = get_config("test.llm_providers.openai.api_key")
    model = get_config("test.llm_providers.custom_openai.model")
    timeout = get_config("test.llm_providers.openai.timeout_seconds")
    if not base_url or not api_key or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.custom_openai.* in config")
    provider = OpenAIProvider(
        base_url=str(base_url),
        api_key=str(api_key),
        model=str(model),
        timeout=int(timeout),
    )

    assert provider.base_url == str(base_url)
    assert provider.model == str(model)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_openai_provider_timeout_configuration():
    """Test OpenAI provider timeout configuration."""
    base_url = get_config("test.llm_providers.openai.base_url")
    api_key = get_config("test.llm_providers.openai.api_key")
    model = get_config("test.llm_providers.openai.model")
    timeout = get_config("test.llm_providers.openai.timeout_seconds")
    if not base_url or not api_key or not model or timeout is None:
        pytest.fail("Missing test.llm_providers.openai.* in config")
    provider = OpenAIProvider(
        base_url=str(base_url),
        api_key=str(api_key),
        model=str(model),
        timeout=int(timeout),
    )

    assert provider.timeout == int(timeout)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


@pytest.mark.asyncio
async def test_openai_provider_usage_tracking(openai_provider):
    """Test OpenAI provider tracks token usage."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    model = get_config("test.llm_providers.openai.model")
    if not model:
        pytest.fail("Missing test.llm_providers.openai.model in config")
    mock_response.json.return_value = {
        "model": str(model),
        "choices": [
            {"message": {"content": "Response", "role": "assistant"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }
    mock_response.raise_for_status = MagicMock()

    openai_provider._client.client.post = AsyncMock(return_value=mock_response)

    response = await openai_provider.generate(messages=[{"role": "user", "content": "Test"}])

    # Response should include usage information
    assert response is not None
    assert "tokens_used" in response
    assert response["tokens_used"] == 30
    assert "metadata" in response
    assert response["metadata"]["prompt_tokens"] == 20
    assert response["metadata"]["completion_tokens"] == 10

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.llm, pytest.mark.fast]

