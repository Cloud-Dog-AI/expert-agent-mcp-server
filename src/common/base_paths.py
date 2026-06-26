"""Shared helpers for configurable server route prefixes."""

from __future__ import annotations

from typing import Any

SURFACE_BASE_PATH_DEFAULTS: dict[str, str] = {
    "api": "/v1",
    "web": "",
    "mcp": "/mcp",
    "a2a": "/a2a",
}


def normalise_base_path(value: object, *, default: str = "") -> str:
    """Return a normalised URL prefix with a leading slash and no trailing slash."""
    resolved = str(value or "").strip() or str(default or "").strip()
    if resolved in {"", "/"}:
        return ""
    return "/" + resolved.strip("/")


def configured_base_path(config: Any, surface: str) -> str:
    """Return the configured base path for one server surface."""
    default = SURFACE_BASE_PATH_DEFAULTS.get(surface, "")
    getter = getattr(config, "get", None)
    if callable(getter):
        return normalise_base_path(getter(f"{surface}_server.base_path", default), default=default)
    return normalise_base_path(default, default=default)


def join_route(base_path: str, suffix: str = "") -> str:
    """Join a base path and route fragment into one absolute URL path."""
    prefix = normalise_base_path(base_path)
    tail = str(suffix or "").strip()
    if tail in {"", "/"}:
        return prefix or "/"
    if not tail.startswith("/"):
        tail = f"/{tail}"
    return f"{prefix}{tail}" if prefix else tail
