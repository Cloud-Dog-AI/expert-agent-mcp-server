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
Session Management Module

License: Apache 2.0
Ownership: Cloud Dog
Description: Session creation, management, and message history

Related Requirements: FR1.2, FR1.12
Related Tasks: T022, T023, T024
Related Architecture: CC2.1.1
Related Tests: IT2.5, AT1.5

Recent Changes:
- Initial implementation
"""

from .manager import SessionManager
from .models import SessionState

__all__ = ["SessionManager", "SessionState"]
