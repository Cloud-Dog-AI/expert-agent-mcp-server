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
Vector Store Integration Module

License: Apache 2.0
Ownership: Cloud Dog
Description: Vector database abstraction and integration

Related Requirements: FR1.3
Related Tasks: T014, T015, T016, T018, T020, T021
Related Architecture: CC4.1.1, CC4.1.2, CC4.1.3
Related Tests: IT2.6, UT1.17, UT1.19, UT1.20, UT1.21, UT1.22, UT1.24

Recent Changes:
- Added lifecycle, isolation, and indexing managers
"""

from .manager import VectorStoreManager
from .providers import VectorStoreProvider, ChromaProvider
from .lifecycle import VectorLifecycleManager
from .isolation import VectorIsolationManager
from .indexing import VectorIndexingManager, IndexFormat, MetadataFieldType

__all__ = [
    "VectorStoreManager",
    "VectorStoreProvider",
    "ChromaProvider",
    "VectorLifecycleManager",
    "VectorIsolationManager",
    "VectorIndexingManager",
    "IndexFormat",
    "MetadataFieldType",
]
