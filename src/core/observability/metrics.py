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
Prometheus Metrics

License: Apache 2.0
Ownership: Cloud Dog
Description: Prometheus metrics collection and exposure

Related Requirements: FR1.9
Related Tasks: T040, T100
Related Architecture: MO1.2
Related Tests: ST1.16

Recent Changes:
- Initial implementation
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Global metrics registry
_metrics_registry: Optional[CollectorRegistry] = None

# Metrics
session_counter = None
message_counter = None
request_duration = None
active_sessions = None
queue_depth = None


def setup_metrics(registry: Optional[CollectorRegistry] = None):
    """Setup Prometheus metrics."""
    global \
        _metrics_registry, \
        session_counter, \
        message_counter, \
        request_duration, \
        active_sessions, \
        queue_depth

    _metrics_registry = registry or CollectorRegistry()

    # Counters
    session_counter = Counter(
        "expert_agent_sessions_total",
        "Total number of sessions created",
        registry=_metrics_registry,
    )

    message_counter = Counter(
        "expert_agent_messages_total",
        "Total number of messages processed",
        ["role"],  # user, assistant, system
        registry=_metrics_registry,
    )

    # Histograms
    request_duration = Histogram(
        "expert_agent_request_duration_seconds",
        "Request duration in seconds",
        ["endpoint"],
        registry=_metrics_registry,
    )

    # Gauges
    active_sessions = Gauge(
        "expert_agent_active_sessions", "Number of active sessions", registry=_metrics_registry
    )

    queue_depth = Gauge(
        "expert_agent_queue_depth", "Current queue depth", registry=_metrics_registry
    )

    logger.info("Prometheus metrics initialized")


def get_metrics_registry() -> CollectorRegistry:
    """Get metrics registry."""
    if _metrics_registry is None:
        setup_metrics()
    return _metrics_registry


def get_metrics_output() -> bytes:
    """Get metrics in Prometheus format."""
    registry = get_metrics_registry()
    return generate_latest(registry)
