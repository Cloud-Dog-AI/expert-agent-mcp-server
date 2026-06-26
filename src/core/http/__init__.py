"""Shared HTTP client utilities."""

from .client import close_shared_async_clients, get_shared_async_client

__all__ = ["close_shared_async_clients", "get_shared_async_client"]
