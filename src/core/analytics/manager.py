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
Analytics Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages channel analytics and metrics

Related Requirements: FR1.22, FR1.23, UC1.17
Related Tasks: T061
Related Architecture: MO1.4.1
Related Tests: AT1.21

Recent Changes:
- Initial implementation
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.database.models import Job, CallLog
from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalyticsManager:
    """Manages channel analytics."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize analytics manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def get_channel_analytics(
        self,
        channel_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get analytics for a channel.

        Args:
            channel_id: Channel ID
            start_date: Start date (default: 30 days ago)
            end_date: End date (default: now)

        Returns:
            Analytics dict
        """
        db = self._get_db()

        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        # Get jobs for channel
        jobs = (
            db.query(Job)
            .filter(
                Job.channel_id == channel_id,
                Job.created_at >= start_date,
                Job.created_at <= end_date,
            )
            .all()
        )

        # Calculate metrics
        total_jobs = len(jobs)
        completed_jobs = len([j for j in jobs if j.status == "completed"])
        failed_jobs = len([j for j in jobs if j.status == "failed"])
        success_rate = (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0

        # Get call logs for jobs
        job_ids = [j.id for j in jobs]
        call_logs = db.query(CallLog).filter(CallLog.job_id.in_(job_ids)).all()

        # Calculate token and cost metrics
        total_input_tokens = sum(cl.input_tokens or 0 for cl in call_logs)
        total_output_tokens = sum(cl.output_tokens or 0 for cl in call_logs)
        total_tokens = total_input_tokens + total_output_tokens
        total_cost = sum(cl.cost_usd or 0 for cl in call_logs)
        avg_latency = (
            sum(cl.latency_ms or 0 for cl in call_logs) / len(call_logs) if call_logs else 0
        )

        return {
            "channel_id": channel_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "usage": {
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "success_rate": round(success_rate, 2),
            },
            "tokens": {
                "total": total_tokens,
                "input": total_input_tokens,
                "output": total_output_tokens,
            },
            "cost": {"total_usd": round(total_cost, 4)},
            "performance": {"avg_latency_ms": round(avg_latency, 2)},
        }

    def get_user_analytics(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get analytics for a user."""
        db = self._get_db()

        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        jobs = (
            db.query(Job)
            .filter(
                Job.user_id == user_id, Job.created_at >= start_date, Job.created_at <= end_date
            )
            .all()
        )

        return {
            "user_id": user_id,
            "total_jobs": len(jobs),
            "completed_jobs": len([j for j in jobs if j.status == "completed"]),
            "failed_jobs": len([j for j in jobs if j.status == "failed"]),
        }
