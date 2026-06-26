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
Channel Management Module

License: Apache 2.0
Ownership: Cloud Dog
Description: Channel-based expert system

Related Requirements: FR1.12, UC1.6
Related Tasks: T050
Related Architecture: CC3.1.3
Related Tests: AT1.13

Recent Changes:
- Initial implementation
"""

from .manager import ChannelManager

__all__ = ["ChannelManager"]
