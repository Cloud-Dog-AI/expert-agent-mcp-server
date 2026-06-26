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
Configuration Models

License: Apache 2.0
Ownership: Cloud Dog
Description: Pydantic models for type-safe configuration

Related Requirements: NF1.5
Related Tasks: T110
Related Architecture: CM1.1
Related Tests: UT1.32

Recent Changes:
- Initial implementation
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Application configuration."""

    name: str = "Expert Agent MCP Server"
    version: str = "0.1.0"
    environment: str = "development"


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int
    base_path: str = ""
    debug: bool = False
    log_file: Optional[str] = None
    enabled: bool = True


class LLMConfig(BaseModel):
    """LLM configuration."""

    provider: str = "ollama"
    base_url: str = ""
    model: str = "qwen3:14b"
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: int = 300
    default_system_prompt: Optional[str] = None


class DatabaseConfig(BaseModel):
    """Database configuration."""

    uri: str = "sqlite:///expert.db"
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False


class SessionConfig(BaseModel):
    """Session management configuration."""

    default_ttl_hours: int = 24
    history_retention_days: int = 30
    context_window_size: int = 4096
    max_history_messages: int = 100


class AuthConfig(BaseModel):
    """Authentication configuration."""

    provider: str = "local"
    jwt_secret: str
    session_timeout_minutes: int = 60
    password_min_length: int = 8
    password_require_complexity: bool = True
    lockout_enabled: bool = False
    lockout_max_attempts: int = 5
    lockout_window_seconds: int = 300
    lockout_seconds: int = 300


class LogConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    dump_config: bool = False
    pii_redaction: bool = True


class PrivacyConfig(BaseModel):
    """Privacy configuration."""

    pii_removal_enabled: bool = True
    pii_patterns: List[Dict[str, str]] = Field(default_factory=list)
    data_encryption_at_rest: bool = True
    user_data_retention_days: int = 365


class ExpertAgentConfig(BaseModel):
    """Complete Expert Agent configuration."""

    app: AppConfig
    api_server: ServerConfig
    web_server: ServerConfig
    mcp_server: ServerConfig
    a2a_server: ServerConfig
    llm: LLMConfig
    db: DatabaseConfig
    session: SessionConfig
    auth: AuthConfig
    log: LogConfig
    privacy: PrivacyConfig

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ExpertAgentConfig":
        """Create configuration from dictionary."""
        return cls(
            app=AppConfig(**config_dict.get("app", {})),
            api_server=ServerConfig(**config_dict.get("api_server", {"port": 8083})),
            web_server=ServerConfig(**config_dict.get("web_server", {"port": 8080})),
            mcp_server=ServerConfig(**config_dict.get("mcp_server", {"port": 8081})),
            a2a_server=ServerConfig(**config_dict.get("a2a_server", {"port": 8082})),
            llm=LLMConfig(**config_dict.get("llm", {})),
            db=DatabaseConfig(**config_dict.get("db", {})),
            session=SessionConfig(**config_dict.get("session", {})),
            auth=AuthConfig(**config_dict.get("auth", {})),
            log=LogConfig(**config_dict.get("log", {})),
            privacy=PrivacyConfig(**config_dict.get("privacy", {})),
        )
