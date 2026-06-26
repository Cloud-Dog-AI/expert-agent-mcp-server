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
Context Window Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages LLM context window limits

Related Requirements: FR1.2, T010
Related Tasks: T010
Related Architecture: CC2.1.1
Related Tests: UT1.10, AT1.10

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContextWindowManager:
    """Manages context window for LLM interactions."""

    def __init__(self, max_tokens: int = 4096):
        """
        Initialize context window manager.

        Args:
            max_tokens: Maximum tokens in context window
        """
        self.max_tokens = max_tokens
        self.reserved_tokens = 100  # Reserve for system prompts, etc.
        self.available_tokens = max_tokens - self.reserved_tokens

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Rough estimate: 4 characters per token
        return len(text) // 4

    def estimate_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        Estimate total tokens for messages.

        Args:
            messages: List of message dicts

        Returns:
            Total estimated tokens
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self.estimate_tokens(content)
            total += 5  # Overhead for role and formatting
        return total

    def fit_messages(
        self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Fit messages within token limit, keeping most recent.

        Args:
            messages: List of messages
            max_tokens: Maximum tokens (defaults to available)

        Returns:
            Fitted messages list
        """
        max_tokens = max_tokens or self.available_tokens

        if not messages:
            return []

        # Start from most recent and work backwards
        fitted = []
        total_tokens = 0

        for msg in reversed(messages):
            msg_tokens = self.estimate_tokens(msg.get("content", "")) + 5
            if total_tokens + msg_tokens > max_tokens:
                break
            fitted.insert(0, msg)
            total_tokens += msg_tokens

        return fitted

    def get_usage_stats(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Get context window usage statistics.

        Args:
            messages: List of messages

        Returns:
            Usage statistics dict
        """
        total_tokens = self.estimate_messages_tokens(messages)
        usage_percent = (total_tokens / self.max_tokens) * 100

        return {
            "total_tokens": total_tokens,
            "max_tokens": self.max_tokens,
            "available_tokens": self.max_tokens - total_tokens,
            "usage_percent": usage_percent,
            "near_limit": usage_percent > 80,
            "exceeded": total_tokens > self.max_tokens,
        }
