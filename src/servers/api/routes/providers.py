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

"""LLM provider + model discovery routes.

Surfaces the configured LLM providers and, for each provider, the models it
exposes so the WebUI Expert form can populate the provider/model pick lists from
live discovery (EXPWEB-017/018/031/032). Backed by the service ``llm`` /
``embeddings`` config plus a live query of the provider endpoint (Ollama
``/api/tags`` for ollama providers). No new persistence — discovery is read-only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from src.config.loader import get_config
from src.servers.api.auth import require_permission

logger = logging.getLogger(__name__)

# Read-only discovery: gated on the same read scope the Experts form already holds.
router = APIRouter(
    prefix="/providers",
    tags=["providers"],
    dependencies=[Depends(require_permission("experts:read"))],
)


def _provider_entries() -> List[Dict[str, Any]]:
    """Enumerate the configured LLM providers (deduplicated by id)."""
    entries: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(pid: str, name: str, ptype: str, base_url: Optional[str], primary: bool) -> None:
        key = pid.lower()
        if not key or key in seen:
            return
        seen.add(key)
        entries.append(
            {
                "id": pid,
                "name": name,
                "type": ptype,
                "base_url": str(base_url or ""),
                "is_primary": primary,
            }
        )

    # Primary chat LLM (config `llm.*` / `expert.llm.*`).
    llm_provider = str(get_config("llm.provider") or get_config("expert.llm.provider") or "").strip()
    llm_base = get_config("llm.base_url") or get_config("expert.llm.base_url")
    if llm_provider:
        add(llm_provider, llm_provider.capitalize(), llm_provider, llm_base, True)

    # Embeddings provider (config `embeddings.*`).
    emb_provider = str(get_config("embeddings.provider") or get_config("expert.embeddings.provider") or "").strip()
    emb_base = get_config("embeddings.base_url") or get_config("expert.embeddings.base_url")
    if emb_provider:
        add(emb_provider, emb_provider.capitalize(), emb_provider, emb_base, False)

    # Always advertise the common providers the Expert form supports so the pick
    # list is never empty even before a base_url is configured.
    add("ollama", "Ollama", "ollama", llm_base if llm_provider == "ollama" else None, False)
    add("openai", "OpenAI", "openai", None, False)

    return entries


def _find_provider(provider_id: str) -> Optional[Dict[str, Any]]:
    key = str(provider_id or "").strip().lower()
    for entry in _provider_entries():
        if entry["id"].lower() == key or entry["type"].lower() == key:
            return entry
    return None


async def _ollama_models(base_url: str) -> List[Dict[str, Any]]:
    """Query an Ollama endpoint's ``/api/tags`` and normalise to ProviderModelRecord."""
    url = base_url.rstrip("/") + "/api/tags"
    async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
    models: List[Dict[str, Any]] = []
    for item in payload.get("models", []) or []:
        name = str(item.get("name") or item.get("model") or "").strip()
        if not name:
            continue
        details = item.get("details") or {}
        models.append(
            {
                "id": name,
                "name": name,
                "parameter_size": details.get("parameter_size"),
                "family": details.get("family"),
                "quantization": details.get("quantization_level"),
                "format": details.get("format"),
            }
        )
    return models


@router.get("")
async def list_providers() -> List[Dict[str, Any]]:
    """List the configured LLM providers."""
    return _provider_entries()


@router.get("/{provider_id}/models")
async def list_provider_models(provider_id: str) -> List[Dict[str, Any]]:
    """List the models a provider exposes via live discovery.

    Unknown or unreachable providers return an empty list rather than a 5xx so the
    WebUI can degrade gracefully (the form falls back to free-text entry).
    """
    provider = _find_provider(provider_id)
    ptype = (provider or {}).get("type", str(provider_id or "").lower())
    base_url = str((provider or {}).get("base_url") or "").strip()

    if ptype == "ollama" and base_url:
        try:
            return await _ollama_models(base_url)
        except Exception as exc:  # pragma: no cover - network/endpoint variance
            logger.warning("provider model discovery failed for %s (%s): %s", provider_id, base_url, exc)
            return []

    # No live discovery available for this provider (e.g. openai without a
    # catalogue endpoint, or no configured base_url) — return empty.
    return []
