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
LLM Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages LLM providers and connections

Related Requirements: FR1.1, FR1.12
Related Tasks: T007, T008, T056
Related Architecture: CC3.1.2
Related Tests: IT2.4
Recent Changes:
- Initial implementation
"""

import asyncio
from typing import Dict, Any, Optional, List
from src.common.llm_client import LLMClient, get_llm_client
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _coerce_max_tokens(value: Any, default: int = 1024) -> int:
    """Return an integer max_tokens value, falling back for placeholder env values."""
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


class LLMManager:
    """Manages LLM providers and connections."""

    def __init__(self, provider_config: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM manager.

        Args:
            provider_config: Provider-specific configuration (overrides config)
        """
        self.provider_config = provider_config or {}
        self.client: Optional[LLMClient] = None
        self._initialized = False
        self._active_config: Optional[Dict[str, Any]] = None

    async def initialize(
        self,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> bool:
        """
        Initialize LLM provider.

        Args:
            provider: Provider name (ollama, openai, openrouter)
            base_url: Base URL for provider
            model: Model name
            api_key: API key (if required)

        Returns:
            True if initialization successful
        """
        try:
            # Get configuration
            provider = (
                provider or self.provider_config.get("provider") or get_config("llm.provider")
            )
            base_url = (
                base_url or self.provider_config.get("base_url") or get_config("llm.base_url")
            )
            model = model or self.provider_config.get("model") or get_config("llm.model")
            api_key = api_key or self.provider_config.get("api_key") or get_config("llm.api_key")
            timeout = self.provider_config.get("timeout") or get_config("llm.timeout")
            # Ensure timeout is numeric
            if timeout is None:
                raise ValueError("llm.timeout not configured")
            timeout = float(timeout)

            if not provider:
                raise ValueError("llm.provider not configured")
            provider_name = str(provider).strip().lower()
            if provider_name not in {"ollama", "openai", "openrouter"}:
                raise ValueError(f"Unsupported llm.provider: {provider}")
            if not base_url:
                raise ValueError("llm.base_url not configured")
            if not model:
                raise ValueError("llm.model not configured")

            provider_name = str(provider).strip().lower()
            base_url_str = str(base_url).rstrip("/")
            model_str = str(model)
            timeout_int = int(timeout)
            normalized_config = {
                "provider": provider_name,
                "base_url": base_url_str,
                "model": model_str,
                "api_key": str(api_key) if api_key else None,
                "timeout": timeout_int,
            }

            # Fast path: already initialized for the same provider/model endpoint.
            # This avoids repeated client recreation and health checks per request.
            if self._initialized and self.client and self._active_config == normalized_config:
                return True

            # If a different config is requested, close the existing client first
            # to prevent leaked sockets/transports across repeated re-initialization.
            if self.client:
                try:
                    await self.client.close()
                except Exception as close_exc:
                    logger.warning(f"Failed to close existing LLM client cleanly: {close_exc}")

            logger.info(
                "Initializing LLM provider: %s model=%s base_url=%s",
                provider_name,
                model_str,
                base_url_str,
            )

            self.client = get_llm_client(
                provider=provider_name,
                base_url=base_url_str,
                model=model_str,
                api_key=normalized_config["api_key"],
                timeout=timeout_int,
            )

            # Health check (non-fatal to align with prior behavior)
            try:
                health_timeout = max(1.0, min(float(timeout_int), 5.0))
                if await asyncio.wait_for(self.client.health_check(), timeout=health_timeout):
                    logger.info(f"LLM provider {provider} initialized successfully")
                else:
                    logger.warning(f"LLM provider {provider} health check failed, but continuing")
            except asyncio.TimeoutError:
                logger.warning(
                    "LLM provider %s health check timed out after %.1fs, but continuing",
                    provider,
                    health_timeout,
                )
            except Exception as e:
                logger.warning(f"LLM provider {provider} health check errored, but continuing: {e}")

            self._initialized = True
            self._active_config = normalized_config
            return True

        except Exception as e:
            logger.error(f"Failed to initialize LLM provider: {e}", exc_info=True)
            self._initialized = False
            self.client = None
            self._active_config = None
            return False

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate response from LLM using common client.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (defaults to config)
            max_tokens: Maximum tokens (defaults to config)
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict with 'content', 'tokens_used', 'model', etc.
        """
        if not self._initialized or not self.client:
            await self.initialize()

        if not self.client:
            raise RuntimeError("LLM client not initialized")

        if temperature is None:
            temperature = float(get_config("llm.temperature", 0.7))
        if max_tokens is None:
            max_tokens = _coerce_max_tokens(get_config("llm.max_tokens", 1024))

        return await self.client.chat(
            messages=messages,
            temperature=float(temperature),
            max_tokens=_coerce_max_tokens(max_tokens),
            **kwargs,
        )

    async def health_check(self) -> bool:
        """Check if LLM provider is healthy."""
        if not self.client:
            return False
        return await self.client.health_check()

    async def close(self):
        """Close LLM provider connections."""
        if self.client:
            await self.client.close()
        self._initialized = False
        self.client = None
        self._active_config = None
