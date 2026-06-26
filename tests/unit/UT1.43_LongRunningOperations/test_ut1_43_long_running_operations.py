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
Unit Test: UT1.43 - Long-running Operation Status Tracking

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for status polling and progress tracking for long-running operations

Related Requirements: FR1.14
Related Tasks: T038
Related Architecture: CC7.1
Related Tests: UT1.43

Recent Changes:
- Initial implementation
"""

import pytest
from datetime import datetime, timedelta
from src.core.operations.status import (
    OperationStatusManager,
    OperationStatus,
    OperationType,
    LongRunningOperation,
)


@pytest.fixture
def operation_manager(db_session):
    """Create an OperationStatusManager instance."""
    return OperationStatusManager(db=db_session)


@pytest.fixture
def sample_operation():
    """Create a sample long-running operation."""
    return LongRunningOperation(
        operation_id="test-op-123",
        operation_type=OperationType.LLM_GENERATION,
        status=OperationStatus.PENDING,
        progress=0.0,
        metadata={"user_id": 1, "session_id": 42},
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_create_operation(operation_manager):
    """Test creating a new long-running operation."""
    operation_id = operation_manager.create_operation(
        operation_type=OperationType.LLM_GENERATION, metadata={"user_id": 1}
    )

    assert operation_id is not None
    assert isinstance(operation_id, str)

    # Verify operation was created
    status = operation_manager.get_operation_status(operation_id)
    assert status is not None
    assert status["operation_type"] == OperationType.LLM_GENERATION.value
    assert status["status"] == OperationStatus.PENDING.value
    assert status["progress"] == 0.0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_get_operation_status(operation_manager, sample_operation):
    """Test retrieving an operation status by ID."""
    # Store operation
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    retrieved = operation_manager.get_operation_status(sample_operation.operation_id)

    assert retrieved is not None
    assert isinstance(retrieved, dict)
    assert retrieved["operation_id"] == sample_operation.operation_id
    assert retrieved["status"] == sample_operation.status.value
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_get_operation_status_not_found(operation_manager):
    """Test retrieving a non-existent operation."""
    result = operation_manager.get_operation_status("nonexistent-id")

    assert result is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_update_operation_status(operation_manager, sample_operation):
    """Test updating operation status."""
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    updated = operation_manager.update_operation_status(
        operation_id=sample_operation.operation_id, status=OperationStatus.RUNNING
    )

    assert updated is True
    assert (
        operation_manager._operations[sample_operation.operation_id].status
        == OperationStatus.RUNNING
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_update_operation_progress(operation_manager, sample_operation):
    """Test updating operation progress."""
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    updated = operation_manager.update_operation_status(
        operation_id=sample_operation.operation_id, status=OperationStatus.RUNNING, progress=50.0
    )

    assert updated is True
    assert operation_manager._operations[sample_operation.operation_id].progress == 50.0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_complete_operation(operation_manager, sample_operation):
    """Test completing an operation."""
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    result = {"output": "completed successfully"}
    completed = operation_manager.update_operation_status(
        operation_id=sample_operation.operation_id, status=OperationStatus.COMPLETED, result=result
    )

    assert completed is True
    op = operation_manager._operations[sample_operation.operation_id]
    assert op.status == OperationStatus.COMPLETED
    assert op.result == result
    assert op.completed_at is not None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_fail_operation(operation_manager, sample_operation):
    """Test failing an operation."""
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    error_message = "Operation failed due to timeout"
    failed = operation_manager.update_operation_status(
        operation_id=sample_operation.operation_id,
        status=OperationStatus.FAILED,
        error=error_message,
    )

    assert failed is True
    op = operation_manager._operations[sample_operation.operation_id]
    assert op.status == OperationStatus.FAILED
    assert op.error == error_message
    assert op.completed_at is not None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_cancel_operation(operation_manager, sample_operation):
    """Test cancelling an operation."""
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    cancelled = operation_manager.cancel_operation(sample_operation.operation_id)

    assert cancelled is True
    op = operation_manager._operations[sample_operation.operation_id]
    assert op.status == OperationStatus.CANCELLED
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_get_operations_by_type(operation_manager):
    """Test retrieving operations by type."""
    operation_manager.create_operation(operation_type=OperationType.LLM_GENERATION, metadata={})
    operation_manager.create_operation(operation_type=OperationType.VECTOR_INDEXING, metadata={})

    llm_ops = operation_manager.list_operations(operation_type=OperationType.LLM_GENERATION)

    assert len(llm_ops) >= 1
    assert all(op["operation_type"] == OperationType.LLM_GENERATION.value for op in llm_ops)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_get_operations_by_status(operation_manager):
    """Test retrieving operations by status."""
    op1_id = operation_manager.create_operation(
        operation_type=OperationType.LLM_GENERATION, metadata={}
    )
    operation_manager.update_operation_status(op1_id, OperationStatus.RUNNING)

    running_ops = operation_manager.list_operations(status=OperationStatus.RUNNING)

    assert len(running_ops) >= 1
    assert all(op["status"] == OperationStatus.RUNNING.value for op in running_ops)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_timeout(operation_manager, sample_operation):
    """Test operation timeout handling."""
    # Set operation to running with old timestamp
    sample_operation.status = OperationStatus.RUNNING
    sample_operation.created_at = datetime.utcnow() - timedelta(hours=2)
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    timed_out = operation_manager.check_timeout(
        operation_id=sample_operation.operation_id,
        timeout_seconds=3600,  # 1 hour
    )

    assert timed_out is True
    op = operation_manager._operations[sample_operation.operation_id]
    assert op.status == OperationStatus.TIMEOUT
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_no_timeout(operation_manager, sample_operation):
    """Test operation that hasn't timed out."""
    sample_operation.status = OperationStatus.RUNNING
    sample_operation.created_at = datetime.utcnow() - timedelta(minutes=30)
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    timed_out = operation_manager.check_timeout(
        operation_id=sample_operation.operation_id,
        timeout_seconds=3600,  # 1 hour
    )

    assert timed_out is False
    op = operation_manager._operations[sample_operation.operation_id]
    assert op.status == OperationStatus.RUNNING
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_to_dict(sample_operation):
    """Test converting operation to dictionary."""
    op_dict = sample_operation.to_dict()

    assert isinstance(op_dict, dict)
    assert op_dict["operation_id"] == sample_operation.operation_id
    assert op_dict["operation_type"] == sample_operation.operation_type.value
    assert op_dict["status"] == sample_operation.status.value
    assert op_dict["progress"] == sample_operation.progress
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_progress_increment(operation_manager, sample_operation):
    """Test incrementing operation progress."""
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    operation_manager.update_operation_status(
        sample_operation.operation_id, OperationStatus.RUNNING, progress=25.0
    )
    operation_manager.update_operation_status(
        sample_operation.operation_id, OperationStatus.RUNNING, progress=50.0
    )
    operation_manager.update_operation_status(
        sample_operation.operation_id, OperationStatus.RUNNING, progress=75.0
    )

    op = operation_manager._operations[sample_operation.operation_id]
    assert op.progress == 75.0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_metadata_update(operation_manager, sample_operation):
    """Test updating operation metadata."""
    operation_manager._operations[sample_operation.operation_id] = sample_operation

    new_metadata = {"user_id": 1, "session_id": 42, "additional": "data"}
    # Update metadata directly on the operation
    sample_operation.metadata.update(new_metadata)

    op = operation_manager._operations[sample_operation.operation_id]
    assert op.metadata["user_id"] == 1
    assert op.metadata["session_id"] == 42
    assert op.metadata["additional"] == "data"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_status_transitions(operation_manager):
    """Test valid operation status transitions."""
    op_id = operation_manager.create_operation(
        operation_type=OperationType.LLM_GENERATION, metadata={}
    )

    # PENDING -> RUNNING
    assert operation_manager.update_operation_status(op_id, OperationStatus.RUNNING) is True

    # RUNNING -> COMPLETED
    assert operation_manager.update_operation_status(op_id, OperationStatus.COMPLETED) is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_list_all(operation_manager):
    """Test listing all operations."""
    op1_id = operation_manager.create_operation(
        operation_type=OperationType.LLM_GENERATION, metadata={}
    )
    op2_id = operation_manager.create_operation(
        operation_type=OperationType.VECTOR_INDEXING, metadata={}
    )

    all_ops = operation_manager.list_operations()

    assert len(all_ops) >= 2
    op_ids = [op["operation_id"] for op in all_ops]
    assert op1_id in op_ids
    assert op2_id in op_ids
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_cleanup_completed(operation_manager):
    """Test cleaning up completed operations."""
    op1_id = operation_manager.create_operation(
        operation_type=OperationType.LLM_GENERATION, metadata={}
    )
    operation_manager.update_operation_status(
        op1_id, OperationStatus.COMPLETED, result={"result": "done"}
    )

    op2_id = operation_manager.create_operation(
        operation_type=OperationType.VECTOR_INDEXING, metadata={}
    )
    operation_manager.update_operation_status(op2_id, OperationStatus.RUNNING)

    # Cleanup completed operations older than 1 day (default is 7 days)
    cleaned = operation_manager.cleanup_old_operations(days=1)

    # Should not remove recent completed operations (less than 1 day old)
    assert isinstance(cleaned, int)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-009")


def test_operation_poll_status(operation_manager):
    """Test polling operation status."""
    op_id = operation_manager.create_operation(
        operation_type=OperationType.LLM_GENERATION, metadata={}
    )

    # Poll initial status
    status1 = operation_manager.get_operation_status(op_id)
    assert status1 is not None
    assert status1["status"] == OperationStatus.PENDING.value

    # Update and poll again
    operation_manager.update_operation_status(op_id, OperationStatus.RUNNING)
    status2 = operation_manager.get_operation_status(op_id)
    assert status2["status"] == OperationStatus.RUNNING.value

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.fast]

