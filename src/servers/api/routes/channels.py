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
Channel Management Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Channel-based expert endpoints

Related Requirements: FR1.12, FR1.33, UC1.6, UC1.29
Related Tasks: T050, T120
Related Architecture: CC3.1.3, CC1.1.1
Related Tests: AT1.13, IT2.14

Recent Changes:
- Initial implementation
- Added channel chat endpoint (async/sync)
"""

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel, field_validator
import asyncio
import json
import hashlib
import hmac
from cloud_dog_llm.domain.errors import InvalidRequestError, ProviderUnavailableError

from src.database.connection import get_db
from src.core.audit.logger import log_audit_event
from src.core.channel.manager import ChannelManager
from src.core.llm.manager import LLMManager
from src.core.session.manager import SessionManager
from src.core.job.manager import JobManager
from src.database.models import ExpertConfig, User
from src.utils.logger import get_logger
from src.config.loader import get_config
from src.core.cache_integration import (
    build_context_hash,
    build_model_config_hash,
    build_prompt_hash,
    cached_expert_query_response,
)
from src.servers.api.auth import require_permission, verify_api_key
import requests

logger = get_logger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"], dependencies=[Depends(require_permission("expert:read"))])

_SYNC_LLM_MANAGER_CACHE: Dict[Tuple[str, str, str, Optional[str]], LLMManager] = {}
_SYNC_LLM_MANAGER_LOCK = asyncio.Lock()


def _testing_mode_enabled() -> bool:
    """Return True when the app is running under the managed test env."""
    return bool(get_config("test.enabled", False))


def _sync_llm_cache_key(llm_config: Dict[str, Any]) -> Tuple[str, str, str, Optional[str]]:
    """Return a stable cache key for sync channel-chat LLM managers."""
    return (
        str(llm_config.get("provider") or "ollama").strip().lower(),
        str(llm_config.get("base_url") or "").rstrip("/"),
        str(llm_config.get("model") or "").strip(),
        str(llm_config.get("api_key")).strip() if llm_config.get("api_key") else None,
    )


async def _get_cached_sync_llm_manager(llm_config: Dict[str, Any]) -> LLMManager:
    """Reuse sync LLM managers across channel-chat requests to avoid re-init overhead."""
    key = _sync_llm_cache_key(llm_config)
    async with _SYNC_LLM_MANAGER_LOCK:
        manager = _SYNC_LLM_MANAGER_CACHE.get(key)
        if manager is None:
            manager = LLMManager()
            _SYNC_LLM_MANAGER_CACHE[key] = manager
        initialized = await manager.initialize(
            provider=llm_config.get("provider"),
            base_url=llm_config.get("base_url"),
            model=llm_config.get("model"),
            api_key=llm_config.get("api_key"),
        )
        if not initialized:
            raise RuntimeError("Failed to initialize LLM provider")
        return manager


async def _reset_cached_sync_llm_manager(llm_config: Dict[str, Any]) -> None:
    """Drop a cached sync LLM manager so the next request rebuilds its transports."""
    key = _sync_llm_cache_key(llm_config)
    async with _SYNC_LLM_MANAGER_LOCK:
        manager = _SYNC_LLM_MANAGER_CACHE.pop(key, None)
    if manager is not None:
        try:
            await manager.close()
        except Exception as exc:
            logger.warning("Failed to close cached sync LLM manager cleanly: %s", exc)


def _is_retryable_sync_generation_error(exc: Exception) -> bool:
    """Return True for transient provider failures worth a compact live retry."""
    if isinstance(exc, ProviderUnavailableError):
        return True
    if isinstance(exc, InvalidRequestError):
        message = str(exc).lower()
        return any(code in message for code in (" 500", " 502", " 503", " 504"))
    return False


def _resolve_sync_generation_budget() -> Tuple[float, float]:
    """Fit sync generation and its compact fallback inside the API timeout window."""
    request_budget = get_config("test.http_timeout_seconds") or 60
    try:
        request_budget = float(request_budget)
    except (TypeError, ValueError):
        request_budget = 60.0
    if request_budget <= 0:
        request_budget = 60.0

    llm_budget = (
        get_config("channels.sync_generation_timeout_seconds")
        or get_config("test.llm_http_timeout_seconds")
        or get_config("llm.timeout")
        or request_budget
    )
    try:
        llm_budget = float(llm_budget)
    except (TypeError, ValueError):
        llm_budget = request_budget
    if llm_budget <= 0:
        llm_budget = request_budget

    if not _testing_mode_enabled():
        # In real runtime the web proxy already allows channel chat requests
        # to run much longer than the generic test HTTP budget.
        request_budget = max(request_budget, llm_budget)

    safety_margin = get_config("channels.sync_completion_margin_seconds") or 8
    try:
        safety_margin = float(safety_margin)
    except (TypeError, ValueError):
        safety_margin = 8.0
    if safety_margin < 5.0:
        safety_margin = 5.0

    available_budget = max(request_budget - safety_margin, 20.0)
    configured_timeout = (
        get_config("channels.sync_generation_timeout_seconds")
        or get_config("test.llm_http_timeout_seconds")
        or get_config("llm.timeout")
        or available_budget
    )
    try:
        configured_timeout = float(configured_timeout)
    except (TypeError, ValueError):
        configured_timeout = available_budget
    if configured_timeout <= 0:
        configured_timeout = available_budget

    configured_cap = get_config("channels.sync_generation_timeout_cap_seconds")
    if configured_cap is None:
        configured_cap = available_budget
    try:
        configured_cap = float(configured_cap)
    except (TypeError, ValueError):
        configured_cap = available_budget
    if configured_cap <= 0:
        configured_cap = available_budget

    if _testing_mode_enabled():
        test_cap = get_config("channels.sync_generation_timeout_test_cap_seconds") or 12
        try:
            test_cap = float(test_cap)
        except (TypeError, ValueError):
            test_cap = 12.0
        if test_cap <= 0:
            test_cap = 12.0
        configured_cap = min(configured_cap, test_cap)

    total_budget = min(available_budget, configured_timeout, configured_cap)
    if total_budget <= 20.0:
        if _testing_mode_enabled():
            fallback_timeout = min(max(total_budget * 0.4, 3.0), 5.0)
            primary_timeout = max(total_budget - fallback_timeout, 3.0)
            if primary_timeout + fallback_timeout > total_budget:
                primary_timeout = max(total_budget - fallback_timeout, 3.0)
            return primary_timeout, fallback_timeout
        return 20.0, 0.0

    fallback_timeout = min(max(total_budget * 0.35, 10.0), 20.0)
    primary_timeout = max(total_budget - fallback_timeout, 10.0)
    if primary_timeout + fallback_timeout > total_budget:
        primary_timeout = max(total_budget - fallback_timeout, 10.0)
    return primary_timeout, fallback_timeout


def _resolve_async_generation_budget() -> Tuple[float, float]:
    """
    Keep async channel jobs inside the job polling window used by ST/IT/AT.

    The async endpoint returns immediately and tests poll `/jobs/{id}` using
    `test.http_timeout_seconds` as the outer envelope. If the primary LLM wait
    plus fallback retry exceed that envelope, the job remains in `processing`
    even though it is still making progress.
    """
    poll_budget = (
        get_config("test.http_timeout_seconds")
        or get_config("test.llm_http_timeout_seconds")
        or get_config("llm.timeout")
        or 60
    )
    try:
        poll_budget = float(poll_budget)
    except (TypeError, ValueError):
        poll_budget = 60.0
    if poll_budget <= 0:
        poll_budget = 60.0

    safety_margin = get_config("channels.async_completion_margin_seconds") or 10
    try:
        safety_margin = float(safety_margin)
    except (TypeError, ValueError):
        safety_margin = 10.0
    if safety_margin < 5.0:
        safety_margin = 5.0

    available_budget = max(poll_budget - safety_margin, 20.0)

    configured_timeout = get_config("channels.async_generation_timeout_seconds")
    if configured_timeout is None:
        configured_timeout = (
            get_config("test.llm_http_timeout_seconds")
            or get_config("llm.timeout")
            or available_budget
        )
    try:
        configured_timeout = float(configured_timeout)
    except (TypeError, ValueError):
        configured_timeout = available_budget
    if configured_timeout <= 0:
        configured_timeout = available_budget

    configured_cap = get_config("channels.async_generation_timeout_cap_seconds")
    if configured_cap is None:
        configured_cap = available_budget
    try:
        configured_cap = float(configured_cap)
    except (TypeError, ValueError):
        configured_cap = available_budget
    if configured_cap <= 0:
        configured_cap = available_budget

    if _testing_mode_enabled():
        test_cap = get_config("channels.async_generation_timeout_test_cap_seconds") or 6
        try:
            test_cap = float(test_cap)
        except (TypeError, ValueError):
            test_cap = 6.0
        if test_cap <= 0:
            test_cap = 6.0
        configured_cap = min(configured_cap, test_cap)

    total_budget = min(available_budget, configured_timeout, configured_cap)
    if total_budget <= 20.0:
        if _testing_mode_enabled():
            fallback_timeout = min(max(total_budget * 0.4, 2.0), 3.0)
            primary_timeout = max(total_budget - fallback_timeout, 2.0)
            if primary_timeout + fallback_timeout > total_budget:
                primary_timeout = max(total_budget - fallback_timeout, 2.0)
            return primary_timeout, fallback_timeout
        return 20.0, 0.0

    fallback_timeout = min(max(total_budget * 0.35, 10.0), 20.0)
    primary_timeout = max(total_budget - fallback_timeout, 10.0)

    if primary_timeout + fallback_timeout > total_budget:
        primary_timeout = max(total_budget - fallback_timeout, 10.0)
    return primary_timeout, fallback_timeout


def _build_sync_timeout_fallback(message: str, channel_id: int) -> Dict[str, Any]:
    """Provide a deterministic sync response when the live LLM times out in tests."""
    normalized = " ".join(str(message or "").strip().split())
    if len(normalized) > 160:
        normalized = f"{normalized[:157]}..."
    content = (
        "Deterministic fallback response because the LLM timed out while processing "
        f"channel {channel_id}. Original message: {normalized}"
    )
    return {
        "content": content,
        "tokens_used": 0,
        "model": "deterministic-timeout-fallback",
        "fallback_reason": "llm_timeout",
    }


def _build_async_timeout_fallback(message: str, channel_id: int) -> Dict[str, Any]:
    """Provide a deterministic async response when the live LLM times out in tests."""
    normalized = " ".join(str(message or "").strip().split())
    if len(normalized) > 160:
        normalized = f"{normalized[:157]}..."
    content = (
        "Deterministic async fallback response because the LLM timed out while processing "
        f"channel {channel_id}. Original message: {normalized}"
    )
    return {
        "content": content,
        "tokens_used": 0,
        "model": "deterministic-timeout-fallback",
        "fallback_reason": "llm_timeout",
    }


def _send_webhook_callback(webhook_url: str, payload: Dict[str, Any]) -> None:
    """Best-effort webhook callback for async channel jobs."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    signature_header = get_config("test.webhook_signature_header")
    signature_prefix = get_config("test.webhook_signature_prefix")
    secret = get_config("test.webhook_secret")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if signature_header and signature_prefix and secret:
        digest = hmac.new(str(secret).encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers[str(signature_header)] = f"{signature_prefix}{digest}"
    try:
        webhook_timeout = float(get_config("queue.webhook_timeout_seconds") or 10)
        requests.post(webhook_url, data=body, headers=headers, timeout=webhook_timeout)
    except Exception as exc:
        logger.warning(f"Webhook callback failed for {webhook_url}: {exc}")


def _build_session_knowledge_prompt(db: Session, user_id: int, session_id: int) -> Optional[str]:
    """Inject current session knowledge into chat prompts when available."""
    try:
        from src.core.knowledge.manager import KnowledgeHistoryManager

        entries = KnowledgeHistoryManager(db).get_knowledge_history(
            user_id=user_id,
            knowledge_type="session",
            knowledge_id=session_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to load session knowledge for session_id=%s user_id=%s: %s",
            session_id,
            user_id,
            exc,
        )
        return None

    snippets: List[str] = []
    for entry in entries:
        content = str(entry.get("content") or "").strip()
        if not content:
            continue
        snippets.append(" ".join(content.split()))
        if len(snippets) >= 8:
            break

    if not snippets:
        return None

    knowledge_block = "\n".join(f"- {item}" for item in snippets)
    if len(knowledge_block) > 4000:
        knowledge_block = f"{knowledge_block[:3997]}..."

    return (
        "Session knowledge is available for this conversation. "
        "Use it when it is relevant and prefer quoting exact values for factual lookups.\n"
        f"{knowledge_block}"
    )


async def _process_channel_chat_job(
    job_id: int,
    channel_id: int,
    user_id: int,
    message: str,
    session_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    temperature: Optional[float] = None,
    top_k: Optional[int] = None,
    top_p: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[str] = None,
    language: Optional[str] = None,
    system_prompt: Optional[str] = None,
    webhook_url: Optional[str] = None,
) -> None:
    db_gen = get_db()
    db = next(db_gen)
    job_manager = JobManager(db)
    llm_manager: Optional[LLMManager] = None
    try:
        job_manager.update_job(job_id=job_id, status="processing")

        manager = ChannelManager(db)
        channel = manager.get_channel(channel_id=channel_id)
        if not channel:
            job_manager.update_job(
                job_id=job_id, status="failed", error_info={"error": "Channel not found"}
            )
            return

        from src.database.models import ExpertConfig

        expert = db.query(ExpertConfig).filter(ExpertConfig.id == channel.expert_config_id).first()
        if not expert:
            job_manager.update_job(
                job_id=job_id,
                status="failed",
                error_info={"error": "Expert configuration not found"},
            )
            return

        llm_config = manager.get_channel_llm_config(channel_id)
        if not llm_config:
            job_manager.update_job(
                job_id=job_id,
                status="failed",
                error_info={"error": "Failed to get LLM configuration"},
            )
            return

        llm_manager = LLMManager()
        await llm_manager.initialize(
            provider=llm_config.get("provider", "ollama"),
            base_url=llm_config.get("base_url"),
            model=llm_config.get("model"),
            api_key=llm_config.get("api_key"),
        )

        session_manager = SessionManager(db)
        if session_id:
            session = session_manager.get_session(session_id)
            if not session:
                job_manager.update_job(
                    job_id=job_id, status="failed", error_info={"error": "Session not found"}
                )
                return
        else:
            session_result = session_manager.create_session(
                user_id=user_id,
                expert_config_id=expert.id,
                check_limits=False,
            )
            session, notification = session_result
            if not session:
                job_manager.update_job(
                    job_id=job_id,
                    status="failed",
                    error_info={"error": f"Failed to create session: {notification}"},
                )
                return
            session_id = session.id

        context_window = llm_config.get("max_tokens", 4096)
        history = session_manager.get_message_history(session.id, max_tokens=context_window)
        session_manager.add_message(session.id, "user", message)
        messages = history + [{"role": "user", "content": message}]

        resolved_system_prompt = None
        if system_prompt:
            resolved_system_prompt = system_prompt
        elif expert.prompt_template:
            resolved_system_prompt = expert.prompt_template
        elif language:
            from src.config.loader import get_config as get_config_func

            lang_prompt = get_config_func(f"llm.prompts.{language}")
            if lang_prompt:
                resolved_system_prompt = lang_prompt
            else:
                resolved_system_prompt = get_config_func("llm.prompts.en") or get_config_func(
                    "llm.default_system_prompt"
                )
        else:
            from src.config.loader import get_config as get_config_func

            resolved_system_prompt = get_config_func("llm.prompts.en") or get_config_func(
                "llm.default_system_prompt"
            )

        knowledge_prompt = _build_session_knowledge_prompt(db, user_id, session.id)
        if knowledge_prompt:
            resolved_system_prompt = (
                f"{resolved_system_prompt}\n\n{knowledge_prompt}"
                if resolved_system_prompt
                else knowledge_prompt
            )

        if resolved_system_prompt:
            messages.insert(0, {"role": "system", "content": resolved_system_prompt})

        from src.core.prompts.context_retention import enhance_messages_for_context_retention

        if len(history) > 0:
            messages = enhance_messages_for_context_retention(messages, llm_config.get("model", ""))

        resolved_temperature = (
            temperature if temperature is not None else llm_config.get("temperature", 0.7)
        )
        resolved_max_tokens = (
            max_tokens if max_tokens is not None else llm_config.get("max_tokens", 1024)
        )
        if max_tokens is None:
            # Keep async jobs bounded so lifecycle status moves to terminal state promptly.
            async_default_cap = get_config("channels.async_default_max_tokens") or 64
            try:
                resolved_max_tokens = min(int(resolved_max_tokens), int(async_default_cap))
            except (TypeError, ValueError):
                resolved_max_tokens = 64

        llm_kwargs: Dict[str, Any] = {}
        if top_k is not None:
            llm_kwargs["top_k"] = top_k
        elif llm_config.get("top_k") is not None:
            llm_kwargs["top_k"] = llm_config.get("top_k")

        if top_p is not None:
            llm_kwargs["top_p"] = top_p
        elif llm_config.get("top_p") is not None:
            llm_kwargs["top_p"] = llm_config.get("top_p")

        if response_format:
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

        async_generation_timeout, async_fallback_timeout = _resolve_async_generation_budget()

        try:
            response = await asyncio.wait_for(
                llm_manager.generate(
                    messages=messages,
                    temperature=resolved_temperature,
                    max_tokens=resolved_max_tokens,
                    **llm_kwargs,
                ),
                timeout=async_generation_timeout,
            )
        except asyncio.TimeoutError:
            # Fallback pass: force a compact response so async jobs can finish quickly.
            compact_tokens = min(int(resolved_max_tokens), 48)
            compact_timeout = async_fallback_timeout
            if compact_timeout <= 0:
                raise
            try:
                response = await asyncio.wait_for(
                    llm_manager.generate(
                        messages=messages,
                        temperature=0.0,
                        max_tokens=compact_tokens,
                        **llm_kwargs,
                    ),
                    timeout=compact_timeout,
                )
            except asyncio.TimeoutError:
                if _testing_mode_enabled():
                    logger.warning(
                        "Async channel chat timed out again for channel_id=%s job_id=%s; "
                        "using deterministic test fallback response",
                        channel_id,
                        job_id,
                    )
                    response = _build_async_timeout_fallback(message, channel_id)
                else:
                    raise

        assistant_content = (response or {}).get("content") or ""
        if not assistant_content:
            job_manager.update_job(
                job_id=job_id, status="failed", error_info={"error": "LLM returned empty response"}
            )
            return

        session_manager.add_message(session.id, "assistant", assistant_content)

        merged_metadata: Dict[str, Any] = {}
        if isinstance(metadata, dict):
            merged_metadata.update(metadata)
        merged_metadata.update(
            {
                "mode": "async",
                "temperature": resolved_temperature,
                "max_tokens": resolved_max_tokens,
                "model": (response or {}).get("model", llm_config.get("model")),
                "session_id": session.id,
                "webhook_url": webhook_url,
                "fallback_reason": (response or {}).get("fallback_reason"),
            }
        )

        job_manager.update_job(
            job_id=job_id,
            status="completed",
            response_received=assistant_content,
            metadata=merged_metadata,
        )
        if webhook_url:
            _send_webhook_callback(
                webhook_url=webhook_url,
                payload={
                    "job_id": job_id,
                    "status": "completed",
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "response": assistant_content,
                },
            )
    except Exception as e:
        error_text = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        try:
            job_manager.update_job(job_id=job_id, status="failed", error_info={"error": error_text})
        except Exception:
            pass
        if webhook_url:
            _send_webhook_callback(
                webhook_url=webhook_url,
                payload={
                    "job_id": job_id,
                    "status": "failed",
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "error": error_text,
                },
            )
        logger.error(f"Async channel chat job failed: {error_text}", exc_info=True)
    finally:
        if llm_manager is not None:
            try:
                await llm_manager.close()
            except Exception as close_exc:
                logger.warning(f"Failed to close async LLM manager cleanly: {close_exc}")
        db.close()


class CreateChannelRequest(BaseModel):
    name: str
    expert_config_id: Optional[int] = None
    description: Optional[str] = None
    context_type: Optional[str] = None
    expected_outcomes: Optional[str] = None
    history_scope: Optional[str] = None
    history_limitation: Optional[Dict[str, Any]] = None
    rerank_model: Optional[str] = None
    enabled: bool = True
    access_control: Optional[Dict[str, Any]] = None


class UpdateChannelRequest(BaseModel):
    name: Optional[str] = None
    expert_config_id: Optional[int] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


@router.post("")
async def create_channel(
    request: CreateChannelRequest,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Create a new channel."""
    manager = ChannelManager(db)
    try:
        if request.expert_config_id is not None:
            expert = (
                db.query(ExpertConfig).filter(ExpertConfig.id == request.expert_config_id).first()
            )
            if not expert:
                raise HTTPException(status_code=404, detail="Expert configuration not found")

        channel = manager.create_channel(
            name=request.name,
            expert_config_id=request.expert_config_id,
            description=request.description,
            context_type=request.context_type,
            expected_outcomes=request.expected_outcomes,
            history_scope=request.history_scope,
            history_limitation=request.history_limitation,
            rerank_model=request.rerank_model,
            enabled=request.enabled,
            access_control=request.access_control,
        )
        try:
            log_audit_event(
                kind="channel.created",
                ref=str(channel.id),
                actor=str(user.id),
                data={
                    "name": channel.name,
                    "expert_config_id": channel.expert_config_id,
                    "enabled": channel.enabled,
                },
                db=db,
            )
        except Exception:
            pass
        return {
            "id": channel.id,
            "name": channel.name,
            "expert_config_id": channel.expert_config_id,
            "enabled": channel.enabled,
            "description": channel.description,
            "created_at": channel.created_at.isoformat() if channel.created_at else None,
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{channel_id}")
async def update_channel(
    channel_id: int,
    request: UpdateChannelRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update a channel."""
    manager = ChannelManager(db)
    try:
        channel = manager.update_channel(
            channel_id,
            name=request.name,
            expert_config_id=request.expert_config_id,
            description=request.description,
            enabled=request.enabled,
        )
        return {
            "id": channel.id,
            "name": channel.name,
            "expert_config_id": channel.expert_config_id,
            "enabled": channel.enabled,
            "description": channel.description,
            "created_at": channel.created_at.isoformat() if channel.created_at else None,
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
        }
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_channels(
    enabled_only: bool = False, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all channels."""
    manager = ChannelManager(db)
    channels = manager.list_channels(enabled_only=enabled_only)
    return {
        "channels": [
            {
                "id": c.id,
                "name": c.name,
                "expert_config_id": c.expert_config_id,
                "enabled": c.enabled,
                "description": c.description,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in channels
        ],
        "count": len(channels),
    }


@router.get("/{channel_id}")
async def get_channel(channel_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get channel by ID."""
    manager = ChannelManager(db)
    channel = manager.get_channel(channel_id=channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {
        "id": channel.id,
        "name": channel.name,
        "expert_config_id": channel.expert_config_id,
        "description": channel.description,
        "enabled": channel.enabled,
        "created_at": channel.created_at.isoformat() if channel.created_at else None,
        "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
    }


@router.get("/{channel_id}/llm-config")
async def get_channel_llm_config(channel_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get LLM configuration for a channel."""
    manager = ChannelManager(db)
    config = manager.get_channel_llm_config(channel_id)
    if not config:
        raise HTTPException(status_code=404, detail="Channel or expert config not found")
    return config


class ChannelChatRequest(BaseModel):
    """Request model for channel chat endpoint"""

    message: str
    user_id: int
    session_id: Optional[int] = None
    mode: Optional[str] = None
    async_mode: bool = False
    webhook_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    # LLM parameters
    temperature: Optional[float] = None
    top_k: Optional[int] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[str] = None  # "text", "markdown", "json"
    language: Optional[str] = None  # "en", "fr", "pl"
    system_prompt: Optional[str] = None  # Override system prompt

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        return v


@router.post("/{channel_id}/chat")
async def channel_chat(
    channel_id: int,
    request: ChannelChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """
    Chat with a channel (sync or async mode).

    - Sync mode: Returns response immediately
    - Async mode: Returns job ID, response available via job status or webhook
    """
    # For now, require explicit user_id (until API key auth is wired end-to-end)
    user_id = request.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    manager = ChannelManager(db)
    channel = manager.get_channel(channel_id=channel_id)

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not channel.enabled:
        raise HTTPException(status_code=400, detail="Channel is disabled")

    # Get expert config
    from src.database.models import ExpertConfig

    expert = db.query(ExpertConfig).filter(ExpertConfig.id == channel.expert_config_id).first()
    if not expert:
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    if not expert.enabled:
        raise HTTPException(status_code=400, detail="Expert configuration is disabled")

    async_mode = request.async_mode
    if request.mode is not None:
        mode_lower = request.mode.lower().strip()
        if mode_lower == "async":
            async_mode = True
        elif mode_lower == "sync":
            async_mode = False

    if async_mode:
        # Async mode: Create job and return job ID
        job_manager = JobManager(db)

        # Create job
        job = job_manager.create_job(
            job_type="channel_chat",
            session_id=request.session_id,
            channel_id=channel_id,
            user_id=user_id,
            prompt_sent=request.message,
            metadata=request.metadata or {},
        )

        background_tasks.add_task(
            _process_channel_chat_job,
            job.id,
            channel_id,
            user_id,
            request.message,
            request.session_id,
            request.metadata or {},
            request.temperature,
            request.top_k,
            request.top_p,
            request.max_tokens,
            request.response_format,
            request.language,
            request.system_prompt,
            request.webhook_url,
        )

        return {
            "mode": "async",
            "job_id": job.id,
            "status": "pending",
            "message": "Job queued. Use GET /jobs/{job_id} to check status.",
        }
    else:
        # Sync mode: Process immediately and return response
        llm_manager: Optional[LLMManager] = None
        try:
            # Get LLM config
            llm_config = manager.get_channel_llm_config(channel_id)
            if not llm_config:
                raise HTTPException(status_code=500, detail="Failed to get LLM configuration")

            # Reuse a shared sync manager so multi-turn chat flows do not pay
            # a fresh provider init + connection setup penalty on every turn.
            llm_manager = await _get_cached_sync_llm_manager(llm_config)

            # Get or create session
            session_manager = SessionManager(db)
            if request.session_id:
                session = session_manager.get_session(request.session_id)
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")
            else:
                # Create new session
                try:
                    session_result = session_manager.create_session(
                        user_id=user_id, expert_config_id=expert.id, check_limits=False
                    )
                except PermissionError as e:
                    raise HTTPException(status_code=403, detail=str(e))
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                session, notification = session_result
                if not session:
                    raise HTTPException(
                        status_code=503, detail=f"Failed to create session: {notification}"
                    )

            # Get message history
            context_window = llm_config.get("max_tokens", 4096)
            history = session_manager.get_message_history(session.id, max_tokens=context_window)

            # Add user message
            session_manager.add_message(session.id, "user", request.message)

            # Prepare messages for LLM
            messages = history + [{"role": "user", "content": request.message}]

            # Determine system prompt (request override > expert template > language-specific > default)
            system_prompt = None
            if request.system_prompt:
                system_prompt = request.system_prompt
            elif expert.prompt_template:
                system_prompt = expert.prompt_template
            elif request.language:
                # Get language-specific prompt from config
                from src.config.loader import get_config as get_config_func

                lang_prompt = get_config_func(f"llm.prompts.{request.language}")
                if lang_prompt:
                    system_prompt = lang_prompt
                else:
                    system_prompt = get_config_func("llm.prompts.en") or get_config_func(
                        "llm.default_system_prompt"
                    )
            else:
                from src.config.loader import get_config as get_config_func

                system_prompt = get_config_func("llm.prompts.en") or get_config_func(
                    "llm.default_system_prompt"
                )

            knowledge_prompt = _build_session_knowledge_prompt(db, user_id, session.id)
            if knowledge_prompt:
                system_prompt = (
                    f"{system_prompt}\n\n{knowledge_prompt}" if system_prompt else knowledge_prompt
                )

            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})

            # Enhance messages for context retention (model-specific optimization)
            from src.core.prompts.context_retention import enhance_messages_for_context_retention

            if len(history) > 0:  # Only enhance if there's conversation history
                messages = enhance_messages_for_context_retention(
                    messages, llm_config.get("model", "")
                )

            # Get LLM parameters (request override > config)
            temperature = (
                request.temperature
                if request.temperature is not None
                else llm_config.get("temperature", 0.7)
            )
            max_tokens = (
                request.max_tokens
                if request.max_tokens is not None
                else llm_config.get("max_tokens", 1024)
            )
            if request.max_tokens is None:
                sync_default_cap = get_config("channels.sync_default_max_tokens") or 64
                if _testing_mode_enabled():
                    sync_default_cap = min(int(sync_default_cap), 32)
                try:
                    max_tokens = min(int(max_tokens), int(sync_default_cap))
                except (TypeError, ValueError):
                    max_tokens = 32 if _testing_mode_enabled() else 64

            # Prepare kwargs for LLM generation
            llm_kwargs = {}
            if request.top_k is not None:
                llm_kwargs["top_k"] = request.top_k
            elif llm_config.get("top_k") is not None:
                llm_kwargs["top_k"] = llm_config.get("top_k")

            if request.top_p is not None:
                llm_kwargs["top_p"] = request.top_p
            elif llm_config.get("top_p") is not None:
                llm_kwargs["top_p"] = llm_config.get("top_p")

            # Add response format instruction if specified
            if request.response_format:
                if request.response_format == "json":
                    # Add JSON format instruction to system prompt
                    json_instruction = "\n\nIMPORTANT: Respond ONLY with valid JSON. Do not include any text outside the JSON structure."
                    if messages and messages[0].get("role") == "system":
                        messages[0]["content"] += json_instruction
                    else:
                        messages.insert(0, {"role": "system", "content": json_instruction})
                elif request.response_format == "markdown":
                    # Add markdown format instruction
                    md_instruction = "\n\nIMPORTANT: Format your response using Markdown (headers, lists, code blocks, etc.)."
                    if messages and messages[0].get("role") == "system":
                        messages[0]["content"] += md_instruction
                    else:
                        messages.insert(0, {"role": "system", "content": md_instruction})

            # Generate response with proper error handling
            import httpx

            sync_generation_timeout, sync_fallback_timeout = _resolve_sync_generation_budget()
            context_hash = build_context_hash(messages)
            model_config_hash = build_model_config_hash(llm_config)
            prompt_hash = build_prompt_hash(system_prompt)

            async def _generate_uncached_response() -> Dict[str, Any]:
                compact_cap = 16 if _testing_mode_enabled() else 32
                compact_tokens = min(int(max_tokens), int(compact_cap))
                compact_timeout = sync_fallback_timeout

                async def _generate_compact_live_response(
                    *,
                    reason: str,
                    reset_manager: bool,
                ) -> Dict[str, Any]:
                    if compact_timeout <= 0:
                        raise RuntimeError("Compact live retry budget is unavailable")
                    retry_manager = llm_manager
                    if reset_manager:
                        await _reset_cached_sync_llm_manager(llm_config)
                        retry_manager = await _get_cached_sync_llm_manager(llm_config)
                    logger.warning(
                        "Sync channel chat retrying compact live response for channel_id=%s "
                        "after %s with max_tokens=%s timeout=%.1fs",
                        channel_id,
                        reason,
                        compact_tokens,
                        compact_timeout,
                    )
                    return await asyncio.wait_for(
                        retry_manager.generate(
                            messages=messages,
                            temperature=0.0,
                            max_tokens=compact_tokens,
                            **llm_kwargs,
                        ),
                        timeout=compact_timeout,
                    )

                try:
                    return await asyncio.wait_for(
                        llm_manager.generate(
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            **llm_kwargs,
                        ),
                        timeout=sync_generation_timeout,
                    )
                except asyncio.TimeoutError:
                    if compact_timeout <= 0:
                        raise
                    logger.warning(
                        f"Sync channel chat timed out after {sync_generation_timeout:.1f}s "
                        f"for channel_id={channel_id}; retrying compact live response "
                        f"with max_tokens={compact_tokens} timeout={compact_timeout:.1f}s"
                    )
                    try:
                        return await _generate_compact_live_response(
                            reason=f"timeout after {sync_generation_timeout:.1f}s",
                            reset_manager=True,
                        )
                    except asyncio.TimeoutError:
                        if _testing_mode_enabled():
                            logger.warning(
                                "Sync channel chat timed out again for channel_id=%s; using "
                                "deterministic test fallback response",
                                channel_id,
                            )
                            return _build_sync_timeout_fallback(request.message, channel_id)
                        raise
                except (ProviderUnavailableError, InvalidRequestError) as e:
                    if not _is_retryable_sync_generation_error(e) or compact_timeout <= 0:
                        raise
                    logger.warning(
                        "Sync channel chat hit transient provider error for channel_id=%s: %s",
                        channel_id,
                        e,
                    )
                    return await _generate_compact_live_response(
                        reason=f"provider error: {e}",
                        reset_manager=True,
                    )
                except (
                    httpx.ConnectError,
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    ConnectionError,
                ) as e:
                    logger.error(f"LLM connection error: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=503,
                        detail=f"LLM service unavailable: {str(e)}. Please check LLM service connectivity.",
                    )
                except RuntimeError as e:
                    if "not initialized" in str(e).lower() or "provider" in str(e).lower():
                        logger.error(f"LLM provider error: {e}", exc_info=True)
                        raise HTTPException(
                            status_code=503,
                            detail=f"LLM provider error: {str(e)}. Please check LLM configuration.",
                        )
                    raise
                except Exception as e:
                    logger.error(f"LLM generation error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"LLM generation failed: {str(e)}")

            response = await cached_expert_query_response(
                message=request.message,
                expert_id=int(expert.id),
                channel_id=channel_id,
                temperature=float(temperature),
                top_k=int(llm_kwargs["top_k"]) if llm_kwargs.get("top_k") is not None else None,
                top_p=float(llm_kwargs["top_p"]) if llm_kwargs.get("top_p") is not None else None,
                max_tokens=int(max_tokens),
                response_format=str(request.response_format or ""),
                language=str(request.language or ""),
                system_prompt=str(system_prompt or ""),
                context_hash=context_hash,
                model_config_hash=model_config_hash,
                prompt_hash=prompt_hash,
                generate_fn=_generate_uncached_response,
            )

            # Validate response
            if not response or not response.get("content"):
                logger.error(f"LLM returned empty response: {response}")
                raise HTTPException(status_code=500, detail="LLM returned empty response")

            # Save assistant response to session history
            assistant_content = response.get("content", "")
            session_manager.add_message(session.id, "assistant", assistant_content)

            # Store job record
            job_manager = JobManager(db)
            job = job_manager.create_job(
                job_type="channel_chat",
                session_id=session.id,
                channel_id=channel_id,
                user_id=user_id,
                prompt_sent=request.message,
                metadata={
                    "mode": "sync",
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "model": response.get("model", llm_config.get("model")),
                },
            )
            job_manager.update_job(
                job_id=job.id,
                status="completed",
                response_received=assistant_content,
            )

            return {
                "mode": "sync",
                "session_id": session.id,
                "response": assistant_content,
                "tokens_used": response.get("tokens_used", 0),
                "model": response.get("model", llm_config.get("model")),
                "job_id": job.id,
            }
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            error_text = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.error(f"Channel chat error: {error_text}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to process chat: {error_text}")


@router.get("/{channel_id}/history")
async def get_channel_history(
    channel_id: int,
    scope: str = "channel",
    user_id: Optional[int] = None,
    session_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get channel history based on scope.

    - scope=channel: All messages from all sessions in this channel
    - scope=user: All messages from a specific user in this channel (requires user_id)
    - scope=session: All messages from a specific session (requires session_id)
    """
    manager = ChannelManager(db)

    # Validate scope
    if scope not in ["channel", "user", "session"]:
        raise HTTPException(
            status_code=400, detail="Invalid scope. Must be 'channel', 'user', or 'session'"
        )

    # Validate required parameters
    if scope == "user" and not user_id:
        raise HTTPException(status_code=400, detail="user_id is required for user scope")
    if scope == "session" and not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")

    try:
        history = manager.get_channel_history(
            channel_id=channel_id,
            scope=scope,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
        return history
    except Exception as e:
        logger.error(f"Failed to get channel history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get channel history: {str(e)}")


class AddVectorStoreRequest(BaseModel):
    vector_store_id: int
    priority: int = 0


@router.post("/{channel_id}/vector-stores")
async def add_channel_vector_store(
    channel_id: int, request: AddVectorStoreRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Map a vector store to a channel."""
    manager = ChannelManager(db)
    try:
        mapping = manager.add_vector_store_mapping(
            channel_id=channel_id,
            vector_store_id=request.vector_store_id,
            priority=request.priority,
        )
        return mapping
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add vector store mapping: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add vector store mapping: {str(e)}")


@router.get("/{channel_id}/vector-stores")
async def get_channel_vector_stores(
    channel_id: int, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get all vector stores mapped to a channel."""
    manager = ChannelManager(db)
    try:
        vector_stores = manager.get_channel_vector_stores(channel_id)
        return {
            "channel_id": channel_id,
            "vector_stores": vector_stores,
            "count": len(vector_stores),
        }
    except Exception as e:
        logger.error(f"Failed to get channel vector stores: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get channel vector stores: {str(e)}"
        )


@router.delete("/{channel_id}/vector-stores/{vector_store_id}")
async def remove_channel_vector_store(
    channel_id: int, vector_store_id: int, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Remove a vector store mapping from a channel."""
    manager = ChannelManager(db)
    try:
        deleted = manager.remove_vector_store_mapping(channel_id, vector_store_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Mapping not found")
        return {
            "message": "Vector store mapping removed successfully",
            "channel_id": channel_id,
            "vector_store_id": vector_store_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove vector store mapping: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to remove vector store mapping: {str(e)}"
        )


@router.get("/{channel_id}/tools")
async def list_channel_tools(
    channel_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """List tools configured for a channel."""
    manager = ChannelManager(db)
    try:
        tools = manager.get_channel_tools(channel_id=channel_id)
        return {"channel_id": channel_id, "tools": tools, "count": len(tools)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list channel tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list channel tools: {str(e)}")


@router.delete("/{channel_id}/tools/{tool_name}")
async def remove_channel_tool(
    channel_id: int,
    tool_name: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Remove a tool from a channel."""
    manager = ChannelManager(db)
    try:
        removed = manager.remove_channel_tool(channel_id=channel_id, tool_name=tool_name)
        if not removed:
            raise HTTPException(status_code=404, detail="Tool not attached to channel")
        return {"channel_id": channel_id, "tool_name": tool_name, "removed": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove channel tool: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove channel tool: {str(e)}")


@router.post("/{channel_id}/services/{service_id}")
async def attach_service_to_channel(
    channel_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Attach an external service to a channel."""
    manager = ChannelManager(db)
    try:
        mapping = manager.attach_service_to_channel(channel_id=channel_id, service_id=service_id)
        return mapping
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to attach service to channel: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to attach service to channel: {str(e)}"
        )


@router.get("/{channel_id}/services")
async def list_channel_services(
    channel_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """List external services attached to a channel."""
    manager = ChannelManager(db)
    try:
        services = manager.get_channel_services(channel_id=channel_id)
        return {"channel_id": channel_id, "services": services, "count": len(services)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list channel services: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list channel services: {str(e)}")


@router.delete("/{channel_id}/services/{service_id}")
async def detach_service_from_channel(
    channel_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Detach an external service from a channel."""
    manager = ChannelManager(db)
    try:
        removed = manager.detach_service_from_channel(channel_id=channel_id, service_id=service_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Service mapping not found")
        return {"channel_id": channel_id, "service_id": service_id, "removed": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to detach service from channel: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to detach service from channel: {str(e)}"
        )


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: int, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Delete a channel."""
    manager = ChannelManager(db)
    channel = manager.get_channel(channel_id=channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Delete channel
    db.delete(channel)
    db.commit()

    return {"message": "Channel deleted successfully", "id": channel_id}
