"""Authoritative per-execution timeout contract helpers.

Long-running expert requests carry their own ``max_wall_time_seconds`` budget.
Async API/MCP wrappers must preserve that value instead of silently replacing
it with a process default while the transactional worker receives a different
budget.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


def positive_timeout_seconds(value: Any, *, field_name: str) -> float:
    """Return a finite positive timeout or fail closed with a useful error."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive number")
    try:
        timeout_seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive number") from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return timeout_seconds


def resolve_execution_timeout_seconds(
    parameters: Mapping[str, Any] | None,
    *,
    configured_timeout_seconds: Any,
) -> float:
    """Resolve the worker wrapper timeout without clipping an explicit budget."""
    configured = positive_timeout_seconds(
        configured_timeout_seconds,
        field_name="configured async execution timeout",
    )
    if not isinstance(parameters, Mapping) or "max_wall_time_seconds" not in parameters:
        return configured
    return positive_timeout_seconds(
        parameters["max_wall_time_seconds"],
        field_name="max_wall_time_seconds",
    )
