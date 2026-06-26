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
Authentication Middleware

License: Apache 2.0
Ownership: Cloud Dog
Description: API key authentication middleware

Related Requirements: CS1.1, FR1.11
Related Tasks: T006, T055
Related Architecture: SE1.1
Related Tests: ST1.7

Recent Changes:
- Initial implementation
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from src.core.auth.api_key_manager import APIKeyManager
from src.database.connection import get_db
from src.database.models import APIKey, User
from src.core.auth.user_manager import UserManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class APIKeyAuth:
    """API key authentication."""

    def __init__(self):
        self.user_manager = None

    async def verify_api_key(
        self,
        api_key: Optional[str] = Header(None, alias="X-API-Key"),
        db: Session = Depends(get_db),
    ) -> Optional[APIKey]:
        """
        Verify API key from header.

        Args:
            api_key: API key from header

        Returns:
            APIKey object if valid

        Raises:
            HTTPException: If API key is invalid
        """
        if not api_key:
            raise HTTPException(
                status_code=401, detail="API key required. Include X-API-Key header."
            )

        api_key_manager = APIKeyManager(db)
        api_key_obj = api_key_manager.validate_key(api_key)
        if not api_key_obj:
            raise HTTPException(status_code=401, detail="Invalid or expired API key")

        return api_key_obj


# Global auth instance
_auth = APIKeyAuth()


async def get_current_user(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get current user from API key.

    Args:
        api_key: API key from header

    Returns:
        User object if authenticated

    Raises:
        HTTPException: If authentication fails
    """
    api_key_obj = await _auth.verify_api_key(api_key=api_key, db=db)

    if api_key_obj and api_key_obj.user_id:
        user_manager = UserManager(db)
        return user_manager.get_user(user_id=api_key_obj.user_id)

    return None


def require_auth():
    """Dependency for routes requiring authentication."""
    return Depends(get_current_user)
