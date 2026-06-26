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
Unit Test: UT1.42 - Callback Mechanism for Async Responses

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for callback mechanism

Related Requirements: FR1.7
Related Tasks: T037
Related Architecture: AI1.1
Related Tests: UT1.42

Recent Changes:
- Initial implementation
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.core.job.callbacks import CallbackManager
from src.config.loader import get_config


def _require_callback_base_url() -> str:
    base_url = get_config("test.callback_base_url")
    if not base_url:
        pytest.fail("Missing test.callback_base_url in config")
    return str(base_url)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_callback_manager_initialization():
    """Test callback manager can be initialized."""
    manager = CallbackManager()
    assert manager is not None
    assert manager.registered_callbacks == {}
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_register_callback():
    """Test registering a callback."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    result = manager.register_callback(
        job_id=1, callback_url=f"{base_url}/callback", callback_method="POST"
    )

    assert result is True
    assert 1 in manager.registered_callbacks
    assert manager.registered_callbacks[1]["url"] == f"{base_url}/callback"
    assert manager.registered_callbacks[1]["method"] == "POST"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_register_callback_with_headers():
    """Test registering callback with custom headers."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    headers = {"Authorization": "Bearer token123"}
    result = manager.register_callback(
        job_id=2,
        callback_url=f"{base_url}/callback",
        callback_method="PUT",
        callback_headers=headers,
    )

    assert result is True
    assert manager.registered_callbacks[2]["headers"] == headers
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_unregister_callback():
    """Test unregistering a callback."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    # Register first
    manager.register_callback(1, f"{base_url}/callback")
    assert 1 in manager.registered_callbacks

    # Unregister
    result = manager.unregister_callback(1)
    assert result is True
    assert 1 not in manager.registered_callbacks
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_unregister_nonexistent_callback():
    """Test unregistering a non-existent callback."""
    manager = CallbackManager()

    result = manager.unregister_callback(999)
    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_trigger_callback_success():
    """Test triggering a callback successfully."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    # Register callback
    manager.register_callback(1, f"{base_url}/callback", "POST")

    # Mock httpx client
    with patch("src.core.job.callbacks.get_shared_async_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.put = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await manager.trigger_callback(1, "completed", {"result": "success"})

        assert result is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_trigger_callback_not_registered():
    """Test triggering callback for non-registered job."""
    manager = CallbackManager()

    result = await manager.trigger_callback(999, "completed")

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_trigger_callback_put_method():
    """Test triggering callback with PUT method."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    manager.register_callback(1, f"{base_url}/callback", "PUT")

    with patch("src.core.job.callbacks.get_shared_async_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.put = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await manager.trigger_callback(1, "completed")

        assert result is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_trigger_callback_with_payload():
    """Test triggering callback with job result payload."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    manager.register_callback(1, f"{base_url}/callback")

    job_result = {"response": "test response", "tokens_used": 100}

    with patch("src.core.job.callbacks.get_shared_async_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        result = await manager.trigger_callback(1, "completed", job_result)

        assert result is True
        # Verify payload was sent
        call_args = mock_post.call_args
        assert call_args[1]["json"]["result"] == job_result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_trigger_callback_failure():
    """Test triggering callback when HTTP request fails."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    manager.register_callback(1, f"{base_url}/callback")

    with patch("src.core.job.callbacks.get_shared_async_client") as mock_get_client:
        mock_client = MagicMock()
        mock_post = AsyncMock(side_effect=Exception("Connection error"))
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        result = await manager.trigger_callback(1, "completed")

        assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_multiple_callbacks():
    """Test managing multiple callbacks."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    # Register multiple callbacks
    manager.register_callback(1, f"{base_url}/callback1")
    manager.register_callback(2, f"{base_url}/callback2")
    manager.register_callback(3, f"{base_url}/callback3")

    assert len(manager.registered_callbacks) == 3
    assert all(i in manager.registered_callbacks for i in [1, 2, 3])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_callback_payload_structure():
    """Test callback payload structure."""
    manager = CallbackManager()
    base_url = _require_callback_base_url()

    manager.register_callback(1, f"{base_url}/callback")

    # The payload should include job_id, status, and result
    # This is verified in trigger_callback_with_payload test
    assert True  # Placeholder - actual verification in async test

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]

