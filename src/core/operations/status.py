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
Long-running Operation Status Tracking

License: Apache 2.0
Ownership: Cloud Dog
Description: Status polling and progress tracking for long-running operations

Related Requirements: FR1.14
Related Tasks: T038
Related Architecture: CC7.1
Related Tests: UT1.43, ST1.25

Recent Changes:
- Initial implementation
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy.orm import Session
import uuid

from src.database.connection import get_db
from src.database.models import Job
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OperationStatus(str, Enum):
    """Operation status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class OperationType(str, Enum):
    """Operation type values."""

    LLM_GENERATION = "llm_generation"
    VECTOR_INDEXING = "vector_indexing"
    KNOWLEDGE_INGESTION = "knowledge_ingestion"
    SESSION_PROCESSING = "session_processing"
    BATCH_OPERATION = "batch_operation"
    CUSTOM = "custom"


class LongRunningOperation:
    """Represents a long-running operation with status tracking."""

    def __init__(
        self,
        operation_id: str,
        operation_type: OperationType,
        status: OperationStatus = OperationStatus.PENDING,
        progress: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """
        Initialize long-running operation.

        Args:
            operation_id: Unique operation ID
            operation_type: Type of operation
            status: Current status
            progress: Progress percentage (0.0 to 100.0)
            metadata: Additional metadata
            created_at: Creation timestamp
            updated_at: Last update timestamp
            completed_at: Completion timestamp
            result: Operation result (if completed)
            error: Error message (if failed)
        """
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.status = status
        self.progress = progress
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.completed_at = completed_at
        self.result = result
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "status": self.status.value,
            "progress": self.progress,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
        }


class OperationStatusManager:
    """Manages long-running operation status tracking."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize operation status manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self._operations: Dict[str, LongRunningOperation] = {}

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def create_operation(
        self, operation_type: OperationType, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new long-running operation.

        Args:
            operation_type: Type of operation
            metadata: Additional metadata

        Returns:
            Operation ID
        """
        operation_id = str(uuid.uuid4())

        operation = LongRunningOperation(
            operation_id=operation_id,
            operation_type=operation_type,
            status=OperationStatus.PENDING,
            progress=0.0,
            metadata=metadata or {},
        )

        self._operations[operation_id] = operation

        # Also create a job record in database
        try:
            db = self._get_db()
            job = Job(
                job_type=operation_type.value,
                status="pending",
                metadata_json=str(metadata) if metadata else None,
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            # Store job ID in operation metadata
            operation.metadata["job_id"] = job.id
        except Exception as e:
            logger.warning(f"Failed to create job record: {e}")

        logger.info(f"Created operation {operation_id} of type {operation_type.value}")
        return operation_id

    def update_operation_status(
        self,
        operation_id: str,
        status: OperationStatus,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update operation status.

        Args:
            operation_id: Operation ID
            status: New status
            progress: Progress percentage (0.0 to 100.0)
            result: Operation result (if completed)
            error: Error message (if failed)

        Returns:
            True if updated successfully
        """
        if operation_id not in self._operations:
            logger.warning(f"Operation {operation_id} not found")
            return False

        operation = self._operations[operation_id]
        operation.status = status
        operation.updated_at = datetime.utcnow()

        if progress is not None:
            operation.progress = max(0.0, min(100.0, progress))

        if status == OperationStatus.COMPLETED:
            operation.completed_at = datetime.utcnow()
            if result:
                operation.result = result

        if status == OperationStatus.FAILED:
            operation.completed_at = datetime.utcnow()
            if error:
                operation.error = error

        # Update job record in database
        try:
            if "job_id" in operation.metadata:
                db = self._get_db()
                job = db.query(Job).filter(Job.id == operation.metadata["job_id"]).first()
                if job:
                    job.status = status.value
                    if result:
                        job.metadata_json = str(result)
                    db.commit()
        except Exception as e:
            logger.warning(f"Failed to update job record: {e}")

        logger.debug(f"Updated operation {operation_id} status to {status.value}")
        return True

    def get_operation_status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get operation status.

        Args:
            operation_id: Operation ID

        Returns:
            Operation status dictionary or None if not found
        """
        if operation_id not in self._operations:
            logger.warning(f"Operation {operation_id} not found")
            return None

        return self._operations[operation_id].to_dict()

    def list_operations(
        self,
        operation_type: Optional[OperationType] = None,
        status: Optional[OperationStatus] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List operations with optional filters.

        Args:
            operation_type: Filter by operation type
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of operation status dictionaries
        """
        operations = list(self._operations.values())

        # Apply filters
        if operation_type:
            operations = [op for op in operations if op.operation_type == operation_type]

        if status:
            operations = [op for op in operations if op.status == status]

        # Sort by updated_at descending
        operations.sort(key=lambda op: op.updated_at, reverse=True)

        # Limit results
        operations = operations[:limit]

        return [op.to_dict() for op in operations]

    def cancel_operation(self, operation_id: str, reason: Optional[str] = None) -> bool:
        """
        Cancel an operation.

        Args:
            operation_id: Operation ID
            reason: Cancellation reason

        Returns:
            True if cancelled successfully
        """
        if operation_id not in self._operations:
            logger.warning(f"Operation {operation_id} not found")
            return False

        operation = self._operations[operation_id]

        # Only cancel if not already completed/failed/cancelled
        if operation.status in [
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        ]:
            logger.warning(
                f"Operation {operation_id} cannot be cancelled (status: {operation.status.value})"
            )
            return False

        operation.status = OperationStatus.CANCELLED
        operation.completed_at = datetime.utcnow()
        operation.updated_at = datetime.utcnow()
        if reason:
            operation.metadata["cancellation_reason"] = reason

        # Update job record
        try:
            if "job_id" in operation.metadata:
                db = self._get_db()
                job = db.query(Job).filter(Job.id == operation.metadata["job_id"]).first()
                if job:
                    job.status = "cancelled"
                    db.commit()
        except Exception as e:
            logger.warning(f"Failed to update job record: {e}")

        logger.info(f"Cancelled operation {operation_id}")
        return True

    def check_timeout(self, operation_id: str, timeout_seconds: int = 3600) -> bool:
        """
        Check if operation has timed out.

        Args:
            operation_id: Operation ID
            timeout_seconds: Timeout in seconds

        Returns:
            True if operation has timed out
        """
        if operation_id not in self._operations:
            return False

        operation = self._operations[operation_id]

        # Only check timeout for running operations
        if operation.status != OperationStatus.RUNNING:
            return False

        elapsed = (datetime.utcnow() - operation.created_at).total_seconds()

        if elapsed > timeout_seconds:
            self.update_operation_status(
                operation_id,
                OperationStatus.TIMEOUT,
                error=f"Operation timed out after {timeout_seconds} seconds",
            )
            return True

        return False

    def cleanup_old_operations(self, days: int = 7) -> int:
        """
        Clean up old completed/failed operations.

        Args:
            days: Number of days to keep operations

        Returns:
            Number of operations cleaned up
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        to_remove = []
        for operation_id, operation in self._operations.items():
            if operation.completed_at and operation.completed_at < cutoff:
                if operation.status in [
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                    OperationStatus.CANCELLED,
                    OperationStatus.TIMEOUT,
                ]:
                    to_remove.append(operation_id)

        for operation_id in to_remove:
            del self._operations[operation_id]

        logger.info(f"Cleaned up {len(to_remove)} old operations")
        return len(to_remove)
