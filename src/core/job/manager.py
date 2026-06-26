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
Job Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages job and call logging

Related Requirements: FR1.14, UC1.8
Related Tasks: T052
Related Architecture: CC7.1
Related Tests: AT1.15

Recent Changes:
- Initial implementation
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session

from src.database.models import Job, CallLog
from src.database.connection import get_db
from src.core.job.callbacks import CallbackManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class JobManager:
    """Manages jobs and call logs."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize job manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self.callback_manager = CallbackManager()

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def create_job(
        self,
        job_type: str,
        session_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        user_id: Optional[int] = None,
        prompt_sent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Job:
        """
        Create a new job.

        Args:
            job_type: Job type (e.g., 'llm_call', 'vector_search')
            session_id: Associated session ID
            channel_id: Associated channel ID
            user_id: Associated user ID
            prompt_sent: Prompt sent to LLM
            metadata: Additional metadata

        Returns:
            Created job
        """
        db = self._get_db()
        try:
            job = Job(
                job_type=job_type,
                session_id=session_id,
                channel_id=channel_id,
                user_id=user_id,
                status="pending",
                prompt_sent=prompt_sent,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            logger.debug(f"Created job: {job.id} ({job_type})")
            return job
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create job: {e}", exc_info=True)
            raise

    def update_job(
        self,
        job_id: int,
        status: Optional[str] = None,
        response_received: Optional[str] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
        vector_context: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        error_info: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Job]:
        """Update job with results."""
        db = self._get_db()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None

            if status:
                job.status = status
            if response_received:
                job.response_received = response_received
            if performance_metrics:
                job.performance_metrics_json = json.dumps(performance_metrics)
            if vector_context:
                job.vector_context_json = json.dumps(vector_context)
            if tool_calls:
                job.tool_calls_json = json.dumps(tool_calls)
            if error_info:
                job.error_info_json = json.dumps(error_info)
            if metadata:
                # Merge with existing metadata
                existing_metadata = json.loads(job.metadata_json) if job.metadata_json else {}
                existing_metadata.update(metadata)
                job.metadata_json = json.dumps(existing_metadata)

            if status in ["completed", "failed"]:
                job.completed_at = datetime.utcnow()

            db.commit()
            db.refresh(job)

            logger.debug(f"Updated job: {job_id} (status: {status})")
            return job
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update job: {e}", exc_info=True)
            return None

    def log_llm_call(
        self,
        job_id: int,
        llm_provider: str,
        llm_model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        latency_ms: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> CallLog:
        """
        Log an LLM call.

        Args:
            job_id: Associated job ID
            llm_provider: LLM provider name
            llm_model: LLM model name
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            latency_ms: Latency in milliseconds
            cost_usd: Cost in USD

        Returns:
            Created call log
        """
        db = self._get_db()
        try:
            call_log = CallLog(
                job_id=job_id,
                llm_provider=llm_provider,
                llm_model=llm_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
            )
            db.add(call_log)
            db.commit()
            db.refresh(call_log)

            logger.debug(f"Logged LLM call: {call_log.id} ({llm_provider}/{llm_model})")
            return call_log
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to log LLM call: {e}", exc_info=True)
            raise

    def get_job(self, job_id: int) -> Optional[Job]:
        """Get job by ID."""
        db = self._get_db()
        return db.query(Job).filter(Job.id == job_id).first()

    def get_job_call_logs(self, job_id: int) -> List[CallLog]:
        """Get all call logs for a job."""
        db = self._get_db()
        return db.query(CallLog).filter(CallLog.job_id == job_id).all()

    def list_jobs(
        self,
        session_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Job]:
        """List jobs with filters."""
        db = self._get_db()
        query = db.query(Job)

        if session_id:
            query = query.filter(Job.session_id == session_id)
        if channel_id:
            query = query.filter(Job.channel_id == channel_id)
        if user_id:
            query = query.filter(Job.user_id == user_id)
        if status:
            query = query.filter(Job.status == status)

        return query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()

    def get_job_counts_by_status(self) -> Dict[str, int]:
        """Get job counts by status."""
        db = self._get_db()
        from sqlalchemy import func

        counts = db.query(Job.status, func.count(Job.id).label("count")).group_by(Job.status).all()

        return {status: count for status, count in counts}
