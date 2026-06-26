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
Expert Configuration Models

License: Apache 2.0
Ownership: Cloud Dog
Description: Expert configuration data models

Related Requirements: FR1.1
Related Tasks: T007
Related Architecture: CC3.1.1
Related Tests: IT2.4

Recent Changes:
- Initial implementation
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class ExpertConfig(BaseModel):
    """Expert configuration model."""

    name: str
    title: str
    description: Optional[str] = None
    llm_provider: str
    llm_model: str
    llm_params: Optional[Dict[str, Any]] = None
    prompt_template: Optional[str] = None
    tools: Optional[List[str]] = None
    enabled: bool = True
    access_control: Optional[Dict[str, Any]] = None
