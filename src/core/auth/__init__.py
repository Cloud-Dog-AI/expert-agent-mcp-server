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
Authentication and Authorization Module

License: Apache 2.0
Ownership: Cloud Dog
Description: User, group, and API key management

Related Requirements: FR1.5, FR1.11, CS1.1
Related Tasks: T005, T006, T055
Related Architecture: CC5.1, SE1.1
Related Tests: AT1.7, ST1.7

Recent Changes:
- Initial implementation
"""

from .user_manager import UserManager
from .group_manager import GroupManager
from .api_key_manager import APIKeyManager
from .password import hash_password, verify_password

__all__ = ["UserManager", "GroupManager", "APIKeyManager", "hash_password", "verify_password"]
