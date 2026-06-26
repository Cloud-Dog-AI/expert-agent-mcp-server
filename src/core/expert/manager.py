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
Expert Configuration Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages expert configurations

Related Requirements: FR1.1, FR1.12
Related Tasks: T007
Related Architecture: CC3.1.1
Related Tests: IT2.4

Recent Changes:
- Initial implementation
"""

import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import unicodedata

from src.database.models import ExpertConfig as ExpertConfigModel
from src.database.connection import get_db
from src.utils.logger import get_logger
from src.config.loader import get_config

logger = get_logger(__name__)


def _is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return (
        (0x3400 <= code <= 0x4DBF)
        or (0x4E00 <= code <= 0x9FFF)
        or (0xF900 <= code <= 0xFAFF)
        or (0x3040 <= code <= 0x309F)
        or (0x30A0 <= code <= 0x30FF)
        or (0xAC00 <= code <= 0xD7AF)
    )


def _entropy_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    buf: List[str] = []

    def _flush() -> None:
        if not buf:
            return
        token = "".join(buf)
        if token and all(_is_cjk_char(ch) for ch in token) and len(token) > 1:
            tokens.extend(list(token))
        else:
            tokens.append(token)
        buf.clear()

    for ch in str(text or "").casefold():
        cat0 = unicodedata.category(ch)[:1]
        if cat0 in ("L", "N"):
            buf.append(ch)
            continue
        if cat0 == "M" and buf:
            buf.append(ch)
            continue
        _flush()

    _flush()
    return [t for t in tokens if t]


def _entropy_unique_letter_number_count(text: str) -> int:
    chars = set()
    for ch in str(text or "").casefold():
        cat0 = unicodedata.category(ch)[:1]
        if cat0 in ("L", "N"):
            chars.add(ch)
    return len(chars)


class ExpertManager:
    """Manages expert configurations."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize expert manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def create_expert(
        self,
        name: str,
        title: str,
        description: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_params: Optional[Dict[str, Any]] = None,
        prompt_template: Optional[str] = None,
        tools: Optional[List[str]] = None,
        enabled: bool = True,
        access_control: Optional[Dict[str, Any]] = None,
    ) -> ExpertConfigModel:
        """
        Create a new expert configuration.

        Args:
            name: Expert name (unique)
            title: Expert title
            description: Expert description
            llm_provider: LLM provider (ollama, openai, openrouter)
            llm_model: LLM model name
            llm_params: Additional LLM parameters
            prompt_template: System prompt template
            tools: List of tool names
            enabled: Whether expert is enabled
            access_control: Access control settings

        Returns:
            Created expert configuration
        """
        db = self._get_db()
        try:
            # Mandatory title + description with entropy checks (config-driven defaults)
            if not title or str(title).strip() == "":
                raise ValueError("title is required")
            if not description or str(description).strip() == "":
                raise ValueError("description is required")

            min_desc_chars = int(get_config("prompts.min_description_chars", 30))
            if len(str(description).strip()) < min_desc_chars:
                raise ValueError(f"description must be at least {min_desc_chars} characters")

            # Simple entropy check: minimum unique words in title+description
            min_unique = int(get_config("prompts.entropy_min_unique_words", 8))
            text = f"{title} {description}"
            tokens = _entropy_tokens(text)
            if len(set(tokens)) < min_unique:
                min_unique_chars = get_config("prompts.entropy_min_unique_chars")
                if min_unique_chars is None:
                    min_unique_chars = min_unique * 2
                min_unique_chars = int(min_unique_chars)

                unique_chars = _entropy_unique_letter_number_count(text)
                if unique_chars < min_unique_chars:
                    raise ValueError(
                        "description/title entropy too low (insufficient unique words)"
                    )

            # Auto-generate prompt_template if missing
            if prompt_template is None or str(prompt_template).strip() == "":
                prompt_template = (
                    f"You are an expert assistant.\n\n"
                    f"Title: {title}\n"
                    f"Description: {description}\n\n"
                    f"Provide accurate, safe, and helpful responses. Ask clarifying questions when required."
                )

            # Resolve LLM provider/model from config if not supplied
            if not llm_provider:
                llm_provider = get_config("llm.provider")
            if not llm_model:
                llm_model = get_config("llm.model")
            if not llm_provider:
                raise ValueError("llm.provider not configured (set via env/config hierarchy)")
            if not llm_model:
                raise ValueError("llm.model not configured (set via env/config hierarchy)")

            # Check if expert exists
            existing = db.query(ExpertConfigModel).filter(ExpertConfigModel.name == name).first()
            if existing:
                raise ValueError(f"Expert '{name}' already exists")

            expert = ExpertConfigModel(
                name=name,
                title=title,
                description=description,
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_params_json=json.dumps(llm_params) if llm_params else None,
                prompt_template=prompt_template,
                tools_json=json.dumps(tools) if tools else None,
                enabled=enabled,
                access_control_json=json.dumps(access_control) if access_control else None,
            )
            db.add(expert)
            db.commit()
            db.refresh(expert)

            logger.info(f"Created expert configuration: {name}")
            return expert
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create expert: {e}", exc_info=True)
            raise

    def get_expert(
        self, expert_id: Optional[int] = None, name: Optional[str] = None
    ) -> Optional[ExpertConfigModel]:
        """Get expert by ID or name."""
        db = self._get_db()
        if expert_id:
            return db.query(ExpertConfigModel).filter(ExpertConfigModel.id == expert_id).first()
        elif name:
            return db.query(ExpertConfigModel).filter(ExpertConfigModel.name == name).first()
        return None

    def list_experts(
        self, enabled_only: bool = False, skip: int = 0, limit: int = 100
    ) -> List[ExpertConfigModel]:
        """List all experts."""
        db = self._get_db()
        query = db.query(ExpertConfigModel)
        if enabled_only:
            query = query.filter(ExpertConfigModel.enabled)
        # Keep pagination deterministic and return newest first so recently
        # created experts are visible on the first page in busy environments.
        query = query.order_by(ExpertConfigModel.id.desc())
        return query.offset(skip).limit(limit).all()

    def update_expert(self, expert_id: int, **kwargs) -> Optional[ExpertConfigModel]:
        """Update expert configuration."""
        db = self._get_db()
        try:
            expert = db.query(ExpertConfigModel).filter(ExpertConfigModel.id == expert_id).first()
            if not expert:
                return None

            # Enforce mandatory title/description and entropy when provided
            new_title = kwargs.get("title", expert.title)
            new_desc = kwargs.get("description", expert.description)
            if new_title is not None and str(new_title).strip() == "":
                raise ValueError("title is required")
            if new_desc is not None and str(new_desc).strip() == "":
                raise ValueError("description is required")

            if new_desc is not None:
                min_desc_chars = int(get_config("prompts.min_description_chars", 30))
                if len(str(new_desc).strip()) < min_desc_chars:
                    raise ValueError(f"description must be at least {min_desc_chars} characters")
                min_unique = int(get_config("prompts.entropy_min_unique_words", 8))
                text = f"{new_title} {new_desc}"
                tokens = _entropy_tokens(text)
                if len(set(tokens)) < min_unique:
                    min_unique_chars = get_config("prompts.entropy_min_unique_chars")
                    if min_unique_chars is None:
                        min_unique_chars = min_unique * 2
                    min_unique_chars = int(min_unique_chars)

                    unique_chars = _entropy_unique_letter_number_count(text)
                    if unique_chars < min_unique_chars:
                        raise ValueError(
                            "description/title entropy too low (insufficient unique words)"
                        )

            # Update allowed fields
            if "llm_params" in kwargs and kwargs["llm_params"] is not None:
                expert.llm_params_json = json.dumps(kwargs["llm_params"])
            if "tools" in kwargs and kwargs["tools"] is not None:
                expert.tools_json = json.dumps(kwargs["tools"])
            if "access_control" in kwargs and kwargs["access_control"] is not None:
                expert.access_control_json = json.dumps(kwargs["access_control"])

            allowed_fields = [
                "name",
                "title",
                "description",
                "llm_provider",
                "llm_model",
                "prompt_template",
                "enabled",
            ]
            for field, value in kwargs.items():
                if field in allowed_fields and value is not None:
                    setattr(expert, field, value)

            db.commit()
            db.refresh(expert)

            logger.info(f"Updated expert: {expert_id}")
            return expert
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update expert: {e}", exc_info=True)
            return None
