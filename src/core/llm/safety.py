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
Safety and Moderation Controls

License: Apache 2.0
Ownership: Cloud Dog
Description: Safety filters and moderation controls for LLM responses

Related Requirements: FR1.1, T011
Related Tasks: T011
Related Architecture: CC3.1.2
Related Tests: UT1.11

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any
import re
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SafetyFilter:
    """Safety and moderation filters for LLM content."""

    def __init__(self):
        """Initialize safety filter."""
        # Define patterns for unsafe content (can be expanded)
        self.unsafe_patterns = [
            r"\b(bomb|explosive|weapon|kill|murder)\b",
            r"\b(hack|exploit|vulnerability|breach)\b",
            # Add more patterns as needed
        ]
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.unsafe_patterns
        ]

    def check_content(self, content: str) -> Dict[str, Any]:
        """
        Check content for safety violations.

        Args:
            content: Content to check

        Returns:
            Dict with 'safe', 'violations', 'filtered_content'
        """
        violations = []
        filtered_content = content

        for pattern in self.compiled_patterns:
            matches = pattern.findall(content)
            if matches:
                violations.extend(matches)
                # Replace with [REDACTED]
                filtered_content = pattern.sub("[REDACTED]", filtered_content)

        is_safe = len(violations) == 0

        return {
            "safe": is_safe,
            "violations": list(set(violations)),
            "filtered_content": filtered_content if not is_safe else content,
        }

    def filter_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Filter messages for safety.

        Args:
            messages: List of message dicts

        Returns:
            Filtered messages
        """
        filtered = []
        for msg in messages:
            result = self.check_content(msg.get("content", ""))
            if result["safe"]:
                filtered.append(msg)
            else:
                # Replace with filtered content
                filtered_msg = msg.copy()
                filtered_msg["content"] = result["filtered_content"]
                filtered.append(filtered_msg)
                logger.warning(f"Safety filter applied to message: {result['violations']}")

        return filtered
