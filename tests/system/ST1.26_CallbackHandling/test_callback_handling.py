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
System Test: ST1.26 - Callback Handling for Async Operations

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for callback handling

Related Requirements: FR1.7
Related Tasks: T037
Related Architecture: AI1.1
Related Tests: ST1.26

Recent Changes:
- Initial implementation
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.core.job.callbacks import CallbackManager
from src.core.job.manager import JobManager
from src.config.loader import get_config
from src.core.auth.user_manager import UserManager


@pytest.fixture
def callback_manager():
    """Create callback manager."""
    return CallbackManager()


@pytest.fixture
def job_manager(db_session):
    """Create job manager."""
    return JobManager(db_session)


@pytest.fixture
def test_user(db_session):
    """Create a test user for job ownership."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    manager = UserManager(db_session)
    return manager.create_user(
        username=f"{base_username}_st1_26",
        email=f"st1_26@{domain}",
        password=password,
    )
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_system_registers_callback_for_job(callback_manager, job_manager, test_user, db_session):
    """Test that system registers callbacks for jobs."""
    callback_base_url = get_config("test.callback_base_url")
    if not callback_base_url:
        pytest.fail("Missing test.callback_base_url in config")
    # Create a job
    job = job_manager.create_job(
        job_type="test_job", user_id=test_user.id, metadata={"test": "data"}
    )

    # Register callback
    result = callback_manager.register_callback(
        job_id=job.id, callback_url=f"{callback_base_url}/callback", callback_method="POST"
    )

    assert result is True
    assert job.id in callback_manager.registered_callbacks
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_system_triggers_callback_on_job_completion(
    callback_manager, job_manager, test_user, db_session
):
    """Test that system triggers callback when job completes."""
    callback_base_url = get_config("test.callback_base_url")
    if not callback_base_url:
        pytest.fail("Missing test.callback_base_url in config")
    # Create job
    job = job_manager.create_job(job_type="test_job", user_id=test_user.id)

    # Register callback
    callback_manager.register_callback(job_id=job.id, callback_url=f"{callback_base_url}/callback")

    # Mock HTTP client
    with patch("src.core.job.callbacks.get_shared_async_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        # Trigger callback
        import asyncio

        result = asyncio.run(
            callback_manager.trigger_callback(job.id, "completed", {"result": "success"})
        )

        assert result is True
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_system_handles_callback_failure_gracefully(
    callback_manager, job_manager, test_user, db_session
):
    """Test that system handles callback failures gracefully."""
    callback_base_url = get_config("test.callback_base_url")
    if not callback_base_url:
        pytest.fail("Missing test.callback_base_url in config")
    # Create job
    job = job_manager.create_job(job_type="test_job", user_id=test_user.id)

    # Register callback
    callback_manager.register_callback(job_id=job.id, callback_url=f"{callback_base_url}/callback")

    # Mock HTTP failure
    with patch("src.core.job.callbacks.get_shared_async_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection error"))
        mock_get_client.return_value = mock_client

        # Trigger callback - should handle failure gracefully
        import asyncio

        result = asyncio.run(callback_manager.trigger_callback(job.id, "completed"))

        # Should return False but not raise exception
        assert result is False
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_system_callback_with_custom_headers(callback_manager, job_manager, test_user, db_session):
    """Test that system supports custom callback headers."""
    callback_base_url = get_config("test.callback_base_url")
    if not callback_base_url:
        pytest.fail("Missing test.callback_base_url in config")
    job = job_manager.create_job(job_type="test_job", user_id=test_user.id)

    headers = {"Authorization": "Bearer token123", "X-Custom": "value"}
    callback_manager.register_callback(
        job_id=job.id, callback_url=f"{callback_base_url}/callback", callback_headers=headers
    )

    assert callback_manager.registered_callbacks[job.id]["headers"] == headers
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_system_callback_with_different_methods(
    callback_manager, job_manager, test_user, db_session
):
    """Test that system supports different HTTP methods."""
    callback_base_url = get_config("test.callback_base_url")
    if not callback_base_url:
        pytest.fail("Missing test.callback_base_url in config")
    job = job_manager.create_job(job_type="test_job", user_id=test_user.id)

    # Test POST
    callback_manager.register_callback(
        job_id=job.id, callback_url=f"{callback_base_url}/callback", callback_method="POST"
    )
    assert callback_manager.registered_callbacks[job.id]["method"] == "POST"

    # Test PUT
    callback_manager.unregister_callback(job.id)
    callback_manager.register_callback(
        job_id=job.id, callback_url=f"{callback_base_url}/callback", callback_method="PUT"
    )
    assert callback_manager.registered_callbacks[job.id]["method"] == "PUT"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_system_callback_payload_structure(callback_manager, job_manager, test_user, db_session):
    """Test that callback payload has correct structure."""
    callback_base_url = get_config("test.callback_base_url")
    if not callback_base_url:
        pytest.fail("Missing test.callback_base_url in config")
    job = job_manager.create_job(job_type="test_job", user_id=test_user.id)

    callback_manager.register_callback(job_id=job.id, callback_url=f"{callback_base_url}/callback")

    job_result = {"response": "test", "tokens": 100}

    with patch("src.core.job.callbacks.get_shared_async_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        import asyncio

        asyncio.run(callback_manager.trigger_callback(job.id, "completed", job_result))

        # Verify payload structure
        call_args = mock_post.call_args
        assert call_args[1]["json"]["job_id"] == job.id
        assert call_args[1]["json"]["status"] == "completed"
        assert call_args[1]["json"]["result"] == job_result
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_system_multiple_callbacks_for_different_jobs(
    callback_manager, job_manager, test_user, db_session
):
    """Test that system handles multiple callbacks for different jobs."""
    callback_base_url = get_config("test.callback_base_url")
    if not callback_base_url:
        pytest.fail("Missing test.callback_base_url in config")
    # Create multiple jobs
    jobs = []
    for i in range(3):
        job = job_manager.create_job(job_type=f"test_job_{i}", user_id=test_user.id)
        callback_manager.register_callback(
            job_id=job.id, callback_url=f"{callback_base_url}/callback/{i}"
        )
        jobs.append(job)

    # All should be registered
    assert len(callback_manager.registered_callbacks) == 3
    assert all(job.id in callback_manager.registered_callbacks for job in jobs)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]
