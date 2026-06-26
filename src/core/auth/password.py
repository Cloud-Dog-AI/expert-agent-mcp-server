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
Password Hashing Utilities

License: Apache 2.0
Ownership: Cloud Dog
Description: Password hashing and verification

Related Requirements: CS1.1
Related Tasks: T005
Related Architecture: SE1.1
Related Tests: UT1.5

Recent Changes:
- Initial implementation
"""

import asyncio
from queue import Queue
from threading import Thread
from typing import Optional

from cloud_dog_idam.config.models import PasswordPolicyConfig
from cloud_dog_idam.domain.errors import AuthenticationError
from cloud_dog_idam.domain.enums import UserStatus
from cloud_dog_idam.domain.models import AuthRequest, User
from cloud_dog_idam.providers.local_password import LocalPasswordProvider
from cloud_dog_idam.security.password_policy import PasswordPolicy

from src.utils.logger import get_logger
from src.config.loader import get_config

logger = get_logger(__name__)


def _run_auth_coro(coro) -> None:
    """Run an auth coroutine to completion whether or not an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    result_queue: Queue[tuple[bool, object | None]] = Queue(maxsize=1)

    def _runner() -> None:
        """Run the coroutine on a dedicated event loop in this worker thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro)
            result_queue.put((True, None))
        except Exception as exc:  # noqa: BLE001
            result_queue.put((False, exc))
        finally:
            loop.close()

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    ok, value = result_queue.get()
    if ok:
        return
    raise value if isinstance(value, Exception) else RuntimeError("Password auth execution failed")


def _build_password_provider(hashed_password: str | None = None) -> LocalPasswordProvider:
    """Build a cloud_dog_idam LocalPasswordProvider bound to a single stored password hash."""
    stored_hash = str(hashed_password or "")

    def _lookup(_: str) -> User:
        """Return the synthetic local user carrying the stored password hash for verification."""
        return User(
            user_id="local-password-user",
            username="local-password-user",
            email="local-password-user@example.com",
            status=UserStatus.ACTIVE,
            role="user",
            password_hash=stored_hash,
        )

    return LocalPasswordProvider(_lookup)


def hash_password(password: str) -> str:
    """
    Hash a password using cloud_dog_idam's local password provider.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    provider = _build_password_provider()
    return provider.hash_password(password)


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        password: Plain text password
        hashed: Hashed password string

    Returns:
        True if password matches
    """
    try:
        provider = _build_password_provider(hashed)
        _run_auth_coro(
            provider.authenticate(
                AuthRequest(
                    auth_type="local_password",
                    principal="local-password-user",
                    secret=password,
                )
            )
        )
        return True
    except AuthenticationError:
        return False
    except Exception as e:
        logger.error(f"Password verification error: {e}", exc_info=True)
        return False


def validate_password_policy(password: Optional[str]) -> None:
    """
    Validate password against configured policy.

    Reads:
    - auth.password_min_length
    - auth.password_require_complexity
    """
    if password is None:
        return

    min_len = get_config("auth.password_min_length")
    try:
        min_len_i = int(min_len) if min_len is not None else 8
    except Exception:
        min_len_i = 8

    if len(password) < min_len_i:
        raise ValueError(f"Password must be at least {min_len_i} characters long")

    require_complexity = get_config("auth.password_require_complexity")
    if require_complexity is None:
        require_complexity = True
    require_complexity = bool(require_complexity)

    policy = PasswordPolicy(
        PasswordPolicyConfig(
            min_length=min_len_i,
            require_uppercase=require_complexity,
            require_lowercase=require_complexity,
            require_digit=require_complexity,
            require_special=require_complexity,
        )
    )
    valid, reason = policy.validate(password)
    if not valid:
        raise ValueError(reason)
