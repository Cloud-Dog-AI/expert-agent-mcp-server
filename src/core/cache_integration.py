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

"""Expert-agent cache integration helpers built on cloud_dog_cache."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from cloud_dog_cache import cached, hash_config, hash_text


def build_context_hash(payload: Any) -> str:
    """Return a stable hash for request context payloads."""
    return hash_text(_stable_text(payload))


def build_model_config_hash(config: Dict[str, Any]) -> str:
    """Return a stable hash for LLM/model configuration."""
    return hash_config(config)


def build_prompt_hash(prompt: Optional[str]) -> str:
    """Return a stable hash for the active system prompt."""
    return hash_text(str(prompt or ""))


def _stable_text(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, default=str)


@cached(
    ttl=300,
    invalidate_on=("context_rebuild", "config_change", "prompt_change"),
    key_params=(
        "message",
        "expert_id",
        "channel_id",
        "temperature",
        "top_k",
        "top_p",
        "max_tokens",
        "response_format",
        "language",
        "system_prompt",
    ),
    context_hash_param="context_hash",
    model_config_hash_param="model_config_hash",
    prompt_hash_param="prompt_hash",
)
async def cached_expert_query_response(
    *,
    message: str,
    expert_id: int,
    channel_id: int,
    temperature: float,
    top_k: Optional[int],
    top_p: Optional[float],
    max_tokens: int,
    response_format: str,
    language: str,
    system_prompt: str,
    context_hash: str,
    model_config_hash: str,
    prompt_hash: str,
    generate_fn: Callable[[], Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Cache expert query responses for repeated live channel-chat requests."""
    return await generate_fn()


@cached(
    ttl=3600,
    invalidate_on=("config_change", "prompt_change"),
    key_params=(
        "title",
        "details",
        "context_type",
        "expected_outcomes",
        "available_tools",
    ),
    model_config_hash_param="model_config_hash",
)
async def cached_prompt_generation(
    *,
    title: str,
    details: str,
    context_type: str,
    expected_outcomes: str,
    available_tools: List[str],
    model_config_hash: str,
    generate_fn: Callable[[], Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Cache generated prompts for equivalent expert descriptions."""
    return await generate_fn()


@cached(
    ttl=3600,
    invalidate_on=("context_rebuild", "config_change"),
    key_params=("user_id", "knowledge_type", "knowledge_id", "limit", "offset"),
)
async def cached_knowledge_history(
    *,
    user_id: int,
    knowledge_type: str,
    knowledge_id: int,
    limit: Optional[int],
    offset: int,
    load_fn: Callable[[], Awaitable[List[Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    """Cache knowledge retrieval results until the underlying context changes."""
    return await load_fn()
