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
Context Summarization

License: Apache 2.0
Ownership: Cloud Dog
Description: Summarizes long conversations to fit within context window

Related Requirements: FR1.2, T024
Related Tasks: T024
Related Architecture: CC2.1.1
Related Tests: UT1.10, AT1.10

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any
import json
import os
import uuid
from datetime import datetime

from cloud_dog_storage.backends.local import LocalStorage as _PlatformLocalStorage

from src.core.llm.manager import LLMManager
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# CWD-scoped storage backend for test-output logging.
_fs = _PlatformLocalStorage(root_path=".")


class ContextSummarizer:
    """Summarizes conversation context to fit within token limits."""

    def __init__(self):
        """Initialize context summarizer."""
        self.llm_manager = LLMManager()

    def _should_log_llm(self) -> bool:
        """Decide whether to log LLM operations (test-only)."""
        testing = get_config("test.enabled")
        if isinstance(testing, str):
            testing = testing.strip().lower() in ("true", "1", "yes", "on")
        if bool(testing):
            return True
        flag = get_config("test.llm_log_operations")
        if isinstance(flag, str):
            flag = flag.strip().lower() == "true"
        return bool(flag)

    def _log_llm_operation(self, payload: Dict[str, Any]) -> None:
        """Persist LLM call details during tests for inspection."""
        if not self._should_log_llm():
            return
        base_dir = os.path.join("working", "AT1.11_MCPToolWorkflows_TEST_OUTPUTS", "llm_operations")
        _fs.create_dir(base_dir, parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        suffix = uuid.uuid4().hex[:8]
        rel_path = os.path.join(base_dir, f"summarization_{timestamp}_{suffix}.json")
        _fs.write_bytes(rel_path, json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8"))

    async def summarize_history(
        self, messages: List[Dict[str, str]], max_tokens: int, preserve_recent: int = 5
    ) -> Dict[str, Any]:
        """
        Summarize message history while preserving recent messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens for summary
            preserve_recent: Number of recent messages to preserve

        Returns:
            Dict with 'summary' and 'preserved_messages'
        """
        if len(messages) <= preserve_recent:
            return {
                "summary": None,
                "preserved_messages": messages,
                "total_tokens": self._estimate_tokens(messages),
            }

        # Separate recent messages from older ones
        recent_messages = messages[-preserve_recent:]
        older_messages = messages[:-preserve_recent]

        # Initialize LLM if needed
        await self.llm_manager.initialize()

        # Create summarization prompt
        older_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in older_messages])

        summary_prompt = f"""Summarize the following conversation history while preserving key information, decisions, and context:

{older_text}

Provide a concise summary that captures:
- Key topics discussed
- Important decisions or conclusions
- Relevant context for continuing the conversation
- Any important facts or information shared

Summary:"""

        try:
            log_payload: Dict[str, Any] = {
                "event": "summarize_history",
                "provider": get_config("llm.provider"),
                "model": get_config("llm.model"),
                "base_url": get_config("llm.base_url"),
                "preserve_recent": preserve_recent,
                "max_tokens": max_tokens,
                "older_message_count": len(older_messages),
                "recent_message_count": len(recent_messages),
                "prompt_chars": len(summary_prompt),
                "prompt_tokens_estimate": self._estimate_tokens(older_messages),
                "prompt": summary_prompt,
            }

            response = await self.llm_manager.generate(
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,
                max_tokens=max_tokens // 2,  # Use half for summary
            )

            summary = response.get("content", "")
            log_payload["response"] = response
            log_payload["response_chars"] = len(summary or "")
            self._log_llm_operation(log_payload)

            # Combine summary with recent messages
            preserved_messages = [
                {"role": "system", "content": f"Previous conversation summary: {summary}"}
            ] + recent_messages

            return {
                "summary": summary,
                "preserved_messages": preserved_messages,
                "total_tokens": self._estimate_tokens(preserved_messages),
            }
        except Exception as e:
            self._log_llm_operation(
                {
                    "event": "summarize_history_error",
                    "provider": get_config("llm.provider"),
                    "model": get_config("llm.model"),
                    "base_url": get_config("llm.base_url"),
                    "preserve_recent": preserve_recent,
                    "max_tokens": max_tokens,
                    "older_message_count": len(older_messages),
                    "recent_message_count": len(recent_messages),
                    "prompt_chars": len(summary_prompt),
                    "prompt_tokens_estimate": self._estimate_tokens(older_messages),
                    "prompt": summary_prompt,
                    "error": str(e),
                }
            )
            logger.error(f"Failed to summarize history: {e}", exc_info=True)
            # Fallback: just return recent messages
            return {
                "summary": None,
                "preserved_messages": recent_messages,
                "total_tokens": self._estimate_tokens(recent_messages),
            }

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Estimate token count for messages."""
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        # Rough estimate: 4 characters per token
        return total_chars // 4
