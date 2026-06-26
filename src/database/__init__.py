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
Database Layer

License: Apache 2.0
Ownership: Cloud Dog
Description: Database connection, ORM models, and database utilities

Related Requirements: NF1.8
Related Tasks: T002
Related Architecture: CC6.1.1
Related Tests: ST1.7, ST1.8

Recent Changes:
- Initial implementation
"""

from .connection import get_db, init_db
from .models import Base

__all__ = ["get_db", "init_db", "Base"]
