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
Context Window Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages context windows and message history

Related Requirements: FR1.2
Related Tasks: T010
Related Architecture: CC2.1.1
Related Tests: UT1.10

Recent Changes:
- Initial implementation
"""

from typing import List, Dict
from src.core.session.manager import SessionManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContextManager:
    """Manages context windows."""

    def __init__(self, session_manager: SessionManager):
        """
        Initialize context manager.

        Args:
            session_manager: Session manager instance
        """
        self.session_manager = session_manager

    def get_context_messages(
        self, session_id: int, max_tokens: int, include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get messages for context window.

        Args:
            session_id: Session ID
            max_tokens: Maximum tokens for context
            include_system: Whether to include system message

        Returns:
            List of messages within token limit
        """
        # Get message history
        messages = self.session_manager.get_message_history(session_id, max_tokens=max_tokens)

        # Filter system messages if needed
        if not include_system:
            messages = [m for m in messages if m.get("role") != "system"]

        return messages

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count (rough: 4 chars per token)
        """
        return len(text) // 4

    def truncate_messages(
        self, messages: List[Dict[str, str]], max_tokens: int, preserve_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Truncate messages to fit within token limit.

        Args:
            messages: List of messages
            max_tokens: Maximum tokens
            preserve_system: Whether to preserve system messages

        Returns:
            Truncated message list
        """
        system_messages = []
        other_messages = []

        # Separate system and other messages
        for msg in messages:
            if msg.get("role") == "system" and preserve_system:
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        # Calculate system token count
        system_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in system_messages)
        remaining_tokens = max(0, max_tokens - system_tokens)

        # Add messages from end until token limit
        truncated = []
        total_tokens = 0

        for msg in reversed(other_messages):
            msg_tokens = self.estimate_tokens(msg.get("content", ""))
            if total_tokens + msg_tokens > remaining_tokens:
                break
            truncated.insert(0, msg)
            total_tokens += msg_tokens

        # Combine system and truncated messages
        return system_messages + truncated
