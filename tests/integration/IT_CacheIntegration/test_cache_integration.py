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

"""Integration Test: IT2.43 - cache integration coverage for expert-agent."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time

import pytest

from cloud_dog_cache import CacheConfig, cached, get_cache_manager, init_cache
from tests.helpers_orchestration import build_api_client, seed_admin


pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.heavy]


async def _fake_initialize(self, **kwargs):
    return True


async def _fake_generate(self, messages, temperature, max_tokens, **kwargs):
    await asyncio.sleep(0.15)
    seed = messages[-1]["content"]
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]
    payload = {
        "prompt": f"Generated prompt {digest}",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tool_recommendations": ["search"],
        "reasoning": f"reason:{digest}",
    }
    return {"content": json.dumps(payload), "tokens_used": 12, "model": "cache-test-model"}


@pytest.fixture
def cache_client(db_session, monkeypatch):
    monkeypatch.setattr("src.core.llm.manager.LLMManager.initialize", _fake_initialize)
    monkeypatch.setattr("src.core.llm.manager.LLMManager.generate", _fake_generate)
    user, api_key = seed_admin(db_session, api_key="cache-integration-key")
    client = build_api_client(db_session, api_key=api_key)
    init_cache(CacheConfig(enabled=True, backend="memory", ttl_seconds=3600, max_entries=1000))
    client.post("/cache/flush")
    yield client, user
    client.post("/cache/flush")


def _stats(client) -> dict[str, float | int | bool]:
    response = client.get("/cache/stats")
    assert response.status_code == 200, response.text
    payload = response.json()
    raw = payload.get("stats") if isinstance(payload, dict) else {}
    raw = raw if isinstance(raw, dict) else payload
    return {
        "enabled": bool(payload.get("enabled", True)),
        "total_entries": int(raw.get("total_entries", raw.get("entries", 0)) or 0),
        "hits": int(raw.get("hits", 0) or 0),
        "misses": int(raw.get("misses", 0) or 0),
        "hit_rate": float(raw.get("hit_rate", 0.0) or 0.0),
        "memory_usage": int(raw.get("memory_usage", raw.get("memory_bytes", 0)) or 0),
    }


def _generate_prompt(client, title: str, details: str):
    return client.post(
        "/prompts/generate",
        json={
            "title": title,
            "details": details,
            "context_type": "technical",
            "expected_outcomes": "Concrete operational guidance",
            "available_tools": ["search", "summarise"],
        },
    )


class TestCacheIntegration:
    """W28A-413 cache integration scenarios."""
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_miss_first_call(self, cache_client):
        client, _user = cache_client
        assert client.post("/cache/flush").status_code == 200
        assert _stats(client)["total_entries"] == 0

        response = _generate_prompt(
            client,
            "Cache Alpha",
            "Generate a systems prompt for expert alpha with precise diagnostics.",
        )
        assert response.status_code == 200, response.text

        stats = _stats(client)
        assert stats["total_entries"] == 1
        assert stats["hits"] == 0
        assert stats["misses"] == 1
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_hit_repeat_call(self, cache_client):
        client, _user = cache_client

        start_1 = time.perf_counter()
        first = _generate_prompt(
            client,
            "Cache Beta",
            "Generate a systems prompt for expert beta with precise diagnostics.",
        )
        duration_1 = time.perf_counter() - start_1
        assert first.status_code == 200, first.text

        warm_durations: list[float] = []
        for _attempt in range(5):
            start_2 = time.perf_counter()
            second = _generate_prompt(
                client,
                "Cache Beta",
                "Generate a systems prompt for expert beta with precise diagnostics.",
            )
            duration_2 = time.perf_counter() - start_2
            warm_durations.append(duration_2)
            assert second.status_code == 200, second.text
            assert second.json() == first.json()

        stats = _stats(client)
        assert stats["total_entries"] == 1
        assert stats["hits"] >= 3
        assert stats["misses"] >= 1
        assert min(warm_durations) < duration_1, (duration_1, warm_durations)
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_miss_different_parameters(self, cache_client):
        client, _user = cache_client

        first = _generate_prompt(
            client,
            "Cache Gamma",
            "Generate a systems prompt for expert gamma with precise diagnostics.",
        )
        second = _generate_prompt(
            client,
            "Cache Delta",
            "Generate a systems prompt for expert delta with precise diagnostics.",
        )
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["prompt"] != second.json()["prompt"]

        stats = _stats(client)
        assert stats["total_entries"] == 2
        assert stats["hits"] == 0
        assert stats["misses"] == 2
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_expiry(self, cache_client):
        client, _user = cache_client
        init_cache(CacheConfig(enabled=True, backend="memory", ttl_seconds=3600, max_entries=1000))
        client.post("/cache/flush")
        calls = {"count": 0}

        @cached(ttl=2, key_params=("value",))
        async def _ttl_probe(*, value: str):
            calls["count"] += 1
            await asyncio.sleep(0.01)
            return {"value": value, "count": calls["count"]}

        first = asyncio.run(_ttl_probe(value="same"))
        second = asyncio.run(_ttl_probe(value="same"))
        assert first == second

        time.sleep(3)
        third = asyncio.run(_ttl_probe(value="same"))
        assert third["count"] == 2

        stats = _stats(client)
        assert stats["misses"] >= 2
        assert stats["hits"] >= 1
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_invalidation_context_change(self, cache_client):
        client, user = cache_client

        first_write = client.post(
            "/knowledge",
            json={
                "knowledge_type": "user",
                "knowledge_id": int(user.id),
                "content": "Initial knowledge block for cache invalidation",
                "metadata": {"source": "it-cache"},
            },
        )
        assert first_write.status_code == 200, first_write.text

        first_read = client.get(f"/knowledge/user/{int(user.id)}")
        assert first_read.status_code == 200, first_read.text
        stats_after_first_read = _stats(client)
        assert stats_after_first_read["misses"] >= 1

        second_write = client.post(
            "/knowledge",
            json={
                "knowledge_type": "user",
                "knowledge_id": int(user.id),
                "content": "Second knowledge block forces context rebuild",
                "metadata": {"source": "it-cache"},
            },
        )
        assert second_write.status_code == 200, second_write.text

        second_read = client.get(f"/knowledge/user/{int(user.id)}")
        assert second_read.status_code == 200, second_read.text
        stats_after_second_read = _stats(client)
        assert stats_after_second_read["misses"] >= stats_after_first_read["misses"] + 1
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_flush(self, cache_client):
        client, _user = cache_client

        assert _generate_prompt(
            client,
            "Cache Epsilon",
            "Generate a systems prompt for expert epsilon with precise diagnostics.",
        ).status_code == 200
        assert _generate_prompt(
            client,
            "Cache Zeta",
            "Generate a systems prompt for expert zeta with precise diagnostics.",
        ).status_code == 200
        assert _stats(client)["total_entries"] == 2

        flush = client.post("/cache/flush")
        assert flush.status_code == 200, flush.text
        assert _stats(client)["total_entries"] == 0

        again = _generate_prompt(
            client,
            "Cache Epsilon",
            "Generate a systems prompt for expert epsilon with precise diagnostics.",
        )
        assert again.status_code == 200, again.text
        assert _stats(client)["misses"] >= 3
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_stats_endpoint(self, cache_client):
        client, _user = cache_client

        assert _generate_prompt(
            client,
            "Cache Eta",
            "Generate a systems prompt for expert eta with precise diagnostics.",
        ).status_code == 200
        stats = _stats(client)

        assert "total_entries" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "memory_usage" in stats
        assert stats["total_entries"] >= 1
        assert stats["misses"] >= 1
    @pytest.mark.IT
    @pytest.mark.mcp
    @pytest.mark.req("FR-047")

    def test_cache_disabled(self, cache_client):
        client, _user = cache_client
        init_cache(CacheConfig(enabled=False, backend="memory", ttl_seconds=3600, max_entries=1000))
        client.post("/cache/flush")

        start_1 = time.perf_counter()
        first = _generate_prompt(
            client,
            "Cache Theta",
            "Generate a systems prompt for expert theta with precise diagnostics.",
        )
        duration_1 = time.perf_counter() - start_1
        assert first.status_code == 200, first.text

        start_2 = time.perf_counter()
        second = _generate_prompt(
            client,
            "Cache Theta",
            "Generate a systems prompt for expert theta with precise diagnostics.",
        )
        duration_2 = time.perf_counter() - start_2
        assert second.status_code == 200, second.text

        stats = _stats(client)
        assert stats["enabled"] is False
        assert stats["total_entries"] == 0
        assert duration_2 >= duration_1 * 0.7, (duration_1, duration_2)
