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
Session Models and Enums

License: Apache 2.0
Ownership: Cloud Dog
Description: Session state machine and models

Related Requirements: FR1.2
Related Tasks: T022
Related Architecture: CC2.1.1
Related Tests: IT2.5

Recent Changes:
- Initial implementation
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class SessionState(str, Enum):
    """Session state enumeration."""

    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SessionContext:
    """Session context information."""

    def __init__(
        self,
        session_id: int,
        user_id: int,
        expert_config_id: int,
        channel_id: Optional[int] = None,
        context_window: int = 4096,
        history_retention_days: int = 30,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.expert_config_id = expert_config_id
        self.channel_id = channel_id
        self.context_window = context_window
        self.history_retention_days = history_retention_days
        self.state = SessionState.CREATED
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.messages: list = []
        self.metadata: Dict[str, Any] = {}
