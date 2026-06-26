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
Queue Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Queue manager facade backed by cloud_dog_jobs

Related Requirements: FR1.26, UC1.20
Related Tasks: T064
Related Architecture: CC2.1.4
Related Tests: AT1.22

Recent Changes:
- Migrated queue backend integration to cloud_dog_jobs primitives
"""

from typing import Optional, Dict, Any, List
import json
from urllib.parse import quote_plus

from cloud_dog_jobs import (
    JobQueue,
    JobRequest,
    JobStateMachine,
    JobStatus as PlatformJobStatus,
    RedisQueueBackend,
    SQLQueueBackend,
    Worker,
)
from cloud_dog_jobs.maintenance.reaper import MaintenanceReaper
from sqlalchemy.orm import Session

from src.config.loader import get_config
from src.core.job.manager import JobManager
from src.database.connection import get_db, get_db_uri
from src.utils.logger import get_logger

logger = get_logger(__name__)


class QueueManager:
    """Manages queued jobs while preserving legacy queue manager interfaces."""

    _APP_TO_PLATFORM_STATUS = {
        "pending": PlatformJobStatus.QUEUED.value,
        "processing": PlatformJobStatus.RUNNING.value,
        "completed": PlatformJobStatus.SUCCEEDED.value,
        "failed": PlatformJobStatus.FAILED.value,
        "cancelled": PlatformJobStatus.CANCELLED.value,
    }

    _PLATFORM_TO_APP_STATUS = {
        PlatformJobStatus.QUEUED.value: "pending",
        PlatformJobStatus.SCHEDULED.value: "pending",
        PlatformJobStatus.RUNNING.value: "processing",
        PlatformJobStatus.RETRY_WAIT.value: "processing",
        PlatformJobStatus.PAUSED.value: "processing",
        PlatformJobStatus.TIMEOUT.value: "failed",
        PlatformJobStatus.TTL_EXPIRED.value: "failed",
        PlatformJobStatus.SUCCEEDED.value: "completed",
        PlatformJobStatus.FAILED.value: "failed",
        PlatformJobStatus.CANCELLED.value: "cancelled",
    }

    def __init__(self, db: Optional[Session] = None, use_redis: bool = True):
        """
        Initialize queue manager.

        Args:
            db: Database session (if None, creates new)
            use_redis: Whether to use Redis for queue (default: True)
        """
        self.db = db
        self.job_manager = JobManager(db)
        self.use_redis = use_redis
        self.job_queue: Optional[JobQueue] = None
        self.queue_backend = None
        self.state_machine = JobStateMachine()
        self.worker: Optional[Worker] = None
        self.maintenance_reaper: Optional[MaintenanceReaper] = None
        self._queue_initialized = False

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def _build_redis_url(self) -> Optional[str]:
        """Build redis URL from layered config values."""
        redis_host = get_config("redis.host")
        redis_port = get_config("redis.port")
        redis_db = get_config("redis.db")
        redis_username = get_config("redis.username")
        redis_password = get_config("redis.password")
        redis_ssl = get_config("redis.ssl")

        if redis_host is None or redis_port is None or redis_db is None:
            return None
        if redis_username is None or redis_password is None:
            return None

        scheme = "rediss" if str(redis_ssl).lower() in ("1", "true", "yes") else "redis"
        auth = ""
        if redis_username:
            auth = f"{quote_plus(str(redis_username))}:{quote_plus(str(redis_password))}@"
        elif redis_password:
            auth = f":{quote_plus(str(redis_password))}@"
        return f"{scheme}://{auth}{redis_host}:{int(redis_port)}/{int(redis_db)}"

    async def _get_queue(self) -> Optional[JobQueue]:
        """Get or initialize cloud_dog_jobs queue components."""
        if self._queue_initialized:
            return self.job_queue

        self._queue_initialized = True
        backend = None

        if self.use_redis:
            redis_url = self._build_redis_url()
            if redis_url:
                try:
                    backend = RedisQueueBackend(redis_url=redis_url, key_prefix="expert_agent")
                    if not backend.health_check():
                        raise RuntimeError("Redis backend health check failed")
                    logger.info("cloud_dog_jobs Redis queue backend initialised")
                except Exception as exc:
                    logger.warning(
                        "Failed to initialise cloud_dog_jobs Redis queue backend: %s",
                        exc,
                    )
                    self.use_redis = False

        if backend is None:
            sync_url, _ = get_db_uri()
            backend = SQLQueueBackend(sync_url)
            logger.info("Using cloud_dog_jobs SQL queue backend")

        self.queue_backend = backend
        self.job_queue = JobQueue(backend)
        self.worker = Worker(backend, host_id="expert-agent", worker_id="queue-manager")
        self.maintenance_reaper = MaintenanceReaper(backend)
        return self.job_queue

    @classmethod
    def _app_to_platform_status(cls, status: str) -> str:
        """Map app-level status to cloud_dog_jobs status."""
        return cls._APP_TO_PLATFORM_STATUS.get(status, PlatformJobStatus.QUEUED.value)

    @classmethod
    def _platform_to_app_status(cls, status: str) -> str:
        """Map cloud_dog_jobs status to app-level status."""
        return cls._PLATFORM_TO_APP_STATUS.get(status, "pending")

    def _extract_queue_job_id_for_app_job(self, app_job_id: int) -> Optional[str]:
        """Resolve queue job id for legacy DB job id."""
        job = self.job_manager.get_job(app_job_id)
        if not job or not job.metadata_json:
            return None
        try:
            metadata = json.loads(job.metadata_json)
        except json.JSONDecodeError:
            return None
        queue_job_id = metadata.get("queue_job_id")
        return str(queue_job_id) if queue_job_id else None

    @staticmethod
    def _extract_app_job_id(payload: Dict[str, Any]) -> Optional[int]:
        """Get app job id from queued payload if present."""
        app_job_id = payload.get("app_job_id")
        if app_job_id is None:
            return None
        try:
            return int(app_job_id)
        except (TypeError, ValueError):
            return None

    async def enqueue(
        self,
        job_type: str,
        session_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        user_id: Optional[int] = None,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Add job to queue (cloud_dog_jobs backend + application database).

        Args:
            job_type: Job type
            session_id: Session ID
            channel_id: Channel ID
            user_id: User ID
            priority: Job priority (higher = more important)
            metadata: Additional metadata

        Returns:
            Application job ID
        """
        if metadata is None:
            metadata = {}
        metadata["priority"] = priority

        # Persist legacy app job row first for existing admin/reporting features.
        job = self.job_manager.create_job(
            job_type=job_type,
            session_id=session_id,
            channel_id=channel_id,
            user_id=user_id,
            metadata=metadata,
        )

        queue = await self._get_queue()
        if queue:
            try:
                request = JobRequest(
                    job_type=job_type,
                    queue_name=job_type,
                    payload={
                        "app_job_id": job.id,
                        "job_type": job_type,
                        "session_id": session_id,
                        "channel_id": channel_id,
                        "user_id": user_id,
                        "priority": priority,
                        "metadata": metadata,
                        "created_at": job.created_at.isoformat() if job.created_at else None,
                    },
                    priority=priority,
                    app_id="expert-agent-mcp-server",
                    user_id=str(user_id) if user_id is not None else None,
                    session_id=str(session_id) if session_id is not None else None,
                    channel_id=str(channel_id) if channel_id is not None else None,
                )
                queue_job_id = await queue.submit_async(request)
                self.job_manager.update_job(job.id, metadata={"queue_job_id": queue_job_id})
                logger.debug("Queued app job %s with queue id %s", job.id, queue_job_id)
            except Exception as exc:
                logger.warning("Failed to enqueue job in cloud_dog_jobs backend: %s", exc)

        logger.info("Enqueued job: %s (%s, priority: %s)", job.id, job_type, priority)
        return job.id

    async def dequeue(self, limit: int = 1, job_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get next jobs from queue (cloud_dog_jobs backend or DB fallback).

        Args:
            limit: Maximum number of jobs to retrieve
            job_type: Optional job type filter

        Returns:
            List of job dictionaries
        """
        queue = await self._get_queue()
        if queue:
            try:
                queued_jobs = await queue.list_async(limit=limit, job_type=job_type)
                if queued_jobs:
                    jobs: List[Dict[str, Any]] = []
                    for queued_job in queued_jobs:
                        payload = dict(queued_job.payload or {})
                        app_job_id = self._extract_app_job_id(payload)

                        # Legacy dequeue semantics remove the item from queued state.
                        if self.queue_backend is not None:
                            self.queue_backend.update_status(
                                queued_job.job_id,
                                PlatformJobStatus.RUNNING.value,
                            )

                        if app_job_id is not None:
                            self.job_manager.update_job(app_job_id, status="processing")

                        jobs.append(
                            {
                                "id": app_job_id
                                if app_job_id is not None
                                else payload.get("id", queued_job.job_id),
                                "job_type": payload.get("job_type", queued_job.job_type),
                                "session_id": payload.get("session_id"),
                                "channel_id": payload.get("channel_id"),
                                "user_id": payload.get("user_id"),
                                "created_at": payload.get("created_at")
                                or (
                                    queued_job.created_at.isoformat()
                                    if queued_job.created_at
                                    else None
                                ),
                            }
                        )
                    return jobs
            except Exception as exc:
                logger.warning("Failed to dequeue from cloud_dog_jobs backend: %s", exc)

        # Fallback to pending DB rows if queue backend is unavailable.
        jobs = self.job_manager.list_jobs(status="pending", limit=limit)
        return [
            {
                "id": job.id,
                "job_type": job.job_type,
                "session_id": job.session_id,
                "channel_id": job.channel_id,
                "user_id": job.user_id,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            for job in jobs
        ]

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get queue status from cloud_dog_jobs backend and legacy DB."""
        db = self._get_db()
        from src.database.models import Job

        pending = db.query(Job).filter(Job.status == "pending").count()
        processing = db.query(Job).filter(Job.status == "processing").count()
        completed = db.query(Job).filter(Job.status == "completed").count()
        failed = db.query(Job).filter(Job.status == "failed").count()

        status = {
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "total": pending + processing + completed + failed,
            "redis_enabled": False,
            "redis_queue_sizes": {},
        }

        await self._get_queue()
        if self.queue_backend:
            try:
                status["redis_enabled"] = bool(self.use_redis and self.queue_backend.health_check())
                queue_sizes: Dict[str, int] = {}
                for queued_job in self.queue_backend.dequeue(limit=10000):
                    queue_sizes[queued_job.job_type] = queue_sizes.get(queued_job.job_type, 0) + 1
                status["redis_queue_sizes"] = queue_sizes
            except Exception as exc:
                logger.warning("Failed to get queue backend status: %s", exc)

        return status

    def update_job_status(self, job_id: int, status: str) -> bool:
        """Update app-level job status and mirror to mapped cloud_dog_jobs status."""
        updated_job = self.job_manager.update_job(job_id, status=status)
        if not updated_job:
            return False

        queue_job_id = self._extract_queue_job_id_for_app_job(job_id)
        if queue_job_id and self.queue_backend:
            try:
                self.queue_backend.update_status(queue_job_id, self._app_to_platform_status(status))
            except Exception as exc:
                logger.warning(
                    "Failed to mirror app job status to queue job (job_id=%s): %s",
                    job_id,
                    exc,
                )
        return True

    async def cancel_job(self, job_id: int) -> bool:
        """Cancel a job in cloud_dog_jobs queue and application database."""
        queue = await self._get_queue()
        removed_from_queue = False

        queue_job_id = self._extract_queue_job_id_for_app_job(job_id)
        if queue and queue_job_id:
            try:
                removed_from_queue = await queue.cancel_async(queue_job_id)
            except Exception as exc:
                logger.warning("Failed to cancel mapped queue job %s: %s", queue_job_id, exc)

        if queue and not removed_from_queue and self.queue_backend:
            try:
                for backend_job in self.queue_backend.all_jobs():
                    app_job_id = self._extract_app_job_id(dict(backend_job.payload or {}))
                    if app_job_id == job_id and await queue.cancel_async(backend_job.job_id):
                        removed_from_queue = True
                        break
            except Exception as exc:
                logger.warning(
                    "Failed to scan queue backend for app job cancellation (job_id=%s): %s",
                    job_id,
                    exc,
                )

        status_updated = self.update_job_status(job_id, "cancelled")
        return removed_from_queue or status_updated

    async def run_maintenance(
        self,
        ttl_seconds: int = 86400,
        retention_seconds: int = 2592000,
    ) -> Dict[str, int]:
        """Run cloud_dog_jobs maintenance sweep for stuck and expired jobs."""
        await self._get_queue()
        if not self.maintenance_reaper:
            return {"stuck_recovered": 0, "ttl_expired": 0, "retention_purged": 0}
        return self.maintenance_reaper.run_sweep(
            ttl_seconds=ttl_seconds,
            retention_seconds=retention_seconds,
        )

    async def close(self):
        """Close queue backend resources if backend exposes a close hook."""
        backend = self.queue_backend
        if not backend:
            return

        close_fn = getattr(backend, "close", None)
        if callable(close_fn):
            close_fn()
        else:
            client = getattr(backend, "_client", None)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

        self._queue_initialized = False
