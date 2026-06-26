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
Analytics Module

License: Apache 2.0
Ownership: Cloud Dog
Description: Channel analytics and metrics

Related Requirements: FR1.22, UC1.17
Related Tasks: T061
Related Architecture: MO1.4.1
Related Tests: AT1.21

Recent Changes:
- Initial implementation
"""

from .manager import AnalyticsManager

__all__ = ["AnalyticsManager"]
