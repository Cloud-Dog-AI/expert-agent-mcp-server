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
Expert Agent MCP Server - Configuration Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Configuration management system with hierarchy support (env vars, .env, config.yaml, defaults.yaml)

Related Requirements: NF1.5, FR1.1
Related Tasks: T003, T110
Related Architecture: CM1.1
Related Tests: UT1.32, ST1.1

Recent Changes:
- Initial implementation
"""

from .loader import ConfigLoader, get_config
from .models import AppConfig, ServerConfig, LLMConfig, DatabaseConfig

__all__ = [
    "ConfigLoader",
    "get_config",
    "AppConfig",
    "ServerConfig",
    "LLMConfig",
    "DatabaseConfig",
]
