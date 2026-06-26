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
Embedding runtime for vector providers.

License: Apache 2.0
Ownership: Cloud Dog
Description: Thin expert-agent adapter over cloud_dog_vdb embedding providers.
"""

from __future__ import annotations

import hashlib
from typing import Any

from cloud_dog_vdb.config.models import ProviderConfig
from cloud_dog_vdb.embeddings.base import EmbeddingProvider
from cloud_dog_vdb.embeddings.providers import build_embedding_provider

from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _as_bool(value: Any, default: bool = False) -> bool:
    """Coerce common string and numeric truth values to bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _as_float(value: Any, default: float) -> float:
    """Coerce a runtime config value to float with a fallback."""
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int) -> int:
    """Coerce a runtime config value to int with a fallback."""
    try:
        return int(value)
    except Exception:
        return int(default)


def _test_mode_embedding_fallback_enabled() -> bool:
    """Return whether deterministic embeddings are allowed for test config."""
    return _as_bool(get_config("test.enabled"), False)


def _deterministic_embedding(text: str, dimension: int) -> list[float]:
    """Generate a stable test embedding without contacting a provider."""
    size = max(1, int(dimension))
    seed = text.encode("utf-8", errors="ignore") or b" "
    vector: list[float] = []
    counter = 0
    while len(vector) < size:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for offset in range(0, len(digest), 4):
            chunk = digest[offset : offset + 4]
            if len(chunk) < 4:
                continue
            raw = int.from_bytes(chunk, "big", signed=False)
            vector.append((raw / 4294967295.0) * 2.0 - 1.0)
            if len(vector) >= size:
                break
        counter += 1
    return vector


class EmbeddingRuntime:
    """Small compatibility layer over cloud_dog_vdb embedding providers."""

    def __init__(self) -> None:
        """Initialise the embedding runtime without opening network clients."""
        self._provider: EmbeddingProvider | None = None
        self._dimension = _as_int(get_config("embeddings.dimension"), 1024)

    @staticmethod
    def _normalise_provider_id(provider_id: str) -> str:
        """Map project provider aliases to cloud_dog_vdb provider IDs."""
        resolved = str(provider_id or "").strip().lower()
        if resolved == "openai_compatible":
            return "openai_compat"
        return resolved

    @staticmethod
    def _config_value(*paths: str, default: Any = None) -> Any:
        """Return the first non-empty config value from a list of paths."""
        for path in paths:
            value = get_config(path)
            if value not in (None, ""):
                return value
        return default

    def _resolved_config(self) -> ProviderConfig:
        """Build the cloud_dog_vdb provider config from runtime settings."""
        provider_id = self._normalise_provider_id(
            str(self._config_value("embeddings.provider", "llm.provider", default=""))
        )
        base_url = str(
            self._config_value(
                "embeddings.base_url",
                f"embeddings.{provider_id}.base_url",
                "llm.base_url",
                default="",
            )
        ).strip()
        model = str(
            self._config_value(
                "embeddings.model",
                f"embeddings.{provider_id}.model",
                "llm.model",
                default="",
            )
        ).strip()
        api_key = str(
            self._config_value(
                "embeddings.api_key",
                f"embeddings.{provider_id}.api_key",
                "llm.api_key",
                default="",
            )
        ).strip()
        timeout_seconds = _as_float(
            self._config_value(
                "embeddings.timeout",
                "embeddings.timeout_seconds",
                f"embeddings.{provider_id}.timeout_seconds",
                "llm.timeout",
                default=30.0,
            ),
            30.0,
        )

        if not provider_id:
            raise ValueError("embeddings.provider not configured")
        if not base_url:
            raise ValueError("embeddings base_url not configured")
        if not model:
            raise ValueError("embeddings model not configured")
        if provider_id in {"openai", "openai_compat", "vllm"} and not api_key:
            raise ValueError("embeddings api_key not configured")

        return ProviderConfig(
            provider_id="embedding-runtime",
            embedding_provider_id=provider_id,
            embedding_base_url=base_url,
            embedding_api_key=api_key,
            embedding_model=model,
            embedding_timeout_seconds=timeout_seconds,
        )

    async def initialize(self) -> None:
        """Build the configured embedding provider once."""
        if self._provider is not None:
            return
        self._provider = build_embedding_provider(self._resolved_config())
        if self._provider is None:
            raise ValueError("Failed to build cloud_dog_vdb embedding provider")

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate one embedding using the configured provider."""
        if self._provider is None:
            await self.initialize()
        assert self._provider is not None
        try:
            vector = await self._provider.embed(text)
        except Exception as exc:
            if not _test_mode_embedding_fallback_enabled():
                raise
            logger.warning(
                "Falling back to deterministic test embeddings after provider error: %s",
                exc,
            )
            return _deterministic_embedding(text, self._dimension)
        if vector:
            self._dimension = len(vector)
        return vector

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a sequence of text inputs."""
        if not texts:
            return []
        return [await self.generate_embedding(text) for text in texts]

    async def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate a batch of embeddings using the sequential provider path."""
        return await self.generate_embeddings(texts)

    @property
    def dimension(self) -> int:
        """Return the most recently observed embedding dimension."""
        return self._dimension

    def get_embedding_dimension(self) -> int:
        """Return the current embedding dimension for legacy callers."""
        return self.dimension

    async def close(self) -> None:
        """Close any provider client held by the runtime."""
        provider = self._provider
        self._provider = None
        if provider is None:
            return
        client = getattr(provider, "_client", None)
        if client is not None and hasattr(client, "aclose"):
            await client.aclose()
