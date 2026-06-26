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
LLM Provider Implementations

License: Apache 2.0
Ownership: Cloud Dog
Description: Concrete LLM provider implementations

Related Requirements: FR1.1, FR1.12
Related Tasks: T008, T056
Related Architecture: IP1.1.1, IP1.1.4
Related Tests: UT1.8

Recent Changes:
- Initial implementation
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List

from src.common.llm_client import LLMClient, get_llm_client
from src.config.loader import get_config


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate a response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict with 'content', 'tokens_used', 'model', etc.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is healthy."""
        pass


class OllamaProvider(LLMProvider):
    """Ollama LLM provider."""

    def __init__(self, base_url: str, model: str, timeout: int = 300):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._client: LLMClient = get_llm_client(
            provider="ollama",
            base_url=base_url,
            model=model,
            timeout=timeout,
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> Dict[str, Any]:
        return await self._client.chat(
            messages=messages,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            **kwargs,
        )

    async def health_check(self) -> bool:
        return await self._client.health_check()

    async def close(self):
        await self._client.close()


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible provider."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 300):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client: LLMClient = get_llm_client(
            provider="openai",
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=timeout,
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> Dict[str, Any]:
        return await self._client.chat(
            messages=messages,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            **kwargs,
        )

    async def health_check(self) -> bool:
        return await self._client.health_check()

    async def close(self):
        await self._client.close()


class OpenRouterProvider(LLMProvider):
    """OpenRouter.ai provider."""

    def __init__(self, api_key: str, model: str, timeout: int = 300):
        base_url = get_config("llm.base_url")
        if not base_url:
            raise ValueError("llm.base_url not configured")
        self.base_url = str(base_url)
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client: LLMClient = get_llm_client(
            provider="openrouter",
            base_url=self.base_url,
            model=model,
            api_key=api_key,
            timeout=timeout,
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> Dict[str, Any]:
        return await self._client.chat(
            messages=messages,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            **kwargs,
        )

    async def health_check(self) -> bool:
        return await self._client.health_check()

    async def close(self):
        await self._client.close()
