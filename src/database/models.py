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
Database ORM Models

License: Apache 2.0
Ownership: Cloud Dog
Description: SQLAlchemy ORM models for all database tables

Related Requirements: NF1.8, FR1.1, FR1.12, FR1.14, FR1.17
Related Tasks: T002
Related Architecture: DM1.1, CC6.1.1
Related Tests: ST1.7, ST1.8

Recent Changes:
- Initial implementation
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from cloud_dog_db.models import PlatformBase as Base


class UserEntity(Base):
    """User entity model — auth decisions delegated to cloud_dog_idam.rbac.RBACEngine."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    pwd_hash = Column(String(255), nullable=True)
    role = Column(String(50), default="user")
    user_type = Column(String(50), default="local")
    language = Column(String(10), default="en")
    timezone = Column(String(50), default="UTC")
    enabled = Column(Boolean, default=True)
    external_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    sessions = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    api_keys = relationship("APIKeyEntity", back_populates="user", cascade="all, delete-orphan")


User = UserEntity  # Backward-compatible alias


class GroupEntity(Base):
    """Group entity model — auth decisions delegated to cloud_dog_idam.rbac.RBACEngine."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    api_keys = relationship("APIKeyEntity", back_populates="group", cascade="all, delete-orphan")


Group = GroupEntity  # Backward-compatible alias


class GroupMember(Base):
    """Group membership model."""

    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="member")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    group = relationship("GroupEntity", back_populates="members")
    user = relationship("UserEntity")


class ExpertConfig(Base):
    """Expert configuration model."""

    __tablename__ = "expert_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    llm_provider = Column(String(100), nullable=False)
    llm_model = Column(String(255), nullable=False)
    llm_params_json = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=True)
    tools_json = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    access_control_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    sessions = relationship("Session", back_populates="expert_config", cascade="all, delete-orphan")
    channels = relationship("Channel", back_populates="expert_config", cascade="all, delete-orphan")
    service_bindings = relationship(
        "ServiceBinding",
        foreign_keys="ServiceBinding.expert_config_id",
        back_populates="expert_config",
        cascade="all, delete-orphan",
    )
    sub_expert_bindings = relationship(
        "SubExpertBinding",
        foreign_keys="SubExpertBinding.parent_expert_id",
        back_populates="parent_expert",
        cascade="all, delete-orphan",
    )
    assigned_as_sub_expert = relationship(
        "SubExpertBinding",
        foreign_keys="SubExpertBinding.child_expert_id",
        back_populates="child_expert",
        cascade="all, delete-orphan",
    )
    prompt_assignments = relationship(
        "ExpertPromptAssignment", back_populates="expert_config", cascade="all, delete-orphan"
    )


class Session(Base):
    """Session model."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expert_config_id = Column(
        Integer, ForeignKey("expert_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_session_id = Column(
        Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title = Column(String(255), nullable=True)
    status = Column(String(50), default="active")
    context_window = Column(Integer, default=4096)
    history_retention_days = Column(Integer, default=30)
    # AT1.11: Session key and history key support
    session_key = Column(String(255), nullable=True, unique=True, index=True)
    history_key = Column(String(255), nullable=True, index=True)
    shared_with_user_ids = Column(Text, nullable=True)  # JSON array of user IDs
    shared_with_group_ids = Column(Text, nullable=True)  # JSON array of group IDs
    session_key_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("UserEntity", back_populates="sessions")
    expert_config = relationship("ExpertConfig", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="session", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="session", cascade="all, delete-orphan")
    parent_session = relationship("Session", remote_side=[id], back_populates="child_sessions")
    child_sessions = relationship("Session", back_populates="parent_session")
    service_invocation_logs = relationship(
        "ServiceInvocationLog", back_populates="session", cascade="all, delete-orphan"
    )


class Summary(Base):
    """Summary model for context summarization (AT1.11)."""

    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary_text = Column(Text, nullable=False)
    original_message_count = Column(Integer, nullable=False)
    preserved_message_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("Session", back_populates="summaries")


class Message(Base):
    """Message model."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    tokens_used = Column(Integer, nullable=True)
    embedding_id = Column(String(255), nullable=True)
    metadata_json = Column(Text, nullable=True)

    # Relationships
    session = relationship("Session", back_populates="messages")


class VectorStore(Base):
    """Vector store model."""

    __tablename__ = "vector_stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    type = Column(String(100), nullable=False)
    config_json = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    access_control_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Channel(Base):
    """Channel model (UC1.6)."""

    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    expert_config_id = Column(
        Integer, ForeignKey("expert_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    description = Column(Text, nullable=True)
    context_type = Column(String(100), nullable=True)
    expected_outcomes = Column(Text, nullable=True)
    history_scope = Column(String(50), nullable=True)  # user, channel, session
    history_limitation_json = Column(Text, nullable=True)
    rerank_model = Column(String(255), nullable=True)
    enabled = Column(Boolean, default=True)
    access_control_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    expert_config = relationship("ExpertConfig", back_populates="channels")
    jobs = relationship("Job", back_populates="channel", cascade="all, delete-orphan")


class Job(Base):
    """Job model (UC1.8)."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(100), nullable=False)
    session_id = Column(
        Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    channel_id = Column(
        Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status = Column(String(50), default="pending", index=True)
    prompt_sent = Column(Text, nullable=True)
    response_received = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    performance_metrics_json = Column(Text, nullable=True)
    vector_context_json = Column(Text, nullable=True)
    tool_calls_json = Column(Text, nullable=True)
    error_info_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    session = relationship("Session", back_populates="jobs")
    channel = relationship("Channel", back_populates="jobs")
    call_logs = relationship("CallLog", back_populates="job", cascade="all, delete-orphan")


class CallLog(Base):
    """Call log model (UC1.8)."""

    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    llm_provider = Column(String(100), nullable=True)
    llm_model = Column(String(255), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job = relationship("Job", back_populates="call_logs")


class Tool(Base):
    """Tool model (UC1.10)."""

    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    input_schema_json = Column(Text, nullable=True)
    output_schema_json = Column(Text, nullable=True)
    auth_requirements_json = Column(Text, nullable=True)
    usage_guidelines = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class APIKeyEntity(Base):
    """API key entity model (UC1.11) — hashing via cloud_dog_idam.api_keys."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name = Column(String(255), nullable=True)
    scopes_json = Column(Text, nullable=True)
    read_channels = Column(Boolean, default=False)
    write_channels = Column(Boolean, default=False)
    read_logs = Column(Boolean, default=False)
    write_logs = Column(Boolean, default=False)
    read_histories = Column(Boolean, default=False)
    write_histories = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("UserEntity", back_populates="api_keys")
    group = relationship("GroupEntity", back_populates="api_keys")


APIKey = APIKeyEntity  # Backward-compatible alias


class ExternalService(Base):
    """External service model (UC1.13)."""

    __tablename__ = "external_services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    type = Column(String(100), nullable=False)  # mcp, a2a
    endpoint_url = Column(String(500), nullable=False)
    auth_config_json = Column(Text, nullable=True)
    health_status = Column(String(50), default="unknown")
    # EA5 (W28C-1704): the external_services.enabled column (migration 006, NOT NULL,
    # server_default dropped after backfill) was missing from this model, so inserts
    # omitted it and raised a NOT-NULL IntegrityError. Map it with an ORM default.
    enabled = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(Text, nullable=True)
    usage_statistics_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    service_bindings = relationship("ServiceBinding", back_populates="service")
    invocation_logs = relationship("ServiceInvocationLog", back_populates="service")


class ServiceBinding(Base):
    """Expert to external-service binding for orchestration."""

    __tablename__ = "service_bindings"

    id = Column(Integer, primary_key=True, index=True)
    expert_config_id = Column(
        Integer, ForeignKey("expert_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id = Column(
        Integer, ForeignKey("external_services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enabled = Column(Boolean, default=True, nullable=False)
    timeout_seconds = Column(Integer, nullable=True)
    priority = Column(Integer, default=100, nullable=False)
    circuit_breaker_threshold = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    expert_config = relationship("ExpertConfig", back_populates="service_bindings")
    service = relationship("ExternalService", back_populates="service_bindings")


class SubExpertBinding(Base):
    """Parent-to-child expert delegation binding."""

    __tablename__ = "sub_expert_bindings"

    id = Column(Integer, primary_key=True, index=True)
    parent_expert_id = Column(
        Integer, ForeignKey("expert_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_expert_id = Column(
        Integer, ForeignKey("expert_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enabled = Column(Boolean, default=True, nullable=False)
    max_depth = Column(Integer, default=3, nullable=False)
    delegation_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    parent_expert = relationship(
        "ExpertConfig",
        foreign_keys=[parent_expert_id],
        back_populates="sub_expert_bindings",
    )
    child_expert = relationship(
        "ExpertConfig",
        foreign_keys=[child_expert_id],
        back_populates="assigned_as_sub_expert",
    )


class PromptTemplate(Base):
    """Reusable, versioned prompt template.

    W28B-319 (D5) mapping to the shared ``cloud_dog_agent.prompts.PromptTemplate``
    /``PromptVersion`` models (used by the optional opt-in PromptManager store
    path; see ``src/core/prompt/manager.py``):

    - ``name``    <-> shared ``PromptTemplate.name`` (the store's natural key)
    - ``version`` <-> shared ``PromptVersion.version`` (store owns immutable
      version history; each content edit appends a new version)
    - ``content`` <-> shared ``PromptVersion.body``
    - ``variables_schema`` carries the declared variable set; the store records
      variables on ``PromptVersion.variables`` and the schema dict under
      ``PromptTemplate.metadata['variables_schema']``
    - ``created_by`` <-> shared ``PromptVersion.created_by`` /
      ``PromptTemplate.metadata['created_by']``

    The service columns are kept as-is (no schema change) so existing flows are
    untouched; the shared store is consulted only when explicitly injected.
    """

    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    content = Column(Text, nullable=False)
    variables_schema = Column(Text, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assignments = relationship(
        "ExpertPromptAssignment", back_populates="prompt_template", cascade="all, delete-orphan"
    )


class ExpertPromptAssignment(Base):
    """Assign a prompt template to an expert."""

    __tablename__ = "expert_prompt_assignments"

    id = Column(Integer, primary_key=True, index=True)
    expert_config_id = Column(
        Integer, ForeignKey("expert_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt_template_id = Column(
        Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_active = Column(Boolean, default=True, nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    expert_config = relationship("ExpertConfig", back_populates="prompt_assignments")
    prompt_template = relationship("PromptTemplate", back_populates="assignments")


class ServiceInvocationLog(Base):
    """Audit trail for external service calls."""

    __tablename__ = "service_invocation_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    service_id = Column(
        Integer, ForeignKey("external_services.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tool_name = Column(String(255), nullable=False)
    request_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    response_status = Column(String(50), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    request_payload_json = Column(Text, nullable=True)
    response_payload_json = Column(Text, nullable=True)

    session = relationship("Session", back_populates="service_invocation_logs")
    service = relationship("ExternalService", back_populates="invocation_logs")


class MultimediaFile(Base):
    """Multimedia file model (UC1.7)."""

    __tablename__ = "multimedia_files"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    file_type = Column(String(50), nullable=False, index=True)  # image, audio, video
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    processing_status = Column(String(50), default="pending")
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    """Audit event model."""

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(100), nullable=False, index=True)
    ref = Column(String(255), nullable=True)
    actor = Column(String(255), nullable=True)
    data = Column(Text, nullable=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    signature = Column(String(255), nullable=True)  # Cryptographic signature


class KnowledgeVersion(Base):
    """Knowledge version model for user/group/session knowledge bases."""

    __tablename__ = "knowledge_versions"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_type = Column(String(50), nullable=False, index=True)  # user | group | session
    knowledge_id = Column(Integer, nullable=False, index=True)
    version = Column(Integer, nullable=False, index=True)
    is_current = Column(Boolean, default=False, index=True)
    note = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    entries = relationship(
        "KnowledgeEntry", back_populates="knowledge_version", cascade="all, delete-orphan"
    )


class KnowledgeEntry(Base):
    """Knowledge entry belonging to a specific knowledge version."""

    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_version_id = Column(
        Integer, ForeignKey("knowledge_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    knowledge_version = relationship("KnowledgeVersion", back_populates="entries")
