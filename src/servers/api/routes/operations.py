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
Long-running Operation Status Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: API endpoints for long-running operation status polling

Related Requirements: FR1.7
Related Tasks: T038
Related Architecture: AI1.1
Related Tests: ST1.25

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from src.database.connection import get_db
from src.core.operations.status import OperationStatusManager, OperationStatus, OperationType
from src.servers.api.auth import require_permission

router = APIRouter(prefix="/operations", tags=["operations"], dependencies=[Depends(require_permission("expert:execute"))])


class CancelOperationRequest(BaseModel):
    reason: Optional[str] = None


@router.get("")
async def list_operations(
    operation_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> List[Dict[str, Any]]:
    """
    List long-running operations with optional filters.

    Args:
        operation_type: Filter by operation type
        status: Filter by status
        limit: Maximum number of results
        offset: Offset for pagination
        db: Database session
        x_api_key: API key for authentication

    Returns:
        List of operation status dictionaries
    """
    manager = OperationStatusManager(db=db)

    # Convert string filters to enums
    op_type = None
    if operation_type:
        try:
            op_type = OperationType(operation_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid operation type: {operation_type}")

    op_status = None
    if status:
        try:
            op_status = OperationStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    operations = manager.list_operations(operation_type=op_type, status=op_status, limit=limit)

    # Apply offset manually (since list_operations doesn't support it)
    return operations[offset : offset + limit]


@router.get("/{operation_id}")
async def get_operation_status(
    operation_id: str, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Get operation status by ID.

    Args:
        operation_id: Operation ID
        db: Database session
        x_api_key: API key for authentication

    Returns:
        Operation status dictionary
    """
    manager = OperationStatusManager(db=db)
    status = manager.get_operation_status(operation_id)

    if status is None:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")

    return status


@router.post("/{operation_id}/cancel")
async def cancel_operation(
    operation_id: str,
    request: CancelOperationRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """
    Cancel a long-running operation.

    Args:
        operation_id: Operation ID
        request: Cancellation request with optional reason
        db: Database session
        x_api_key: API key for authentication

    Returns:
        Updated operation status
    """
    manager = OperationStatusManager(db=db)

    cancelled = manager.cancel_operation(operation_id, reason=request.reason)

    if not cancelled:
        raise HTTPException(
            status_code=400,
            detail=f"Operation {operation_id} cannot be cancelled (may already be completed/failed/cancelled)",
        )

    status = manager.get_operation_status(operation_id)
    return status
