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
Integration Tests for Embedding System

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests embedding generation and integration with vector stores

Related Requirements: FR1.3
Related Tasks: T015, T016
Related Architecture: IP1.1.2
Related Tests: IT2.6

Recent Changes:
- Initial implementation
"""

import asyncio

import pytest

from src.config.loader import get_config, load_config
from src.core.vector.embeddings import EmbeddingRuntime
from src.utils.logger import get_logger

logger = get_logger(__name__)


pytestmark = pytest.mark.integration


def _require_embeddings_config() -> float:
    provider = get_config("embeddings.provider") or get_config("llm.provider")
    model = get_config("embeddings.model")
    base_url = get_config("embeddings.base_url") or get_config("llm.base_url")
    timeout = get_config("embeddings.timeout") or get_config("llm.timeout")
    api_key = get_config("embeddings.api_key") or get_config("llm.api_key")
    if not provider:
        pytest.fail("embeddings.provider (or llm.provider) not configured")
    if not model:
        pytest.fail("embeddings.model not configured")
    if not base_url:
        pytest.fail("embeddings.base_url (or llm.base_url) not configured")
    if timeout is None:
        pytest.fail("embeddings.timeout (or llm.timeout) not configured")
    if str(provider).strip().lower() in ("openai", "openai_compatible") and not api_key:
        pytest.fail("embeddings.api_key (or llm.api_key) required for OpenAI-compatible embeddings")
    return float(timeout)
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_embedding_generation(test_env_file):
    """Test embedding generation."""
    load_config.cache_clear()
    timeout = _require_embeddings_config()
    manager = EmbeddingRuntime()
    try:
        embedding = await asyncio.wait_for(
            manager.generate_embedding("Hello, world!"),
            timeout=timeout,
        )

        assert embedding is not None, "Embedding generation returned None"
        assert isinstance(embedding, list), "Embedding should be a list"
        assert len(embedding) > 0, "Embedding should not be empty"
        assert all(isinstance(x, (int, float)) for x in embedding), (
            "Embedding should contain numbers"
        )

        logger.info(f"✓ Embedding generated: {len(embedding)} dimensions")
    except Exception as e:
        pytest.fail(f"Embedding generation failed (service may be unavailable): {e}")
    finally:
        await asyncio.wait_for(manager.close(), timeout=timeout)
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_embedding_batch(test_env_file):
    """Test batch embedding generation."""
    load_config.cache_clear()
    timeout = _require_embeddings_config()
    manager = EmbeddingRuntime()
    try:
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = await asyncio.wait_for(
            manager.generate_embeddings(texts),
            timeout=timeout,
        )

        assert embeddings is not None, "Batch embedding generation returned None"
        assert len(embeddings) == len(texts), (
            f"Expected {len(texts)} embeddings, got {len(embeddings)}"
        )
        assert all(len(emb) > 0 for emb in embeddings), "All embeddings should be non-empty"

        # Check all embeddings have same dimension
        dimensions = [len(emb) for emb in embeddings]
        assert len(set(dimensions)) == 1, "All embeddings should have the same dimension"

        logger.info(
            f"✓ Batch embeddings generated: {len(embeddings)} embeddings, {dimensions[0]} dimensions"
        )
    except Exception as e:
        pytest.fail(f"Batch embedding generation failed (service may be unavailable): {e}")
    finally:
        await asyncio.wait_for(manager.close(), timeout=timeout)
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_embedding_dimension(test_env_file):
    """Test embedding dimension property."""
    load_config.cache_clear()
    timeout = _require_embeddings_config()
    manager = EmbeddingRuntime()
    try:
        dimension = manager.dimension
        assert dimension > 0, "Embedding dimension should be positive"
        expected_dim = get_config("test.vector.embedding_dim")
        if expected_dim:
            assert int(dimension) == int(expected_dim), (
                f"Embedding dimension mismatch: {dimension} != {expected_dim}"
            )

        # Generate an embedding to verify dimension
        embedding = await asyncio.wait_for(
            manager.generate_embedding("Test"),
            timeout=timeout,
        )
        assert len(embedding) == dimension, (
            f"Embedding length should match dimension: {len(embedding)} != {dimension}"
        )

        logger.info(f"✓ Embedding dimension: {dimension}")
    except Exception as e:
        pytest.fail(f"Embedding dimension test failed: {e}")
    finally:
        await asyncio.wait_for(manager.close(), timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.llm, pytest.mark.vdb, pytest.mark.heavy]
