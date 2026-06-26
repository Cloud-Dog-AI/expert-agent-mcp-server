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
Token Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Authentication token generation and validation

Related Requirements: CS1.1
Related Tasks: T006
Related Architecture: SE1.1
Related Tests: UT1.25

Recent Changes:
- Initial implementation
"""

from typing import Optional, Tuple

from cloud_dog_idam.domain.errors import TokenError
from cloud_dog_idam.tokens.jwt import JWTTokenService

from src.core.auth.audit import log_token_event
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TokenManager:
    """Manages authentication tokens."""

    def __init__(self):
        """Initialize token manager with config from hierarchy."""
        config = get_config()
        auth_config = config.get("auth", {}) if isinstance(config, dict) else {}

        # Get JWT secret from auth config
        self.secret_key = auth_config.get("jwt_secret")
        if not self.secret_key:
            # Generate a random secret if not configured (for testing)
            import secrets

            self.secret_key = secrets.token_urlsafe(32)
            logger.warning("No JWT secret configured, using generated secret (not for production!)")

        # Get algorithm - default to HS256 if not specified
        self.algorithm = auth_config.get("algorithm") or "HS256"
        self.issuer = str(auth_config.get("issuer") or "expert-agent")
        self.audience = str(auth_config.get("audience") or "expert-agent-users")

        # Get session timeout and convert to seconds
        session_timeout_minutes = auth_config.get("session_timeout_minutes")
        if session_timeout_minutes is None:
            session_timeout_minutes = 60  # Default 60 minutes
            logger.warning(
                f"No session_timeout_minutes in config, using default: {session_timeout_minutes}"
            )

        self.default_expires_in = int(session_timeout_minutes) * 60  # Convert to seconds
        self.revoked_tokens = set()  # In production, use Redis or database
        self._token_service = JWTTokenService(
            secret=str(self.secret_key),
            issuer=self.issuer,
            audience=self.audience,
            algorithm=str(self.algorithm),
            access_ttl=self.default_expires_in,
        )

    def generate_token(self, user_id: int, expires_in: Optional[int] = None) -> str:
        """
        Generate authentication token.

        Args:
            user_id: User ID
            expires_in: Token expiration in seconds (default: 1 hour)

        Returns:
            JWT token string
        """
        token_pair = self._token_service.issue(
            user_id=str(user_id),
            claims={"user_id": int(user_id)},
            ttl=int(expires_in) if expires_in is not None else None,
        )
        return token_pair.access_token

    def validate_token(self, token: str) -> Tuple[bool, Optional[int]]:
        """
        Validate authentication token.

        Args:
            token: JWT token string

        Returns:
            Tuple of (is_valid, user_id)
        """
        if token in self.revoked_tokens:
            return False, None

        try:
            payload = self._token_service.verify(token)
        except TokenError:
            log_token_event("token_validate", "failure", reason="invalid_or_expired")
            return False, None

        user_claim = payload.get("user_id", payload.get("sub"))
        try:
            return True, int(user_claim)
        except (TypeError, ValueError):
            log_token_event(
                "token_validate",
                "failure",
                subject=str(user_claim or ""),
                reason="invalid_user_claim",
            )
            return False, None

    def refresh_token(self, token: str) -> Optional[str]:
        """
        Refresh authentication token.

        Args:
            token: Existing JWT token

        Returns:
            New JWT token or None if original token invalid
        """
        is_valid, user_id = self.validate_token(token)
        if not is_valid:
            return None

        if user_id is None:
            return None
        return self.generate_token(user_id)

    def revoke_token(self, token: str) -> bool:
        """
        Revoke authentication token.

        Args:
            token: JWT token to revoke

        Returns:
            True if token revoked
        """
        self.revoked_tokens.add(token)
        try:
            claims = self._token_service.verify(token)
            token_id = claims.get("jti")
            if token_id:
                self._token_service.revoke(str(token_id))
        except TokenError:
            # Keep revocation idempotent even if token is already invalid.
            pass
        return True
