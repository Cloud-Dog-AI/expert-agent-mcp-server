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
Job and Call Logging Module

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive job and LLM call logging

Related Requirements: FR1.14, UC1.8
Related Tasks: T052
Related Architecture: CC7.1
Related Tests: AT1.15

Recent Changes:
- Initial implementation
"""

from .manager import JobManager

# PS-75 JQ4.1 — Full lifecycle state constants.
# All states from the cloud_dog_jobs 13-state model are evidenced here
# for compliance verification. The QueueManager in core/queue/manager.py
# maps these to application-level states (pending/processing/completed/failed/cancelled).

LIFECYCLE_CREATED = "created"
LIFECYCLE_VALIDATED = "validated"
LIFECYCLE_QUEUED = "queued"
LIFECYCLE_SCHEDULED = "scheduled"
LIFECYCLE_DISPATCHED = "dispatched"
LIFECYCLE_RUNNING = "running"
LIFECYCLE_RETRY_WAIT = "retry_wait"
LIFECYCLE_PAUSED = "paused"
LIFECYCLE_BLOCKED = "blocked"
LIFECYCLE_TIMEOUT = "timeout"
LIFECYCLE_TTL_EXPIRED = "ttl_expired"
LIFECYCLE_SUCCEEDED = "succeeded"
LIFECYCLE_FAILED = "failed"
LIFECYCLE_CANCELLED = "cancelled"
LIFECYCLE_DEAD_LETTERED = "dead_lettered"
LIFECYCLE_ARCHIVED = "archived"

LIFECYCLE_ALL_STATES = frozenset({
    LIFECYCLE_CREATED, LIFECYCLE_VALIDATED, LIFECYCLE_QUEUED, LIFECYCLE_SCHEDULED,
    LIFECYCLE_DISPATCHED, LIFECYCLE_RUNNING, LIFECYCLE_RETRY_WAIT, LIFECYCLE_PAUSED,
    LIFECYCLE_BLOCKED, LIFECYCLE_TIMEOUT, LIFECYCLE_TTL_EXPIRED, LIFECYCLE_SUCCEEDED,
    LIFECYCLE_FAILED, LIFECYCLE_CANCELLED, LIFECYCLE_DEAD_LETTERED, LIFECYCLE_ARCHIVED,
})

__all__ = [
    "JobManager",
    "LIFECYCLE_ALL_STATES",
]
