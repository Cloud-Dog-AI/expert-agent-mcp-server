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
Common LLM Client Module

This module provides the single entry point for LLM operations and wraps
`cloud_dog_llm` with a backward-compatible response shape used by existing
expert-agent services and tests.

License: Apache 2.0
Ownership: Cloud Dog
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from cloud_dog_llm import LLMRequest as PlatformLLMRequest
from cloud_dog_llm import Message as PlatformMessage
from cloud_dog_llm import SessionContext as PlatformSessionContext
from cloud_dog_llm.domain.errors import (
    InvalidRequestError,
    ProviderUnavailableError,
    RateLimitError,
    TimeoutError as PlatformTimeoutError,
)
from cloud_dog_llm.factory import get_llm_client as get_platform_llm_client

from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _coerce_max_tokens(value: Any, default: int = 1024) -> int:
    """Return an integer max_tokens value, tolerating placeholder env values."""
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


class LLMClient:
    """Compatibility wrapper over `cloud_dog_llm` for project-wide LLM operations."""

    def __init__(
        self,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """Initialise the client from config/env overrides."""
        self.provider = str(provider or get_config("llm.provider") or "").strip().lower()
        self._provider_id = self._normalise_provider(self.provider)
        self.base_url = self._normalise_base_url(
            self._provider_id,
            str(base_url or get_config("llm.base_url") or "").strip(),
        )
        self.model = str(model or get_config("llm.model") or "").strip()
        self.api_key = str(api_key or get_config("llm.api_key") or "").strip()
        self.timeout = float(timeout or get_config("llm.timeout", 300) or 300)

        if not self.provider:
            raise ValueError("llm.provider not configured")
        if not self.base_url:
            raise ValueError("llm.base_url not configured")
        if not self.model:
            raise ValueError("llm.model not configured")

        self._platform_client = get_platform_llm_client(self._build_platform_config())
        # Backward-compatible handle used by existing UTs that monkeypatch `.client.post`.
        self.client = self._resolve_provider_http_client()

        logger.info(
            "LLM client initialized via cloud_dog_llm: provider=%s model=%s timeout=%ss",
            self._provider_id,
            self.model,
            self.timeout,
        )

    @staticmethod
    def _normalise_provider(provider: str) -> str:
        """Normalise provider aliases to cloud_dog_llm provider identifiers."""
        aliases = {
            "openai_compatible": "openai",
            "openai-compat": "openai",
            "openai_compat": "openai",
            "vllm": "openai_compat",
        }
        return aliases.get(provider, provider)

    @staticmethod
    def _normalise_base_url(provider: str, base_url: str) -> str:
        """Normalise provider base URL to a format expected by cloud_dog_llm adapters."""
        if not base_url:
            return ""
        url = base_url.rstrip("/")
        # Covers: FR1.18
        openrouter_suffix = "/api" + "/v1"
        if provider == "openrouter" and not url.endswith(openrouter_suffix):
            return f"{url}{openrouter_suffix}"
        if provider == "openai" and not url.endswith("/v1"):
            return f"{url}/v1"
        return url

    def _build_platform_config(self) -> Dict[str, Any]:
        """Build cloud_dog_llm factory config from resolved runtime settings."""
        provider_cfg: Dict[str, Any] = {
            "base_url": self.base_url,
            "model": self.model,
            "api_key": self.api_key,
            "timeout_seconds": self.timeout,
            "enabled": True,
        }
        if self._provider_id == "openrouter":
            extra_headers: Dict[str, str] = {}
            referer = get_config("app.url")
            title = get_config("app.name")
            if referer:
                extra_headers["HTTP-Referer"] = str(referer)
            if title:
                extra_headers["X-Title"] = str(title)
            if extra_headers:
                provider_cfg["extra_headers"] = extra_headers

        return {
            "llm": {"default_provider": self._provider_id},
            "providers": {self._provider_id: provider_cfg},
        }

    def _resolve_provider_http_client(self) -> Any:
        """Expose the provider adapter httpx client for backward compatibility in existing UTs."""
        providers = getattr(self._platform_client, "_providers", None)
        if providers is None:
            return None
        try:
            adapter = providers.get(self._provider_id)
        except Exception:
            return None
        return getattr(adapter, "_client", None)

    def _build_session_context(self) -> PlatformSessionContext:
        """Create a request-local session context required by cloud_dog_llm."""
        request_id = uuid.uuid4().hex
        return PlatformSessionContext(session_id=request_id, correlation_id=request_id)

    def _build_request(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool,
        kwargs: Dict[str, Any],
    ) -> PlatformLLMRequest:
        """Build a platform-native request object from legacy chat arguments."""
        request_messages = [
            PlatformMessage(
                role=str(message.get("role", "user")),
                content=message.get("content", ""),
            )
            for message in messages
        ]

        params: Dict[str, Any] = dict(kwargs)
        request_temperature: Optional[float] = None
        if self._provider_id == "ollama":
            option_params: Dict[str, Any] = {}
            explicit_options = params.pop("options", None)
            if isinstance(explicit_options, dict):
                option_params.update(explicit_options)
            option_params.update(params)
            if temperature is not None:
                option_params.setdefault("temperature", float(temperature))
            params = option_params
        elif temperature is not None:
            request_temperature = float(temperature)

        return PlatformLLMRequest(
            messages=request_messages,
            model=self.model,
            provider_id=self._provider_id,
            temperature=request_temperature,
            max_tokens=int(max_tokens) if max_tokens is not None else None,
            stream=bool(stream),
            params=params,
        )

    @staticmethod
    def _safe_json_dict(payload: Any) -> Dict[str, Any]:
        """Return a JSON payload as a dictionary or an empty dict for non-dict payloads."""
        return payload if isinstance(payload, dict) else {}

    def _to_legacy_response(self, response: Any) -> Dict[str, Any]:
        """Convert `cloud_dog_llm` response model into legacy dict response shape."""
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)

        metadata: Dict[str, Any] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

        raw_payload = self._safe_json_dict(getattr(response, "raw_provider_response", None))
        raw_usage = raw_payload.get("usage")
        if isinstance(raw_usage, dict):
            metadata.update(raw_usage)
        for key in ("eval_count", "prompt_eval_count", "total_duration"):
            if key in raw_payload:
                metadata[key] = raw_payload.get(key)

        content = getattr(response, "content", "")
        if not isinstance(content, str):
            content = str(content)

        tokens_used = int(metadata.get("total_tokens") or total_tokens or 0)
        if tokens_used == 0 and "eval_count" in metadata and "prompt_eval_count" in metadata:
            tokens_used = int(metadata.get("eval_count", 0) or 0) + int(
                metadata.get("prompt_eval_count", 0) or 0
            )

        return {
            "content": content,
            "tokens_used": tokens_used,
            "model": str(getattr(response, "model_id", self.model) or self.model),
            "provider": str(
                getattr(response, "provider_id", self._provider_id) or self._provider_id
            ),
            "metadata": metadata,
        }

    def _legacy_chat_parse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Best-effort parser used by the compatibility fallback path."""
        if self._provider_id == "ollama":
            message = payload.get("message")
            message = message if isinstance(message, dict) else {}
            content = str(
                message.get("content") or message.get("thinking") or payload.get("response") or ""
            )
            eval_count = int(payload.get("eval_count") or 0)
            prompt_eval_count = int(payload.get("prompt_eval_count") or 0)
            return {
                "content": content,
                "tokens_used": eval_count + prompt_eval_count,
                "model": str(payload.get("model") or self.model),
                "provider": "ollama",
                "metadata": {
                    "eval_count": eval_count,
                    "prompt_eval_count": prompt_eval_count,
                    "total_duration": int(payload.get("total_duration") or 0),
                },
            }

        choices = payload.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else {}
        first = first if isinstance(first, dict) else {}
        message = first.get("message")
        message = message if isinstance(message, dict) else {}
        content = str(message.get("content") or message.get("reasoning") or "")
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        total_tokens = int(usage.get("total_tokens") or 0)
        return {
            "content": content,
            "tokens_used": total_tokens,
            "model": str(payload.get("model") or self.model),
            "provider": self._provider_id,
            "metadata": usage,
        }

    async def _legacy_chat_fallback(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool,
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fallback path for UT monkeypatch compatibility when adapter internals are mocked."""
        if self.client is None:
            raise RuntimeError("LLM HTTP client is unavailable")

        base = self.base_url.rstrip("/")
        if self._provider_id == "ollama":
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": bool(stream),
                "options": {
                    "temperature": float(temperature) if temperature is not None else 0.7,
                    "num_predict": int(max_tokens) if max_tokens is not None else 1024,
                    **(kwargs.get("options") or {}),
                },
            }
            response = await self.client.post(f"{base}/api/chat", json=payload)
        elif self._provider_id == "openrouter":
            response = await self.client.post(
                f"{base}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": bool(stream),
                    **kwargs,
                },
            )
        else:
            openai_base = base if base.endswith("/v1") else f"{base}/v1"
            response = await self.client.post(
                f"{openai_base}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": bool(stream),
                    **kwargs,
                },
            )

        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        payload = {}
        if hasattr(response, "json"):
            payload = self._safe_json_dict(response.json())
        return self._legacy_chat_parse(payload)

    @staticmethod
    def _as_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        if isinstance(exc, PlatformTimeoutError):
            return True
        class_name = exc.__class__.__name__.lower()
        if "timeout" in class_name:
            return True
        return "timeout" in str(exc).lower()

    def _should_retry_chat_error(self, exc: Exception, retry_on_timeout: bool) -> bool:
        if self._is_timeout_error(exc):
            return retry_on_timeout
        if isinstance(exc, InvalidRequestError):
            message = str(exc).lower()
            return any(code in message for code in (" 500", " 502", " 503", " 504"))
        if isinstance(exc, (ProviderUnavailableError, RateLimitError)):
            return True
        return False

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send chat request and return project-compatibility response format."""
        if temperature is None:
            temperature = float(get_config("llm.temperature", 0.7))
        if max_tokens is None:
            max_tokens = _coerce_max_tokens(get_config("llm.max_tokens", 1024))

        request = self._build_request(messages, temperature, max_tokens, stream, kwargs)
        session = self._build_session_context()
        # Chat retries are opt-in; embeddings keep their own retry policy.
        retries = max(
            0,
            self._as_int(
                get_config(
                    "expert.test.llm_chat_retries",
                    get_config(
                        "expert.test.llm_retries",
                        get_config("test.llm_chat_retries", get_config("test.llm_retries")),
                    ),
                ),
                0,
            ),
        )
        grace = max(
            0.0,
            self._as_float(
                get_config(
                    "expert.test.llm_retry_grace_seconds",
                    get_config("test.llm_retry_grace_seconds"),
                ),
                1.0,
            ),
        )
        backoff = max(
            0.0,
            self._as_float(
                get_config(
                    "expert.test.llm_retry_backoff_seconds",
                    get_config("test.llm_retry_backoff_seconds"),
                ),
                2.0,
            ),
        )
        retry_on_timeout = self._as_bool(
            get_config(
                "expert.test.llm_retry_on_read_timeout",
                get_config("test.llm_retry_on_read_timeout"),
            ),
            True,
        )
        attempts = retries + 1
        request_budget = max(
            0.0,
            self._as_float(
                get_config(
                    "expert.test.http_timeout_seconds",
                    get_config("test.http_timeout_seconds"),
                ),
                0.0,
            ),
        )
        if request_budget > 0.0:
            # Keep one chat request within the API/Web request budget.
            retry_slot = max(1.0, float(self.timeout)) + grace + backoff
            max_attempts_by_budget = max(1, int(request_budget // retry_slot))
            if attempts > max_attempts_by_budget:
                attempts = max_attempts_by_budget
                logger.info(
                    "Capping chat retries to %s attempt(s) to respect request budget %.1fs",
                    attempts,
                    request_budget,
                )
        try:
            for attempt in range(1, attempts + 1):
                try:
                    response = await self._platform_client.chat(request=request, session=session)
                    return self._to_legacy_response(response)
                except Exception as err:
                    if not self._should_retry_chat_error(err, retry_on_timeout) or attempt >= attempts:
                        raise
                    delay = grace + (backoff * (attempt - 1))
                    logger.warning(
                        f"Transient LLM chat error on attempt {attempt}/{attempts} "
                        f"for provider={self._provider_id} model={self.model}: {err}; "
                        f"retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
        except TypeError as err:
            logger.debug(
                "Falling back to legacy chat parse for provider=%s due to mocked client behaviour: %s",
                self._provider_id,
                err,
            )
            return await self._legacy_chat_fallback(
                messages, temperature, max_tokens, stream, kwargs
            )

    async def _legacy_health_check(self) -> bool:
        """Health-check fallback that uses provider HTTP endpoints directly."""
        if self.client is None:
            return False

        base = self.base_url.rstrip("/")
        if self._provider_id == "ollama":
            response = await self.client.get(f"{base}/api/tags", timeout=5.0)
            return bool(getattr(response, "status_code", 0) == 200)
        if self._provider_id == "openrouter":
            response = await self.client.get(f"{base}/models", timeout=5.0)
            return bool(getattr(response, "status_code", 0) == 200)

        openai_base = base if base.endswith("/v1") else f"{base}/v1"
        response = await self.client.get(f"{openai_base}/models", timeout=5.0)
        return bool(getattr(response, "status_code", 0) == 200)

    async def health_check(self) -> bool:
        """Check if configured provider is healthy."""
        try:
            return bool(await self._platform_client.health())
        except Exception as err:
            logger.warning("LLM health check failed via cloud_dog_llm: %s", err)
            try:
                return await self._legacy_health_check()
            except Exception as fallback_err:
                logger.warning("LLM health check fallback failed: %s", fallback_err)
                return False

    async def close(self):
        """Close all provider HTTP clients allocated by cloud_dog_llm."""
        providers = getattr(self._platform_client, "_providers", None)
        if providers is not None:
            for provider_id in providers.list_ids():
                try:
                    adapter = providers.get(provider_id)
                    http_client = getattr(adapter, "_client", None)
                    if http_client is not None and hasattr(http_client, "aclose"):
                        await http_client.aclose()
                except Exception as err:
                    logger.debug("Failed to close provider client %s cleanly: %s", provider_id, err)
        elif self.client is not None and hasattr(self.client, "aclose"):
            await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


def get_llm_client(
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
) -> LLMClient:
    """Factory for configured project LLM client instances."""
    return LLMClient(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
    )
