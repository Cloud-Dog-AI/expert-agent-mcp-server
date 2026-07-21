"""Process-wide shared httpx client registry."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from cloud_dog_api_kit.clients import ClientTimeout, create_http_client

_SHARED_ASYNC_CLIENTS: Dict[Tuple[float, str], Any] = {}


def _client_key(timeout: float, verify: Any) -> Tuple[float, str]:
    return (float(timeout), repr(verify))


def get_shared_async_client(timeout: float = 30.0, verify: Any = True) -> Any:
    """Return a reusable Cloud-Dog API-kit client with verified TLS."""
    # Retain the compatibility argument for callers/config files, but never
    # downgrade the platform client's TLS verification.
    key = _client_key(timeout, True)
    client = _SHARED_ASYNC_CLIENTS.get(key)
    if client is None or client.is_closed:
        timeout_seconds = float(timeout)
        client = create_http_client(
            timeout=ClientTimeout(
                connect=min(5.0, timeout_seconds),
                read=timeout_seconds,
                total=timeout_seconds,
            )
        )
        _SHARED_ASYNC_CLIENTS[key] = client
    return client


async def close_shared_async_clients() -> None:
    """Close and clear all shared AsyncClient instances."""
    clients = list(_SHARED_ASYNC_CLIENTS.values())
    _SHARED_ASYNC_CLIENTS.clear()
    for client in clients:
        if not client.is_closed:
            await client.aclose()
