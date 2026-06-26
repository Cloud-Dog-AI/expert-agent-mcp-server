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
Prompt Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Prompt template rendering and variable substitution

Related Requirements: FR1.1
Related Tasks: T009
Related Architecture: CC3.1.2
Related Tests: UT1.6

Recent Changes:
- Initial implementation
- W28B-319 (D5): optional opt-in delegation of prompt template CRUD to the shared
  cloud_dog_agent.prompts.PromptStore. Default behaviour (db is None or store is
  None) is unchanged; the shared store is only consulted when explicitly injected.
"""

import asyncio
import json
import re
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from src.config.loader import get_config
from src.database.connection import get_db
from src.database.models import (
    ExpertConfig,
    ExpertPromptAssignment,
    PromptTemplate,
    ServiceBinding,
    SubExpertBinding,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class _StoreTemplateView:
    """Read-only view over a shared-store template that mirrors the SQLAlchemy
    ``PromptTemplate`` attributes the CRUD callers and serializer rely on.

    The shared store is keyed by template name (not an autoincrement id) and owns
    its own immutable version history; this adapter exposes a stable, DB-shaped
    surface (``id``/``name``/``version``/``content``/``variables_schema``/
    ``created_by``/``created_at``/``updated_at``) so existing API serialization
    keeps working when CRUD is delegated to the store.
    """

    __slots__ = (
        "id",
        "name",
        "version",
        "content",
        "variables_schema",
        "created_by",
        "created_at",
        "updated_at",
    )

    def __init__(
        self,
        *,
        id: Optional[int],
        name: str,
        version: int,
        content: str,
        variables_schema: Optional[str],
        created_by: Optional[str],
        created_at: Any = None,
        updated_at: Any = None,
    ) -> None:
        self.id = id
        self.name = name
        self.version = version
        self.content = content
        self.variables_schema = variables_schema
        self.created_by = created_by
        self.created_at = created_at
        self.updated_at = updated_at


class PromptManager:
    """Manages prompt templates and variable substitution.

    By default prompt template CRUD is backed by the service-local SQLAlchemy
    models (unchanged behaviour). When an optional ``store`` implementing the
    :class:`cloud_dog_agent.prompts.PromptStore` protocol is injected, the CRUD
    methods delegate to it instead. The store is opt-in: existing call sites pass
    no store and observe identical behaviour.
    """

    def __init__(self, db: Optional[Session] = None, *, store: Optional[Any] = None):
        """Initialize prompt manager.

        Args:
            db: SQLAlchemy session for the default (service-local) CRUD path.
            store: Optional shared ``PromptStore`` (cloud_dog_agent.prompts). When
                provided, template CRUD is delegated to it; when ``None`` (the
                default) the existing DB-backed behaviour is preserved exactly.
        """
        self.db = db
        self.store = store
        # Stable name<->id mapping for the store path so the DB-shaped ``id``
        # surface remains usable for get/update/delete by id. Ids are assigned in
        # creation order; this state is per-manager-instance, matching how the
        # store itself is injected per request/scope.
        self._store_ids: Dict[str, int] = {}
        self._store_names: Dict[int, str] = {}
        self._store_next_id: int = 1

    def _get_db(self) -> Session:
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    # -- shared-store delegation helpers ------------------------------------
    @staticmethod
    def _run(coro: Any) -> Any:
        """Synchronously drive a shared-store coroutine from the sync CRUD API.

        The shared :class:`PromptStore` is async; the manager's CRUD surface is
        sync. This runs the coroutine on a private event loop. It must not be
        called from inside a running loop (the CRUD methods here are sync and are
        invoked from sync code / FastAPI threadpool, so this holds).
        """
        return asyncio.run(coro)

    def _store_id_for(self, name: str) -> int:
        existing = self._store_ids.get(name)
        if existing is not None:
            return existing
        new_id = self._store_next_id
        self._store_next_id += 1
        self._store_ids[name] = new_id
        self._store_names[new_id] = name
        return new_id

    def _store_view(self, template: Any, version_no: Optional[int] = None) -> _StoreTemplateView:
        body = ""
        variables: List[str] = []
        try:
            chosen = self._run(self.store.resolve(template.name))
            body = chosen.body
            variables = list(chosen.variables)
            version_no = version_no if version_no is not None else chosen.version
        except Exception:
            version_no = version_no if version_no is not None else template.latest_version
        return _StoreTemplateView(
            id=self._store_id_for(template.name),
            name=template.name,
            version=version_no,
            content=body,
            variables_schema=json.dumps({"variables": variables}) if variables else json.dumps({}),
            created_by=str(template.metadata.get("created_by") or ""),
        )

    @staticmethod
    def _schema_to_variables(variables_schema: Optional[Dict[str, Any]]) -> Optional[List[str]]:
        """Best-effort extraction of declared variable names from a JSON schema
        dict, so they can be recorded on the shared store version. Returns None
        when nothing usable is present (store then auto-extracts from the body)."""
        if not isinstance(variables_schema, dict):
            return None
        if isinstance(variables_schema.get("variables"), list):
            return [str(v) for v in variables_schema["variables"]]
        props = variables_schema.get("properties")
        if isinstance(props, dict):
            return [str(k) for k in props.keys()]
        return None

    def _store_create_template(
        self,
        *,
        name: str,
        content: str,
        variables_schema: Optional[Dict[str, Any]],
        created_by: Optional[str],
    ) -> _StoreTemplateView:
        from cloud_dog_agent.prompts import TemplateExists

        variables = self._schema_to_variables(variables_schema)
        metadata = {"created_by": created_by} if created_by else {}
        if variables_schema is not None:
            metadata["variables_schema"] = variables_schema
        try:
            template = self._run(
                self.store.create_template(
                    name,
                    content,
                    created_by=created_by or "",
                    variables=variables,
                    metadata=metadata,
                )
            )
        except TemplateExists:
            # New revision of an existing template -> append an immutable version.
            self._run(
                self.store.add_version(
                    name, content, variables=variables, created_by=created_by or ""
                )
            )
            template = self._run(self.store.get_template(name))
        return self._store_view(template)

    def _store_list_templates(self, *, name: Optional[str]) -> List[_StoreTemplateView]:
        templates = self._run(self.store.list_templates())
        if name:
            templates = [t for t in templates if t.name == name]
        return [self._store_view(t) for t in templates]

    def _store_get_template(self, template_id: int) -> Optional[_StoreTemplateView]:
        name = self._store_names.get(template_id)
        if name is None:
            return None
        template = self._run(self.store.get_template(name))
        if template is None:
            return None
        return self._store_view(template)

    def _store_update_template(
        self,
        template_id: int,
        *,
        content: Optional[str],
        variables_schema: Optional[Dict[str, Any]],
    ) -> Optional[_StoreTemplateView]:
        name = self._store_names.get(template_id)
        if name is None:
            return None
        template = self._run(self.store.get_template(name))
        if template is None:
            return None
        if content is not None:
            # Content edits become a new immutable version (store is append-only).
            variables = self._schema_to_variables(variables_schema)
            self._run(self.store.add_version(name, content, variables=variables))
        if variables_schema is not None:
            metadata = dict(template.metadata)
            metadata["variables_schema"] = variables_schema
            self._run(self.store.update_template(name, metadata=metadata))
        template = self._run(self.store.get_template(name))
        return self._store_view(template)

    def _store_delete_template(self, template_id: int) -> bool:
        name = self._store_names.get(template_id)
        if name is None:
            return False
        deleted = bool(self._run(self.store.delete_template(name)))
        if deleted:
            self._store_names.pop(template_id, None)
            self._store_ids.pop(name, None)
        return deleted

    def render_template(
        self, template: str, variables: Dict[str, Any], default_missing: str = ""
    ) -> str:
        """
        Render template with variable substitution.

        Args:
            template: Template string with {{ variable }} placeholders
            variables: Dictionary of variables to substitute
            default_missing: Default value for missing variables

        Returns:
            Rendered template string
        """
        if not template:
            return ""

        result = template

        # Pattern to match {{ variable }} or {{ variable | default(value) }}
        pattern = r"\{\{\s*([^}|]+)(?:\s*\|\s*default\(([^)]+)\))?\s*\}\}"

        def replace_var(match):
            var_path = match.group(1).strip()
            default_value = match.group(2).strip() if match.group(2) else default_missing

            # Handle nested variable access (e.g., user.name)
            value = self._get_nested_value(variables, var_path)

            if value is None:
                return default_value
            return str(value)

        result = re.sub(pattern, replace_var, result)

        return result

    def create_prompt_template(
        self,
        name: str,
        content: str,
        variables_schema: Optional[Dict[str, Any]] = None,
        created_by: Optional[str] = None,
        version: Optional[int] = None,
    ) -> PromptTemplate:
        if self.store is not None:
            return self._store_create_template(
                name=name,
                content=content,
                variables_schema=variables_schema,
                created_by=created_by,
            )
        db = self._get_db()
        resolved_version = version
        if resolved_version is None:
            latest = (
                db.query(PromptTemplate)
                .filter(PromptTemplate.name == name)
                .order_by(PromptTemplate.version.desc())
                .first()
            )
            resolved_version = int(latest.version) + 1 if latest else 1

        template = PromptTemplate(
            name=name,
            version=resolved_version,
            content=content,
            variables_schema=json.dumps(variables_schema or {}),
            created_by=created_by,
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        return template

    def list_prompt_templates(self, name: Optional[str] = None) -> List[PromptTemplate]:
        if self.store is not None:
            return self._store_list_templates(name=name)
        db = self._get_db()
        query = db.query(PromptTemplate)
        if name:
            query = query.filter(PromptTemplate.name == name)
        return query.order_by(PromptTemplate.name.asc(), PromptTemplate.version.desc()).all()

    def get_prompt_template(self, template_id: int) -> Optional[PromptTemplate]:
        if self.store is not None:
            return self._store_get_template(template_id)
        db = self._get_db()
        return db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()

    def update_prompt_template(
        self,
        template_id: int,
        *,
        content: Optional[str] = None,
        variables_schema: Optional[Dict[str, Any]] = None,
    ) -> Optional[PromptTemplate]:
        if self.store is not None:
            return self._store_update_template(
                template_id, content=content, variables_schema=variables_schema
            )
        db = self._get_db()
        template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()
        if not template:
            return None
        if content is not None:
            template.content = content
        if variables_schema is not None:
            template.variables_schema = json.dumps(variables_schema)
        db.commit()
        db.refresh(template)
        return template

    def delete_prompt_template(self, template_id: int) -> bool:
        if self.store is not None:
            return self._store_delete_template(template_id)
        db = self._get_db()
        template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()
        if not template:
            return False
        db.delete(template)
        db.commit()
        return True

    def assign_prompt_template(self, expert_id: int, prompt_template_id: int) -> ExpertPromptAssignment:
        db = self._get_db()
        db.query(ExpertPromptAssignment).filter(
            ExpertPromptAssignment.expert_config_id == expert_id
        ).update({"is_active": False})
        assignment = ExpertPromptAssignment(
            expert_config_id=expert_id,
            prompt_template_id=prompt_template_id,
            is_active=True,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return assignment

    def build_prompt_variables(
        self,
        expert_id: int,
        *,
        user: Optional[Dict[str, Any]] = None,
        session: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        db = self._get_db()
        expert = db.query(ExpertConfig).filter(ExpertConfig.id == expert_id).first()
        if not expert:
            raise ValueError("Expert configuration not found")

        service_bindings = (
            db.query(ServiceBinding)
            .filter(ServiceBinding.expert_config_id == expert_id, ServiceBinding.enabled.is_(True))
            .all()
        )
        sub_experts = (
            db.query(SubExpertBinding)
            .filter(SubExpertBinding.parent_expert_id == expert_id, SubExpertBinding.enabled.is_(True))
            .all()
        )

        services = []
        tools = []
        for binding in service_bindings:
            service = binding.service
            if not service:
                continue
            metadata = {}
            if service.metadata_json:
                try:
                    metadata = json.loads(service.metadata_json) or {}
                except Exception:
                    metadata = {}
            discovered = metadata.get("discovered_tools") or metadata.get("tools") or []
            services.append(
                {
                    "id": service.id,
                    "name": service.name,
                    "type": service.type,
                    "endpoint_url": service.endpoint_url,
                    "tools": discovered,
                }
            )
            for item in discovered:
                if isinstance(item, dict):
                    tools.append(item.get("name") or item.get("id") or str(item))
                else:
                    tools.append(str(item))

        sub_expert_names = []
        for binding in sub_experts:
            if binding.child_expert:
                sub_expert_names.append(binding.child_expert.name)

        return {
            "expert": {"id": expert.id, "name": expert.name, "title": expert.title},
            "services": services,
            "tools": sorted({tool for tool in tools if tool}),
            "sub_experts": sub_expert_names,
            "user": user or {},
            "session": session or {},
        }

    def render_expert_prompt(
        self,
        expert_id: int,
        *,
        base_template: Optional[str] = None,
        user: Optional[Dict[str, Any]] = None,
        session: Optional[Dict[str, Any]] = None,
        extra_variables: Optional[Dict[str, Any]] = None,
    ) -> str:
        db = self._get_db()
        expert = db.query(ExpertConfig).filter(ExpertConfig.id == expert_id).first()
        if not expert:
            raise ValueError("Expert configuration not found")

        assignment = (
            db.query(ExpertPromptAssignment)
            .filter(
                ExpertPromptAssignment.expert_config_id == expert_id,
                ExpertPromptAssignment.is_active.is_(True),
            )
            .order_by(ExpertPromptAssignment.id.desc())
            .first()
        )

        template = base_template
        if template is None and assignment and assignment.prompt_template:
            template = assignment.prompt_template.content
        if template is None:
            template = expert.prompt_template or str(
                get_config("llm.default_system_prompt") or ""
            )

        variables = self.build_prompt_variables(expert_id, user=user, session=session)
        if extra_variables:
            variables.update(extra_variables)
        return self.render_template(template, variables)

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Optional[Any]:
        """
        Get nested value from dictionary using dot notation.

        Args:
            data: Dictionary to search
            path: Dot-separated path (e.g., "user.name")

        Returns:
            Value at path or None
        """
        keys = path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None

        return value
