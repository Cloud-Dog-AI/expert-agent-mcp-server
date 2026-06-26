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
LLM Integration Module

License: Apache 2.0
Ownership: Cloud Dog
Description: LLM provider abstraction and integration

Related Requirements: FR1.1, FR1.12
Related Tasks: T007, T008, T056
Related Architecture: CC3.1.2, IP1.1.1, IP1.1.4
Related Tests: IT2.4, UT1.8

Recent Changes:
- Initial implementation
"""

from .manager import LLMManager
from .providers import LLMProvider, OllamaProvider, OpenAIProvider, OpenRouterProvider

__all__ = ["LLMManager", "LLMProvider", "OllamaProvider", "OpenAIProvider", "OpenRouterProvider"]
