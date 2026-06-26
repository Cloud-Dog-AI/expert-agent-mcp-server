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
Expert Test Suite Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Expert test suite endpoints

Related Requirements: FR1.35, FR1.38, UC1.31
Related Tasks: T122
Related Architecture: TS1.1
Related Tests: PT1.20

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from src.database.connection import get_db
from src.database.models import User
from src.servers.api.auth import require_permission, verify_api_key
from src.core.testing.expert_test_suite import ExpertTestSuite

router = APIRouter(prefix="/testing", tags=["testing"], dependencies=[Depends(require_permission("expert:execute"))])


class RunTestSuiteRequest(BaseModel):
    channel_id: int
    test_cases: Optional[List[Dict[str, Any]]] = None
    user_id: Optional[int] = None


@router.post("/expert-suite")
async def run_expert_test_suite(
    request: RunTestSuiteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Run comprehensive test suite for expert configuration."""
    user_id = request.user_id or current_user.id

    test_suite = ExpertTestSuite(db)
    try:
        results = await test_suite.run_test_suite(
            channel_id=request.channel_id, test_cases=request.test_cases, user_id=user_id
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test suite failed: {str(e)}")
