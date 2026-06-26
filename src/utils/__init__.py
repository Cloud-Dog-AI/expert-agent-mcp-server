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
Utility Functions

License: Apache 2.0
Ownership: Cloud Dog
Description: Common utility functions used across the application

Related Requirements: NF1.1
Related Tasks: Various
Related Architecture: Various
Related Tests: Various

Recent Changes:
- Initial implementation
"""

from .logger import setup_logging, get_logger, PIIRedactor

__all__ = ["setup_logging", "get_logger", "PIIRedactor"]
