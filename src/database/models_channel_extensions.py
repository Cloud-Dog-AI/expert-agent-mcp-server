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
Channel Extensions Database Models

License: Apache 2.0
Ownership: Cloud Dog
Description: Extended models for channel-vector-store mappings

Related Requirements: FR1.12, UC1.6
Related Tasks: T050
Related Architecture: CC3.1.3, CC4.1.1
Related Tests: AT1.55, AT1.56, AT1.57

Recent Changes:
- Initial implementation for channel-vector-store mappings
"""

from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from src.database.models import Base


class ChannelVectorStoreMapping(Base):
    """
    Mapping table for channel-to-vector-store relationships.
    Allows channels to have multiple vector stores for RAG.
    """

    __tablename__ = "channel_vector_store_mappings"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vector_store_id = Column(
        Integer, ForeignKey("vector_stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority = Column(Integer, default=0)  # For ordering multiple vector stores
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Ensure unique channel-vector_store pairs
    __table_args__ = (
        UniqueConstraint("channel_id", "vector_store_id", name="uq_channel_vector_store"),
    )


class ChannelServiceMapping(Base):
    """
    Mapping table for channel-to-external-service relationships.
    Enables explicit attach/detach of registry services per channel.
    """

    __tablename__ = "channel_service_mappings"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id = Column(
        Integer, ForeignKey("external_services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("channel_id", "service_id", name="uq_channel_service"),)
