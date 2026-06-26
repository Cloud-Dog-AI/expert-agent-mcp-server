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
Reliability Module

License: Apache 2.0
Ownership: Cloud Dog
Description: Rate limiting, circuit breaker, backoff, and TTL handling

Related Requirements: FR1.9
Related Tasks: T096-T100
Related Architecture: RR1.1, RR1.2, RR1.3
Related Tests: ST1.16

Recent Changes:
- Initial implementation
"""

from .rate_limiter import RateLimiter
from .circuit_breaker import CircuitBreaker
from .backoff import BackoffManager
from .ttl import TTLHandler

__all__ = ["RateLimiter", "CircuitBreaker", "BackoffManager", "TTLHandler"]
