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
Integration Tests for Redis Queue

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests Redis-based queue operations

Related Requirements: FR1.26, UC1.20
Related Tasks: T064
Related Architecture: CC2.1.4
Related Tests: AT1.22

Recent Changes:
- Initial implementation
"""

import asyncio

import pytest

from src.config.loader import get_config, load_config
from src.core.queue.manager import QueueManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


pytestmark = pytest.mark.integration


def _require_redis_config() -> dict:
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
    return {
        "host": redis_host,
        "port": redis_port,
        "db": redis_db,
        "username": redis_username,
        "password": redis_password,
        "socket_timeout": float(socket_timeout),
    }


def _get_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


async def _require_redis_queue_enabled(manager: QueueManager, timeout: float) -> dict:
    status = await asyncio.wait_for(manager.get_queue_status(), timeout=timeout)
    if not status.get("redis_enabled"):
        pytest.fail("Redis queue not enabled - queue manager fell back to database")
    return status
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


@pytest.mark.asyncio
async def test_redis_queue_enqueue(db_session, test_env_file):
    """Test enqueueing jobs to Redis queue."""
    load_config.cache_clear()
    _require_redis_config()
    timeout = _get_timeout()
    manager = QueueManager(db=db_session, use_redis=True)
    try:
        status_before = await _require_redis_queue_enabled(manager, timeout)
        job_id = await manager.enqueue(job_type="test_job", priority=5, metadata={"test": "data"})

        assert job_id > 0, "Job ID should be positive"
        status_after = await _require_redis_queue_enabled(manager, timeout)
        assert status_after["redis_queue_sizes"].get("test_job", 0) >= status_before[
            "redis_queue_sizes"
        ].get("test_job", 0)
        logger.info(f"✓ Job enqueued: {job_id}")
    except Exception as e:
        pytest.fail(f"Redis queue enqueue failed: {e}")
    finally:
        await manager.close()
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


@pytest.mark.asyncio
async def test_redis_queue_dequeue(db_session, test_env_file):
    """Test dequeueing jobs from Redis queue."""
    load_config.cache_clear()
    _require_redis_config()
    timeout = _get_timeout()
    manager = QueueManager(db=db_session, use_redis=True)
    try:
        await _require_redis_queue_enabled(manager, timeout)
        # Enqueue a job first
        job_id = await manager.enqueue(
            job_type="test_dequeue", priority=10, metadata={"test": "dequeue"}
        )

        # Dequeue it
        jobs = await asyncio.wait_for(
            manager.dequeue(limit=1, job_type="test_dequeue"), timeout=timeout
        )

        assert len(jobs) > 0, "Should dequeue at least one job"
        assert jobs[0]["id"] == job_id, "Dequeued job ID should match"

        logger.info(f"✓ Job dequeued: {jobs[0]['id']}")
    except Exception as e:
        pytest.fail(f"Redis queue dequeue failed: {e}")
    finally:
        await manager.close()
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


@pytest.mark.asyncio
async def test_redis_queue_status(db_session, test_env_file):
    """Test getting queue status from Redis."""
    load_config.cache_clear()
    _require_redis_config()
    timeout = _get_timeout()
    manager = QueueManager(db=db_session, use_redis=True)
    try:
        status = await _require_redis_queue_enabled(manager, timeout)

        assert "pending" in status, "Status should include pending count"
        assert "redis_enabled" in status, "Status should include redis_enabled flag"

        logger.info(f"✓ Queue status: Redis enabled = {status.get('redis_enabled', False)}")
    except Exception as e:
        pytest.fail(f"Redis queue status failed: {e}")
    finally:
        await manager.close()
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


@pytest.mark.asyncio
async def test_redis_queue_update_and_cancel(db_session, test_env_file):
    """Test updating and cancelling jobs in Redis queue."""
    load_config.cache_clear()
    _require_redis_config()
    timeout = _get_timeout()
    manager = QueueManager(db=db_session, use_redis=True)
    try:
        await _require_redis_queue_enabled(manager, timeout)
        job_id = await manager.enqueue(
            job_type="test_update",
            priority=7,
            metadata={"test": "update"},
        )
        updated = manager.update_job_status(job_id, "processing")
        assert updated is True

        job = manager.job_manager.get_job(job_id)
        assert job is not None
        assert job.status == "processing"

        cancelled = await asyncio.wait_for(manager.cancel_job(job_id), timeout=timeout)
        assert cancelled is True

        job = manager.job_manager.get_job(job_id)
        assert job is not None
        assert job.status == "cancelled"
    except Exception as e:
        pytest.fail(f"Redis queue update/cancel failed: {e}")
    finally:
        await manager.close()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.db, pytest.mark.heavy]

