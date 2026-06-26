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
Tool Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages tool definitions

Related Requirements: FR1.15, UC1.10
Related Tasks: T054
Related Architecture: CC8.1.1
Related Tests: AT1.16

Recent Changes:
- Initial implementation
"""

import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from src.database.models import Tool
from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ToolManager:
    """Manages tool definitions."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize tool manager.

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

    def create_tool(
        self,
        name: str,
        description: str,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        auth_requirements: Optional[Dict[str, Any]] = None,
        usage_guidelines: Optional[str] = None,
        enabled: bool = True,
    ) -> Tool:
        """
        Create a new tool definition.

        Args:
            name: Tool name (unique)
            description: Tool description
            input_schema: JSON schema for input
            output_schema: JSON schema for output
            auth_requirements: Authentication requirements
            usage_guidelines: Usage guidelines
            enabled: Whether tool is enabled

        Returns:
            Created tool
        """
        db = self._get_db()
        try:
            # Check if tool exists
            existing = db.query(Tool).filter(Tool.name == name).first()
            if existing:
                raise ValueError(f"Tool '{name}' already exists")

            tool = Tool(
                name=name,
                description=description,
                input_schema_json=json.dumps(input_schema) if input_schema else None,
                output_schema_json=json.dumps(output_schema) if output_schema else None,
                auth_requirements_json=json.dumps(auth_requirements) if auth_requirements else None,
                usage_guidelines=usage_guidelines,
                enabled=enabled,
            )
            db.add(tool)
            db.commit()
            db.refresh(tool)

            logger.info(f"Created tool: {name}")
            return tool
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create tool: {e}", exc_info=True)
            raise

    def get_tool(self, tool_id: Optional[int] = None, name: Optional[str] = None) -> Optional[Tool]:
        """Get tool by ID or name."""
        db = self._get_db()
        if tool_id:
            return db.query(Tool).filter(Tool.id == tool_id).first()
        elif name:
            return db.query(Tool).filter(Tool.name == name).first()
        return None

    def list_tools(self, enabled_only: bool = False) -> List[Tool]:
        """List all tools."""
        db = self._get_db()
        query = db.query(Tool)
        if enabled_only:
            query = query.filter(Tool.enabled)
        return query.all()

    def update_tool(self, tool_id: int, **kwargs) -> Optional[Tool]:
        """Update tool definition."""
        db = self._get_db()
        try:
            tool = db.query(Tool).filter(Tool.id == tool_id).first()
            if not tool:
                return None

            # Update allowed fields
            if "input_schema" in kwargs and kwargs["input_schema"] is not None:
                tool.input_schema_json = json.dumps(kwargs["input_schema"])
            if "output_schema" in kwargs and kwargs["output_schema"] is not None:
                tool.output_schema_json = json.dumps(kwargs["output_schema"])
            if "auth_requirements" in kwargs and kwargs["auth_requirements"] is not None:
                tool.auth_requirements_json = json.dumps(kwargs["auth_requirements"])

            allowed_fields = ["description", "usage_guidelines", "enabled"]
            for field, value in kwargs.items():
                if field in allowed_fields and value is not None:
                    setattr(tool, field, value)

            db.commit()
            db.refresh(tool)

            logger.info(f"Updated tool: {tool_id}")
            return tool
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update tool: {e}", exc_info=True)
            return None
