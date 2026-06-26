"""Process-wide shared httpx client registry."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import httpx

_SHARED_ASYNC_CLIENTS: Dict[Tuple[float, str], httpx.AsyncClient] = {}


def _client_key(timeout: float, verify: Any) -> Tuple[float, str]:
    return (float(timeout), repr(verify))


def get_shared_async_client(timeout: float = 30.0, verify: Any = True) -> httpx.AsyncClient:
    """Return a reusable AsyncClient for the requested transport settings."""
    key = _client_key(timeout, verify)
    client = _SHARED_ASYNC_CLIENTS.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=float(timeout), verify=verify)
        _SHARED_ASYNC_CLIENTS[key] = client
    return client


async def close_shared_async_clients() -> None:
    """Close and clear all shared AsyncClient instances."""
    clients = list(_SHARED_ASYNC_CLIENTS.values())
    _SHARED_ASYNC_CLIENTS.clear()
    for client in clients:
        if not client.is_closed:
            await client.aclose()
