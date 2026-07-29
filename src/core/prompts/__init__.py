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
Prompt Management Module

License: Apache 2.0
Ownership: Cloud Dog
Description: Prompt generation and management

Related Requirements: FR1.15, FR1.28
Related Tasks: T053, T115
Related Architecture: CC3.1.4
Related Tests: AT1.15, AT1.25

Recent Changes:
- Initial implementation
"""

from .generator import PromptGenerator

__all__ = ["PromptGenerator"]
