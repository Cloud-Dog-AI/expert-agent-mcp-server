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
Channel Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages channel-based experts

Related Requirements: FR1.12, UC1.6
Related Tasks: T050
Related Architecture: CC3.1.3
Related Tests: AT1.13

Recent Changes:
- Initial implementation
"""

import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from src.database.models import (
    Channel,
    ExpertConfig,
    ExternalService,
    VectorStore,
    Message,
    Session as SessionModel,
)
from src.database.connection import get_db
from src.core.job.callbacks import CallbackManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChannelManager:
    """Manages channel-based experts."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize channel manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self.callback_manager = CallbackManager()

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def create_channel(
        self,
        name: str,
        expert_config_id: Optional[int] = None,
        description: Optional[str] = None,
        context_type: Optional[str] = None,
        expected_outcomes: Optional[str] = None,
        history_scope: Optional[str] = None,  # user, channel, session
        history_limitation: Optional[Dict[str, Any]] = None,
        rerank_model: Optional[str] = None,
        enabled: bool = True,
        access_control: Optional[Dict[str, Any]] = None,
    ) -> Channel:
        """
        Create a new channel.

        Args:
            name: Channel name (unique)
            expert_config_id: Expert configuration ID
            description: Channel description
            context_type: Context type
            expected_outcomes: Expected outcomes description
            history_scope: History sharing scope (user, channel, session)
            history_limitation: History limitation settings
            rerank_model: Rerank model name
            enabled: Whether channel is enabled
            access_control: Access control settings

        Returns:
            Created channel
        """
        db = self._get_db()
        try:
            # Check if channel exists
            existing = db.query(Channel).filter(Channel.name == name).first()
            if existing:
                raise ValueError(f"Channel '{name}' already exists")

            channel = Channel(
                name=name,
                expert_config_id=expert_config_id,
                description=description,
                context_type=context_type,
                expected_outcomes=expected_outcomes,
                history_scope=history_scope,
                history_limitation_json=json.dumps(history_limitation)
                if history_limitation
                else None,
                rerank_model=rerank_model,
                enabled=enabled,
                access_control_json=json.dumps(access_control) if access_control else None,
            )
            db.add(channel)
            db.commit()
            db.refresh(channel)

            logger.info(f"Created channel: {name}")
            return channel
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create channel: {e}", exc_info=True)
            raise

    def get_channel(
        self, channel_id: Optional[int] = None, name: Optional[str] = None
    ) -> Optional[Channel]:
        """Get channel by ID or name."""
        db = self._get_db()
        if channel_id:
            return db.query(Channel).filter(Channel.id == channel_id).first()
        elif name:
            return db.query(Channel).filter(Channel.name == name).first()
        return None

    def update_channel(
        self,
        channel_id: int,
        *,
        name: Optional[str] = None,
        expert_config_id: Optional[int] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Channel:
        """Update an existing channel."""
        db = self._get_db()
        try:
            channel = self.get_channel(channel_id=channel_id)
            if channel is None:
                raise ValueError("Channel not found")

            if name is not None:
                candidate = name.strip()
                if not candidate:
                    raise ValueError("Channel name cannot be empty")
                existing = db.query(Channel).filter(Channel.name == candidate, Channel.id != channel_id).first()
                if existing is not None:
                    raise ValueError(f"Channel '{candidate}' already exists")
                channel.name = candidate

            if expert_config_id is not None:
                expert = db.query(ExpertConfig).filter(ExpertConfig.id == expert_config_id).first()
                if expert is None:
                    raise ValueError("Expert configuration not found")
                channel.expert_config_id = expert_config_id

            if description is not None:
                channel.description = description

            if enabled is not None:
                channel.enabled = enabled

            db.add(channel)
            db.commit()
            db.refresh(channel)
            return channel
        except Exception:
            db.rollback()
            raise

    def list_channels(self, enabled_only: bool = False) -> List[Channel]:
        """List all channels."""
        db = self._get_db()
        query = db.query(Channel)
        if enabled_only:
            query = query.filter(Channel.enabled)
        return query.all()

    def get_channel_llm_config(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """
        Get LLM configuration for a channel.

        Args:
            channel_id: Channel ID

        Returns:
            LLM configuration dict
        """
        channel = self.get_channel(channel_id=channel_id)
        if not channel or not channel.expert_config_id:
            return None

        db = self._get_db()
        expert = db.query(ExpertConfig).filter(ExpertConfig.id == channel.expert_config_id).first()
        if not expert:
            return None

        llm_params = json.loads(expert.llm_params_json) if expert.llm_params_json else {}

        return {
            "provider": expert.llm_provider,
            "model": expert.llm_model,
            # Backward compatibility: older payloads may store `llm_base_url`.
            "base_url": llm_params.get("base_url") or llm_params.get("llm_base_url"),
            "api_key": llm_params.get("api_key"),
            "temperature": llm_params.get("temperature", 0.7),
            "max_tokens": llm_params.get("max_tokens", 1024),
            "timeout": llm_params.get("timeout", 300),
        }

    def get_channel_history(
        self,
        channel_id: int,
        scope: str = "channel",
        user_id: Optional[int] = None,
        session_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get channel history based on scope.

        Args:
            channel_id: Channel ID
            scope: History scope (user, channel, session)
            user_id: User ID (required for user scope)
            session_id: Session ID (required for session scope)
            limit: Maximum number of messages
            offset: Offset for pagination

        Returns:
            Dictionary with messages and metadata
        """
        db = self._get_db()
        channel = self.get_channel(channel_id=channel_id)
        if not channel:
            return {"messages": [], "count": 0, "scope": scope}

        # Build query based on scope
        query = db.query(Message).join(SessionModel)

        if scope == "user" and user_id:
            # Get all messages from this user in this channel
            query = query.filter(SessionModel.user_id == user_id)
        elif scope == "session" and session_id:
            # Get messages from specific session
            query = query.filter(Message.session_id == session_id)
        elif scope == "channel":
            # Get all messages from all sessions in this channel
            # For now, we'll use jobs to track channel association
            from src.database.models import Job

            session_ids = (
                db.query(Job.session_id)
                .filter(Job.channel_id == channel_id, Job.session_id.isnot(None))
                .distinct()
                .all()
            )
            session_ids = [sid[0] for sid in session_ids]
            if session_ids:
                query = query.filter(Message.session_id.in_(session_ids))
            else:
                return {
                    "messages": [],
                    "count": 0,
                    "limit": limit,
                    "offset": offset,
                    "scope": scope,
                }
        else:
            return {"messages": [], "count": 0, "limit": limit, "offset": offset, "scope": scope}

        # Get total count
        total_count = query.count()

        # Apply pagination and ordering
        messages = query.order_by(Message.timestamp.desc()).limit(limit).offset(offset).all()

        return {
            "messages": [
                {
                    "id": m.id,
                    "session_id": m.session_id,
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                }
                for m in messages
            ],
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "scope": scope,
        }

    def add_vector_store_mapping(
        self, channel_id: int, vector_store_id: int, priority: int = 0
    ) -> Dict[str, Any]:
        """
        Map a vector store to a channel.

        Args:
            channel_id: Channel ID
            vector_store_id: Vector store ID
            priority: Priority for ordering (higher = higher priority)

        Returns:
            Mapping details
        """
        db = self._get_db()

        # Verify channel exists
        channel = self.get_channel(channel_id=channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        # Verify vector store exists
        vs = db.query(VectorStore).filter(VectorStore.id == vector_store_id).first()
        if not vs:
            raise ValueError(f"Vector store {vector_store_id} not found")

        # Import here to avoid circular dependency
        from src.database.models_channel_extensions import ChannelVectorStoreMapping

        # Check if mapping already exists
        existing = (
            db.query(ChannelVectorStoreMapping)
            .filter(
                ChannelVectorStoreMapping.channel_id == channel_id,
                ChannelVectorStoreMapping.vector_store_id == vector_store_id,
            )
            .first()
        )

        if existing:
            raise ValueError(
                f"Mapping already exists between channel {channel_id} and vector store {vector_store_id}"
            )

        # Create mapping
        mapping = ChannelVectorStoreMapping(
            channel_id=channel_id, vector_store_id=vector_store_id, priority=priority
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        logger.info(
            f"Created channel-vector-store mapping: channel={channel_id}, vs={vector_store_id}"
        )

        return {
            "id": mapping.id,
            "channel_id": mapping.channel_id,
            "vector_store_id": mapping.vector_store_id,
            "priority": mapping.priority,
            "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
        }

    def get_channel_vector_stores(self, channel_id: int) -> List[Dict[str, Any]]:
        """
        Get all vector stores mapped to a channel.

        Args:
            channel_id: Channel ID

        Returns:
            List of vector store mappings
        """
        db = self._get_db()

        # Import here to avoid circular dependency
        from src.database.models_channel_extensions import ChannelVectorStoreMapping

        mappings = (
            db.query(ChannelVectorStoreMapping)
            .filter(ChannelVectorStoreMapping.channel_id == channel_id)
            .order_by(ChannelVectorStoreMapping.priority.desc())
            .all()
        )

        result = []
        for mapping in mappings:
            vs = db.query(VectorStore).filter(VectorStore.id == mapping.vector_store_id).first()
            if vs:
                result.append(
                    {
                        "mapping_id": mapping.id,
                        "vector_store_id": vs.id,
                        "vector_store_name": vs.name,
                        "vector_store_type": vs.type,
                        "priority": mapping.priority,
                        "enabled": vs.enabled,
                    }
                )

        return result

    def remove_vector_store_mapping(self, channel_id: int, vector_store_id: int) -> bool:
        """
        Remove vector store mapping from channel.

        Args:
            channel_id: Channel ID
            vector_store_id: Vector store ID

        Returns:
            True if deleted, False if not found
        """
        db = self._get_db()

        # Import here to avoid circular dependency
        from src.database.models_channel_extensions import ChannelVectorStoreMapping

        mapping = (
            db.query(ChannelVectorStoreMapping)
            .filter(
                ChannelVectorStoreMapping.channel_id == channel_id,
                ChannelVectorStoreMapping.vector_store_id == vector_store_id,
            )
            .first()
        )

        if not mapping:
            return False

        db.delete(mapping)
        db.commit()

        logger.info(
            f"Removed channel-vector-store mapping: channel={channel_id}, vs={vector_store_id}"
        )
        return True

    def get_channel_tools(self, channel_id: int) -> List[str]:
        """
        List tool definitions associated with a channel via its expert config.
        """
        channel = self.get_channel(channel_id=channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")
        if not channel.expert_config_id:
            return []

        db = self._get_db()
        expert = db.query(ExpertConfig).filter(ExpertConfig.id == channel.expert_config_id).first()
        if not expert or not expert.tools_json:
            return []
        try:
            tools = json.loads(expert.tools_json)
            if not isinstance(tools, list):
                return []
            return [str(tool) for tool in tools]
        except Exception:
            return []

    def remove_channel_tool(self, channel_id: int, tool_name: str) -> bool:
        """
        Remove a tool definition from a channel's backing expert config.
        """
        channel = self.get_channel(channel_id=channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")
        if not channel.expert_config_id:
            return False

        db = self._get_db()
        expert = db.query(ExpertConfig).filter(ExpertConfig.id == channel.expert_config_id).first()
        if not expert:
            return False

        current_tools: List[str] = []
        if expert.tools_json:
            try:
                loaded = json.loads(expert.tools_json)
                if isinstance(loaded, list):
                    current_tools = [str(tool) for tool in loaded]
            except Exception:
                current_tools = []

        if tool_name not in current_tools:
            return False

        expert.tools_json = json.dumps([tool for tool in current_tools if tool != tool_name])
        db.commit()
        return True

    def attach_service_to_channel(self, channel_id: int, service_id: int) -> Dict[str, Any]:
        """
        Attach an existing external service to a channel.
        """
        db = self._get_db()
        channel = self.get_channel(channel_id=channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
        if not service:
            raise ValueError(f"Service {service_id} not found")

        from src.database.models_channel_extensions import ChannelServiceMapping

        existing = (
            db.query(ChannelServiceMapping)
            .filter(
                ChannelServiceMapping.channel_id == channel_id,
                ChannelServiceMapping.service_id == service_id,
            )
            .first()
        )
        if existing:
            raise ValueError(f"Service {service_id} already attached to channel {channel_id}")

        mapping = ChannelServiceMapping(channel_id=channel_id, service_id=service_id)
        db.add(mapping)
        db.commit()
        db.refresh(mapping)
        return {
            "id": mapping.id,
            "channel_id": mapping.channel_id,
            "service_id": mapping.service_id,
            "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
        }

    def get_channel_services(self, channel_id: int) -> List[Dict[str, Any]]:
        """
        List external services attached to a channel.
        """
        db = self._get_db()
        channel = self.get_channel(channel_id=channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        from src.database.models_channel_extensions import ChannelServiceMapping

        mappings = (
            db.query(ChannelServiceMapping)
            .filter(ChannelServiceMapping.channel_id == channel_id)
            .order_by(ChannelServiceMapping.id.asc())
            .all()
        )

        results: List[Dict[str, Any]] = []
        for mapping in mappings:
            service = db.query(ExternalService).filter(ExternalService.id == mapping.service_id).first()
            if not service:
                continue
            results.append(
                {
                    "mapping_id": mapping.id,
                    "service_id": service.id,
                    "name": service.name,
                    "service_type": service.type,
                    "endpoint_url": service.endpoint_url,
                    "health_status": service.health_status,
                }
            )
        return results

    def detach_service_from_channel(self, channel_id: int, service_id: int) -> bool:
        """
        Detach an external service from a channel.
        """
        db = self._get_db()
        from src.database.models_channel_extensions import ChannelServiceMapping

        mapping = (
            db.query(ChannelServiceMapping)
            .filter(
                ChannelServiceMapping.channel_id == channel_id,
                ChannelServiceMapping.service_id == service_id,
            )
            .first()
        )
        if not mapping:
            return False

        db.delete(mapping)
        db.commit()
        return True
