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
Context Retention Prompt Engineering

Specialized prompts for ensuring LLM context retention across multi-turn conversations.
Different LLMs have different context retention capabilities - this module provides
optimized prompts for each model family.

License: Apache 2.0
Ownership: Cloud Dog

Related Requirements: CM1.1, FR1.12
Related Architecture: CC1.8, CC3.1.2
"""

from typing import Dict, List

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContextRetentionPromptEngine:
    """
    Manages context retention prompts for different LLM models.

    Each model family (Qwen, Llama, GPT, etc.) has different strengths
    and weaknesses in context retention. This engine provides optimized
    system prompts and conversation formatting for each.
    """

    # Model-specific context retention prompts
    QWEN_CONTEXT_PROMPT = """You are a helpful assistant engaged in a conversation. 

CRITICAL INSTRUCTIONS FOR CONTEXT RETENTION:
1. ALWAYS remember information shared by the user in previous messages
2. When asked about previously mentioned information, refer back to it explicitly
3. If the user introduces themselves or shares personal details, remember them
4. Maintain conversation continuity by referencing earlier parts of the discussion

Current conversation context:
{context_summary}

Respond naturally while demonstrating you remember the conversation history."""

    LLAMA_CONTEXT_PROMPT = """You are a helpful assistant. Pay close attention to the conversation history.

Key points to remember:
{context_summary}

When responding:
- Reference information from earlier in the conversation when relevant
- Show that you remember what the user has told you
- Maintain continuity across multiple exchanges"""

    GPT_CONTEXT_PROMPT = """You are a helpful assistant. You have access to the full conversation history.

Important context from this conversation:
{context_summary}

Use this context to provide informed, contextually-aware responses."""

    DEFAULT_CONTEXT_PROMPT = """You are a helpful assistant. Remember the conversation history and use it to provide contextually appropriate responses.

Key information from this conversation:
{context_summary}"""

    @classmethod
    def get_context_prompt(cls, model: str, conversation_history: List[Dict[str, str]]) -> str:
        """
        Get optimized context retention prompt for a specific model.

        Args:
            model: Model name (e.g., "qwen2.5:14b", "llama3.2:latest")
            conversation_history: List of previous messages

        Returns:
            Optimized system prompt for context retention
        """
        # Extract key context from conversation
        context_summary = cls._extract_context_summary(conversation_history)

        # Select prompt based on model family
        model_lower = model.lower()

        if "qwen" in model_lower:
            template = cls.QWEN_CONTEXT_PROMPT
        elif "llama" in model_lower:
            template = cls.LLAMA_CONTEXT_PROMPT
        elif "gpt" in model_lower or "openai" in model_lower:
            template = cls.GPT_CONTEXT_PROMPT
        else:
            template = cls.DEFAULT_CONTEXT_PROMPT

        return template.format(context_summary=context_summary)

    @classmethod
    def _extract_context_summary(cls, conversation_history: List[Dict[str, str]]) -> str:
        """
        Extract key information from conversation history.

        Identifies:
        - User introductions (names, roles, etc.)
        - Important facts shared
        - Questions asked
        - Topics discussed

        Args:
            conversation_history: List of previous messages

        Returns:
            Summary of key context
        """
        if not conversation_history:
            return "No previous context."

        # Extract user messages (skip system messages)
        user_messages = [msg for msg in conversation_history if msg.get("role") == "user"]

        if not user_messages:
            return "No previous user messages."

        # Build context summary
        summary_parts = []

        for i, msg in enumerate(user_messages, 1):
            content = msg.get("content", "")

            # Check for self-introduction patterns
            intro_keywords = ["my name is", "i am", "i'm", "call me"]
            if any(keyword in content.lower() for keyword in intro_keywords):
                summary_parts.append(f"Message {i}: User introduced themselves - {content[:100]}")
            else:
                summary_parts.append(f"Message {i}: {content[:80]}...")

        return (
            "\n".join(summary_parts) if summary_parts else "Previous messages available in history."
        )

    @classmethod
    def format_messages_with_context(
        cls, messages: List[Dict[str, str]], model: str, enhance_context: bool = True
    ) -> List[Dict[str, str]]:
        """
        Format messages with enhanced context retention.

        Args:
            messages: Original message list
            model: Model name
            enhance_context: Whether to add context retention prompt

        Returns:
            Enhanced message list with context retention prompts
        """
        if not enhance_context or len(messages) < 2:
            return messages

        # Separate system messages from conversation
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        conversation = [msg for msg in messages if msg.get("role") != "system"]

        # If there's already a system message, enhance it
        if system_messages:
            # Get context summary
            context_summary = cls._extract_context_summary(
                conversation[:-1]
            )  # Exclude current message

            # Enhance the first system message
            enhanced_system = system_messages[0].copy()
            original_content = enhanced_system.get("content", "")

            # Add context retention instructions
            model_lower = model.lower()
            if "qwen" in model_lower:
                context_addition = f"\n\nCONTEXT RETENTION: Remember all information shared in this conversation. Key context:\n{context_summary}"
            else:
                context_addition = f"\n\nRemember the conversation context:\n{context_summary}"

            enhanced_system["content"] = original_content + context_addition

            # Rebuild messages
            return [enhanced_system] + system_messages[1:] + conversation
        else:
            # Add new system message with context retention
            context_prompt = cls.get_context_prompt(model, conversation[:-1])
            return [{"role": "system", "content": context_prompt}] + conversation


def enhance_messages_for_context_retention(
    messages: List[Dict[str, str]], model: str
) -> List[Dict[str, str]]:
    """
    Convenience function to enhance messages for context retention.

    Args:
        messages: Original message list
        model: Model name

    Returns:
        Enhanced message list
    """
    return ContextRetentionPromptEngine.format_messages_with_context(
        messages, model, enhance_context=True
    )
