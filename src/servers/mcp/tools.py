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
MCP Tools Implementation

License: Apache 2.0
Ownership: Cloud Dog
Description: MCP tools for chat, session management, history, expert config, vector stores

Related Requirements: FR1.7, FR1.25, T039-T043
Related Tasks: T039, T040, T041, T042, T043
Related Architecture: CC1.1.3
Related Tests: ST1.2, IT2.3, AT1.11

Recent Changes:
- Initial implementation
"""

from typing import Dict, Any, List, Optional, Iterator
from contextlib import contextmanager
import json
from src.core.session.manager import SessionManager
from src.core.session.models import SessionState
from src.core.expert.manager import ExpertManager
from src.core.auth.user_manager import UserManager
from src.core.auth.api_key_manager import APIKeyManager
from src.core.vector.manager import VectorStoreManager
from src.core.llm.manager import LLMManager
from src.common.a2a_client import publish_config_change_event
from src.database.models import APIKey, User
from src.servers.api.auth import _validate_api_key_user
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MCPTools:
    """MCP tool implementations."""

    def __init__(self):
        """Initialize MCP tools."""
        self.session_manager = SessionManager()
        self.expert_manager = ExpertManager()
        self.vector_manager = VectorStoreManager()
        self.llm_manager = LLMManager()

    def close(self) -> None:
        """Release owned resources held by long-lived managers."""
        close_fn = getattr(self.session_manager, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass

    def __del__(self) -> None:
        """Best-effort cleanup of manager resources."""
        try:
            self.close()
        except Exception:
            pass

    @contextmanager
    def _db_scope(self) -> Iterator[Any]:
        """Yield a DB session and always release it."""
        from src.database.connection import get_db

        db_gen = get_db()
        db = next(db_gen)
        try:
            yield db
        finally:
            try:
                db.close()
            finally:
                try:
                    db_gen.close()
                except Exception:
                    pass

    @staticmethod
    def _serialise_expert(expert: Any) -> Dict[str, Any]:
        """Serialise an expert config for MCP responses."""
        llm_params: Dict[str, Any] = {}
        if getattr(expert, "llm_params_json", None):
            try:
                llm_params = json.loads(expert.llm_params_json) or {}
            except Exception:
                llm_params = {}

        tools: List[str] = []
        if getattr(expert, "tools_json", None):
            try:
                tools = json.loads(expert.tools_json) or []
            except Exception:
                tools = []

        return {
            "id": expert.id,
            "name": expert.name,
            "title": expert.title,
            "description": expert.description,
            "llm_provider": expert.llm_provider,
            "llm_model": expert.llm_model,
            "llm_params": llm_params,
            "tools": tools,
            "enabled": expert.enabled,
        }

    @staticmethod
    def _serialise_user(user: User) -> Dict[str, Any]:
        """Serialise a user for MCP responses."""
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "enabled": user.enabled,
        }

    @staticmethod
    def _serialise_api_key(row: APIKey) -> Dict[str, Any]:
        """Serialise an API key without leaking the hashed secret."""
        return {
            "id": row.id,
            "user_id": row.user_id,
            "group_id": row.group_id,
            "name": row.name,
            "revoked": bool(row.revoked),
            "read_channels": bool(row.read_channels),
            "read_logs": bool(row.read_logs),
            "read_histories": bool(row.read_histories),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _require_admin(
        self, db: Any, auth_context: Optional[Dict[str, Any]]
    ) -> tuple[Optional[User], Optional[str]]:
        """Resolve and validate MCP admin context."""
        context = auth_context or {}
        api_key = context.get("x_api_key") or context.get("api_key")
        if api_key:
            user = _validate_api_key_user(str(api_key), db)
            if not user:
                return None, "Invalid API key"
            if user.role != "admin":
                return None, "Admin access required"
            return user, None

        if str(context.get("role") or "").strip().lower() == "admin":
            user_id = context.get("user_id")
            username = str(context.get("username") or context.get("actor") or "admin")
            actor = User(id=int(user_id) if user_id is not None else 0, username=username, email="")
            actor.role = "admin"
            actor.enabled = True
            return actor, None

        return None, "Admin access required"

    def _emit_chat_audit(
        self,
        *,
        expert_id: Optional[int],
        user_id: Optional[int],
        session_id: Optional[int],
        outcome: str,
        output_text: str,
        token_usage: Any,
        model: Optional[str],
        llm_model: Optional[str],
        error: Optional[str],
    ) -> None:
        """Emit a PS-40 ``expert.execute`` audit event for the MCP chat path (EA3).

        The MCP ``chat`` handler bypasses ``routes/experts.py`` and the
        TransactionalExecutor, so it emits the same ``expert.execute`` event here.
        Audit emission MUST NOT break the chat response.
        """
        try:
            import hashlib

            from src.core.audit.manager import AuditManager

            details: Dict[str, Any] = {
                "action": "execute",
                "outcome": outcome,
                "mode": "mcp_chat",
                "expert_id": expert_id,
                "llm_model": llm_model,
                "model": model,
                "output_sha256": (
                    hashlib.sha256((output_text or "").encode("utf-8")).hexdigest()
                    if outcome == "success"
                    else None
                ),
                "services_invoked": [],
                "services_invoked_count": 0,
                "token_usage": token_usage,
            }
            if error:
                details["error"] = error
            with self._db_scope() as db:
                AuditManager(db).log_event(
                    event_type="expert.execute",
                    user_id=int(user_id) if user_id is not None else None,
                    expert_id=expert_id,
                    session_id=session_id,
                    details=details,
                )
        except Exception as exc:  # pragma: no cover - audit must never break chat
            logger.warning(f"MCP chat expert.execute audit emit failed: {exc}")

    async def chat_tool(
        self,
        session_id: int,
        message: str,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        language: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Chat tool for conversation initiation.

        Args:
            session_id: Session ID
            message: User message
            temperature: Sampling temperature (optional)
            top_k: Top-K sampling (optional)
            top_p: Top-P sampling (optional)
            max_tokens: Maximum tokens (optional)
            response_format: Response format ("text", "markdown", "json") (optional)
            language: Language code ("en", "fr", "pl") (optional)
            system_prompt: System prompt override (optional)

        Returns:
            Response dict
        """
        actor_user_id: Optional[int] = None
        expert_config_id: Optional[int] = None
        expert_llm_model: Optional[str] = None
        try:
            # Get session
            session = self.session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found"}
            actor_user_id = getattr(session, "user_id", None)
            expert_config_id = getattr(session, "expert_config_id", None)

            # Add user message
            self.session_manager.add_message(session_id, "user", message)

            # Get expert config
            expert = self.expert_manager.get_expert(expert_id=session.expert_config_id)
            if not expert:
                return {"error": "Expert configuration not found"}
            expert_llm_model = expert.llm_model

            llm_params: Dict[str, Any] = {}
            if expert.llm_params_json:
                try:
                    llm_params = json.loads(expert.llm_params_json) or {}
                except Exception:
                    llm_params = {}

            # Initialize LLM
            await self.llm_manager.initialize(
                provider=expert.llm_provider,
                model=expert.llm_model,
                base_url=llm_params.get("base_url"),
                api_key=llm_params.get("api_key"),
            )

            # Get message history with context window management. The just-added
            # user message is already present in session history, so do not append
            # it again or the LLM will receive the prompt twice.
            history = self.session_manager.get_message_history(
                session_id, max_tokens=session.context_window
            )

            # Prepare messages
            messages = list(history)

            # Determine system prompt (request override > expert template > language-specific > default)
            from src.config.loader import get_config

            final_system_prompt = None
            if system_prompt:
                final_system_prompt = system_prompt
            elif expert.prompt_template:
                final_system_prompt = expert.prompt_template
            elif language:
                lang_prompt = get_config(f"llm.prompts.{language}")
                if lang_prompt:
                    final_system_prompt = lang_prompt
                else:
                    final_system_prompt = get_config("llm.default_system_prompt")
            else:
                final_system_prompt = get_config("llm.default_system_prompt")

            if final_system_prompt:
                messages.insert(0, {"role": "system", "content": final_system_prompt})

            # Add response format instruction if specified
            if response_format == "json":
                json_instruction = "\n\nIMPORTANT: Respond ONLY with valid JSON. Do not include any text outside the JSON structure."
                if messages and messages[0].get("role") == "system":
                    messages[0]["content"] += json_instruction
                else:
                    messages.insert(0, {"role": "system", "content": json_instruction})
            elif response_format == "markdown":
                md_instruction = "\n\nIMPORTANT: Format your response using Markdown (headers, lists, code blocks, etc.)."
                if messages and messages[0].get("role") == "system":
                    messages[0]["content"] += md_instruction
                else:
                    messages.insert(0, {"role": "system", "content": md_instruction})

            # Prepare LLM parameters
            if temperature is None:
                temperature = get_config("llm.temperature")
                if temperature is None:
                    raise ValueError("llm.temperature not configured")
            if max_tokens is None:
                max_tokens = get_config("llm.max_tokens")
                if max_tokens is None:
                    raise ValueError("llm.max_tokens not configured")
            llm_temperature = temperature
            llm_max_tokens = max_tokens
            llm_kwargs = {}
            if top_k is not None:
                llm_kwargs["top_k"] = top_k
            if top_p is not None:
                llm_kwargs["top_p"] = top_p

            # Generate response
            response = await self.llm_manager.generate(
                messages=messages,
                temperature=llm_temperature,
                max_tokens=llm_max_tokens,
                **llm_kwargs,
            )

            # Add assistant message
            self.session_manager.add_message(
                session_id,
                "assistant",
                response["content"],
                tokens_used=response.get("tokens_used"),
            )

            self._emit_chat_audit(
                expert_id=expert_config_id,
                user_id=actor_user_id,
                session_id=session_id,
                outcome="success",
                output_text=response.get("content", ""),
                token_usage=response.get("tokens_used"),
                model=response.get("model"),
                llm_model=expert_llm_model,
                error=None,
            )

            return {
                "response": response["content"],
                "tokens_used": response.get("tokens_used"),
                "model": response.get("model"),
            }
        except Exception as e:
            logger.error(f"Chat tool error: {e}", exc_info=True)
            self._emit_chat_audit(
                expert_id=expert_config_id,
                user_id=actor_user_id,
                session_id=session_id,
                outcome="failure",
                output_text="",
                token_usage=None,
                model=None,
                llm_model=expert_llm_model,
                error=str(e),
            )
            return {"error": str(e)}

    def start_session_tool(
        self,
        user_id: int,
        expert_config_id: int,
        title: Optional[str] = None,
        channel_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Start a new session."""
        try:
            session, notification = self.session_manager.create_session(
                user_id=user_id,
                expert_config_id=expert_config_id,
                title=title,
                channel_id=channel_id,
            )

            if notification:
                return notification

            return {"session_id": session.id, "status": session.status, "title": session.title}
        except Exception as e:
            logger.error(f"Start session tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def resume_session_tool(self, session_id: int) -> Dict[str, Any]:
        """Resume an existing session."""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found"}

            # Update state to active
            self.session_manager.update_session_state(session_id, SessionState.ACTIVE)

            return {
                "session_id": session.id,
                "status": "active",
                "message_count": len(self.session_manager.get_messages(session_id)),
            }
        except Exception as e:
            logger.error(f"Resume session tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def end_session_tool(self, session_id: int) -> Dict[str, Any]:
        """End a session."""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found"}

            self.session_manager.update_session_state(session_id, SessionState.COMPLETED)

            return {"session_id": session.id, "status": "completed"}
        except Exception as e:
            logger.error(f"End session tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def list_sessions_tool(
        self, user_id: Optional[int] = None, status: Optional[str] = None
    ) -> Dict[str, Any]:
        """List sessions."""
        try:
            from src.database.models import Session as SessionModel

            with self._db_scope() as db:
                query = db.query(SessionModel)

                if user_id:
                    query = query.filter(SessionModel.user_id == user_id)
                if status:
                    query = query.filter(SessionModel.status == status)

                sessions = query.all()

            return {
                "sessions": [
                    {"id": s.id, "title": s.title, "status": s.status, "user_id": s.user_id}
                    for s in sessions
                ],
                "count": len(sessions),
            }
        except Exception as e:
            logger.error(f"List sessions tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def session_status_tool(self, session_id: int) -> Dict[str, Any]:
        """Get session status."""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {"error": "Session not found"}

            messages = self.session_manager.get_messages(session_id)

            return {
                "session_id": session.id,
                "status": session.status,
                "message_count": len(messages),
                "context_window": session.context_window,
                "created_at": session.created_at.isoformat(),
            }
        except Exception as e:
            logger.error(f"Session status tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def get_history_tool(self, session_id: int, limit: Optional[int] = None) -> Dict[str, Any]:
        """Get session history."""
        try:
            messages = self.session_manager.get_messages(session_id, limit=limit)

            return {
                "session_id": session_id,
                "messages": [
                    {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
                    for m in messages
                ],
                "count": len(messages),
            }
        except Exception as e:
            logger.error(f"Get history tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def list_experts_tool(self) -> Dict[str, Any]:
        """List expert configurations."""
        try:
            experts = self.expert_manager.list_experts()

            return {
                "experts": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "title": e.title,
                        "llm_provider": e.llm_provider,
                        "llm_model": e.llm_model,
                    }
                    for e in experts
                ],
                "count": len(experts),
            }
        except Exception as e:
            logger.error(f"List experts tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def get_expert_tool(self, expert_id: int) -> Dict[str, Any]:
        """Get expert configuration."""
        try:
            expert = self.expert_manager.get_expert(expert_id=expert_id)
            if not expert:
                return {"error": "Expert not found"}

            return {
                "id": expert.id,
                "name": expert.name,
                "title": expert.title,
                "llm_provider": expert.llm_provider,
                "llm_model": expert.llm_model,
                "enabled": expert.enabled,
            }
        except Exception as e:
            logger.error(f"Get expert tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def admin_list_experts_tool(
        self,
        auth_context: Optional[Dict[str, Any]] = None,
        enabled_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """List expert configurations with admin RBAC."""
        try:
            with self._db_scope() as db:
                _, error = self._require_admin(db, auth_context)
                if error:
                    return {"error": error}
                experts = ExpertManager(db).list_experts(
                    enabled_only=enabled_only, skip=skip, limit=limit
                )
            return {
                "experts": [self._serialise_expert(expert) for expert in experts],
                "count": len(experts),
            }
        except Exception as e:
            logger.error(f"Admin list experts tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def admin_create_expert_tool(
        self,
        *,
        name: str,
        title: str,
        description: str,
        auth_context: Optional[Dict[str, Any]] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_params: Optional[Dict[str, Any]] = None,
        prompt_template: Optional[str] = None,
        tools: Optional[List[str]] = None,
        enabled: bool = True,
        access_control: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an expert configuration with admin RBAC."""
        try:
            with self._db_scope() as db:
                actor, error = self._require_admin(db, auth_context)
                if error:
                    return {"error": error}
                resolved_llm_params = dict(llm_params or {})
                if llm_base_url:
                    resolved_llm_params["base_url"] = llm_base_url
                expert = ExpertManager(db).create_expert(
                    name=name,
                    title=title,
                    description=description,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    llm_params=resolved_llm_params or None,
                    prompt_template=prompt_template,
                    tools=tools,
                    enabled=enabled,
                    access_control=access_control,
                )
                payload = self._serialise_expert(expert)
            publish_config_change_event(
                action="create",
                resource_type="expert",
                resource_id=int(payload["id"]),
                actor=getattr(actor, "username", None),
            )
            return payload
        except Exception as e:
            logger.error(f"Admin create expert tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def admin_update_expert_tool(
        self,
        expert_id: int,
        auth_context: Optional[Dict[str, Any]] = None,
        **updates: Any,
    ) -> Dict[str, Any]:
        """Update an expert configuration with admin RBAC."""
        try:
            with self._db_scope() as db:
                actor, error = self._require_admin(db, auth_context)
                if error:
                    return {"error": error}
                update_data = dict(updates)
                llm_base_url = update_data.pop("llm_base_url", None)
                llm_params = update_data.get("llm_params")
                if llm_base_url is not None or llm_params is not None:
                    resolved_llm_params = dict(llm_params or {})
                    if llm_base_url:
                        resolved_llm_params["base_url"] = llm_base_url
                    update_data["llm_params"] = resolved_llm_params
                expert = ExpertManager(db).update_expert(expert_id, **update_data)
                if not expert:
                    return {"error": "Expert not found"}
                payload = self._serialise_expert(expert)
            publish_config_change_event(
                action="update",
                resource_type="expert",
                resource_id=int(payload["id"]),
                actor=getattr(actor, "username", None),
            )
            return payload
        except Exception as e:
            logger.error(f"Admin update expert tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def admin_delete_expert_tool(
        self, expert_id: int, auth_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Delete an expert configuration with admin RBAC."""
        try:
            with self._db_scope() as db:
                actor, error = self._require_admin(db, auth_context)
                if error:
                    return {"error": error}
                expert = ExpertManager(db).get_expert(expert_id=expert_id)
                if not expert:
                    return {"error": "Expert not found"}
                expert_name = expert.name
                db.delete(expert)
                db.commit()
            publish_config_change_event(
                action="delete",
                resource_type="expert",
                resource_id=int(expert_id),
                actor=getattr(actor, "username", None),
            )
            return {"success": True, "id": expert_id, "name": expert_name}
        except Exception as e:
            logger.error(f"Admin delete expert tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def admin_list_users_tool(
        self,
        auth_context: Optional[Dict[str, Any]] = None,
        enabled_only: bool = False,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List users with admin RBAC."""
        try:
            with self._db_scope() as db:
                _, error = self._require_admin(db, auth_context)
                if error:
                    return {"error": error}
                query = db.query(User)
                if enabled_only:
                    query = query.filter(User.enabled.is_(True))
                if role:
                    query = query.filter(User.role == role)
                users = query.order_by(User.id.asc()).all()
            return {"users": [self._serialise_user(user) for user in users], "count": len(users)}
        except Exception as e:
            logger.error(f"Admin list users tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def admin_create_api_key_tool(
        self,
        auth_context: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        name: Optional[str] = None,
        expires_days: Optional[int] = None,
        read_logs: bool = True,
        read_histories: bool = True,
        read_channels: bool = True,
    ) -> Dict[str, Any]:
        """Create an API key with admin RBAC."""
        try:
            with self._db_scope() as db:
                actor, error = self._require_admin(db, auth_context)
                if error:
                    return {"error": error}
                manager = APIKeyManager(db)
                result = manager.generate_key(
                    user_id=user_id,
                    name=name,
                    expires_days=expires_days,
                    scopes=None,
                )
                api_key = result["api_key"]
                api_key.read_logs = bool(read_logs)
                api_key.read_histories = bool(read_histories)
                api_key.read_channels = bool(read_channels)
                db.commit()
                db.refresh(api_key)
                payload = self._serialise_api_key(api_key)
                payload["key"] = result["key"]
            publish_config_change_event(
                action="create",
                resource_type="api_key",
                resource_id=int(payload["id"]),
                actor=getattr(actor, "username", None),
            )
            return payload
        except Exception as e:
            logger.error(f"Admin create api key tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def admin_revoke_api_key_tool(
        self, key_id: int, auth_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Revoke an API key with admin RBAC."""
        try:
            with self._db_scope() as db:
                actor, error = self._require_admin(db, auth_context)
                if error:
                    return {"error": error}
                if not APIKeyManager(db).revoke_key(key_id):
                    return {"error": "API key not found"}
            publish_config_change_event(
                action="delete",
                resource_type="api_key",
                resource_id=int(key_id),
                actor=getattr(actor, "username", None),
            )
            return {"success": True, "id": key_id, "revoked": True}
        except Exception as e:
            logger.error(f"Admin revoke api key tool error: {e}", exc_info=True)
            return {"error": str(e)}

    async def search_vector_tool(
        self, query: str, collection: str, n_results: int = 5, vector_store_name: str = "_DEFAULT_"
    ) -> Dict[str, Any]:
        """Search vector store."""
        try:
            results = await self.vector_manager.search(
                store_name=vector_store_name,
                collection=collection,
                query=query,
                n_results=n_results,
            )

            return {"query": query, "results": results, "count": len(results)}
        except Exception as e:
            logger.error(f"Search vector tool error: {e}", exc_info=True)
            return {"error": str(e)}

    async def add_to_vector_tool(
        self,
        documents: List[str],
        collection: str,
        vector_store_name: str = "_DEFAULT_",
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Add documents to vector store."""
        try:
            ids = await self.vector_manager.add_documents(
                store_name=vector_store_name,
                collection=collection,
                documents=documents,
                metadatas=metadatas,
            )

            return {"ids": ids, "count": len(ids), "collection": collection}
        except Exception as e:
            logger.error(f"Add to vector tool error: {e}", exc_info=True)
            return {"error": str(e)}

    # AT1.11: Session key and history key tools

    def get_session_by_key_tool(self, session_key: str) -> Dict[str, Any]:
        """Get session by session key."""
        try:
            from src.core.session.key_manager import SessionKeyManager

            with self._db_scope() as db:
                key_manager = SessionKeyManager(db)
                session = key_manager.get_session_by_key(session_key)

            if not session:
                return {"error": "Session not found or key expired"}

            return {
                "session_id": session.id,
                "title": session.title,
                "status": session.status,
                "user_id": session.user_id,
                "expert_config_id": session.expert_config_id,
                "session_key": session.session_key,
                "history_key": session.history_key,
            }
        except Exception as e:
            logger.error(f"Get session by key tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def get_history_by_key_tool(self, history_key: str) -> Dict[str, Any]:
        """Get history by history key."""
        try:
            from src.core.session.key_manager import HistoryKeyManager

            with self._db_scope() as db:
                history_manager = HistoryKeyManager(db)
                history = history_manager.get_history_by_key(history_key)

            if not history:
                return {"error": "History not found"}

            return history
        except Exception as e:
            logger.error(f"Get history by key tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def share_session_tool(
        self,
        session_id: int,
        user_ids: Optional[List[int]] = None,
        group_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Share session with users and/or groups."""
        try:
            from src.core.session.sharing_manager import HistorySharingManager

            with self._db_scope() as db:
                sharing_manager = HistorySharingManager(db)
                result = sharing_manager.share_session(
                    session_id=session_id, user_ids=user_ids, group_ids=group_ids
                )
            return result
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Share session tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def unshare_session_tool(
        self,
        session_id: int,
        user_ids: Optional[List[int]] = None,
        group_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Unshare session with users and/or groups."""
        try:
            from src.core.session.sharing_manager import HistorySharingManager

            with self._db_scope() as db:
                sharing_manager = HistorySharingManager(db)
                result = sharing_manager.unshare_session(
                    session_id=session_id, user_ids=user_ids, group_ids=group_ids
                )
            return result
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Unshare session tool error: {e}", exc_info=True)
            return {"error": str(e)}

    async def summarize_session_tool(
        self, session_id: int, preserve_recent: int = 5, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Trigger session summarization."""
        try:
            from src.core.session.summarization_manager import ContextSummarizationManager

            with self._db_scope() as db:
                summarization_manager = ContextSummarizationManager(db)
                result = await summarization_manager.summarize_session(
                    session_id=session_id, preserve_recent=preserve_recent, max_tokens=max_tokens
                )
            return result
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Summarize session tool error: {e}", exc_info=True)
            return {"error": str(e)}

    def get_summaries_tool(self, session_id: int) -> Dict[str, Any]:
        """Get all summaries for a session."""
        try:
            from src.core.session.summarization_manager import ContextSummarizationManager

            with self._db_scope() as db:
                summarization_manager = ContextSummarizationManager(db)
                summaries = summarization_manager.get_summaries(session_id)
            return {"session_id": session_id, "summaries": summaries, "count": len(summaries)}
        except Exception as e:
            logger.error(f"Get summaries tool error: {e}", exc_info=True)
            return {"error": str(e)}

    async def execute_tool(
        self,
        expert_id: int,
        input_text: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Transactional execution entry point for MCP."""
        try:
            from src.core.execution.transactional import TransactionalExecutor

            with self._db_scope() as db:
                executor = TransactionalExecutor(db)
                return await executor.execute(
                    expert_id=expert_id,
                    input_text=input_text,
                    parameters=parameters or {},
                    context=context or {},
                    auth_context=auth_context or {},
                )
        except Exception as e:
            logger.error(f"Execute tool error: {e}", exc_info=True)
            return {"error": str(e)}

    async def list_services_tool(self, expert_id: int) -> Dict[str, Any]:
        """List bound services for an expert."""
        try:
            from src.core.service.composition import ServiceCompositionManager

            with self._db_scope() as db:
                manager = ServiceCompositionManager(db)
                services = await manager.get_available_tools(expert_id)
            return {"expert_id": expert_id, "services": services, "count": len(services)}
        except Exception as e:
            logger.error(f"List services tool error: {e}", exc_info=True)
            return {"error": str(e)}

    async def invoke_service_tool(
        self,
        service_id: int,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        session_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Invoke a remote tool on a bound external service."""
        try:
            from src.core.service.composition import ServiceCompositionManager

            with self._db_scope() as db:
                manager = ServiceCompositionManager(db)
                return await manager.invoke_tool(
                    service_id=service_id,
                    tool_name=tool_name,
                    arguments=arguments or {},
                    auth_context=auth_context or {},
                    session_id=session_id,
                )
        except Exception as e:
            logger.error(f"Invoke service tool error: {e}", exc_info=True)
            return {"error": str(e)}

    async def code_execute_tool(
        self,
        code: str,
        language: Optional[str] = None,
        task_id: Optional[str] = None,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run code on the code-runner service over A2A (analyst reasoning tool).

        Sends a ``code.execute`` request so the agent can compute / verify by
        executing code. The code-runner base URL + API key come from
        ``code_runner.*`` config. The active correlation id (or one supplied via
        ``auth_context['correlation_id']``) is forwarded so code-runner's audit
        can be linked back to this request.
        """
        try:
            from src.core.service.code_runner import CodeRunnerClient

            correlation_id = None
            if isinstance(auth_context, dict):
                correlation_id = auth_context.get("correlation_id")

            client = CodeRunnerClient()
            return await client.execute(
                code=code,
                language=language,
                task_id=task_id,
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.error(f"Code execute tool error: {e}", exc_info=True)
            return {"error": str(e)}
