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
Expert Configuration Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Expert configuration endpoints

Related Requirements: FR1.1, FR1.12
Related Tasks: T007
Related Architecture: CC3.1.1
Related Tests: IT2.4

Recent Changes:
- Initial implementation
- Added DELETE endpoint for expert deletion
"""

import asyncio
from datetime import datetime, timezone
import json
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from cloud_dog_cache.invalidation import CONFIG_CHANGE, PROMPT_CHANGE, invalidate_event

from src.config import get_config
from src.database.connection import get_db
from src.common.a2a_client import publish_config_change_event
from src.core.expert.manager import ExpertManager
from src.core.execution.transactional import TransactionalExecutor
from src.core.security.redaction import merge_write_only_values, redact_sensitive_values
from src.core.service.composition import ServiceCompositionManager
from src.core.job.timeout_contract import resolve_execution_timeout_seconds
from src.core.audit.logger import log_audit_event
from src.database.models import ExternalService, Job, ServiceBinding, SubExpertBinding, User
from src.servers.api.auth import require_permission, verify_admin, verify_api_key
from src.utils.logger import get_logger

router = APIRouter(prefix="/experts", tags=["experts"], dependencies=[Depends(require_permission("experts:read"))])
logger = get_logger(__name__)

_ASYNC_EXPERT_RUNTIME_INSTANCE = uuid.uuid4().hex


def _utc_now() -> str:
    """Return a compact UTC timestamp for durable async-job metadata."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _async_expert_execution_timeout_seconds(
    parameters: Optional[Dict[str, Any]] = None,
) -> float:
    """Resolve the REST wrapper timeout while preserving a request budget."""
    configured = get_config(
        "expert.async_execution_timeout_seconds",
        get_config("mcp_server.async_job_execution_timeout_seconds"),
    )
    return resolve_execution_timeout_seconds(
        parameters,
        configured_timeout_seconds=configured,
    )


def _async_execution_error_info(exc: BaseException) -> Dict[str, str]:
    """Preserve exception type and causal chain when a provider supplies no text."""
    chain: List[str] = []
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen and len(chain) < 4:
        seen.add(id(current))
        detail = str(current).strip()
        chain.append(type(current).__name__ + (f": {detail}" if detail else ""))
        cause = current.__cause__ or current.__context__
        current = cause if isinstance(cause, BaseException) else None
    summary = " <- caused by ".join(chain) or type(exc).__name__
    return {
        "code": "EXPERT_ASYNC_EXECUTION_FAILED",
        "error": summary,
        "exception_type": type(exc).__name__,
    }


def reconcile_interrupted_async_expert_jobs() -> int:
    """Fail prior-process REST jobs that cannot resume after a worker replacement.

    FastAPI background tasks are process-local. A pending or processing job owned by
    an earlier runtime therefore has no executable worker after a restart and must
    be terminally recorded instead of remaining falsely in progress.
    """
    from src.core.job.manager import JobManager

    db_gen = get_db()
    db = next(db_gen)
    try:
        rows = (
            db.query(Job)
            .filter(Job.job_type == "expert_execute", Job.status.in_(("pending", "processing")))
            .all()
        )
        manager = JobManager(db)
        reconciled = 0
        for job in rows:
            try:
                metadata = json.loads(job.metadata_json) if job.metadata_json else {}
            except (TypeError, ValueError):
                metadata = {}
            owner = metadata.get("expert_async_runtime_instance") if isinstance(metadata, dict) else None
            if not owner or owner == _ASYNC_EXPERT_RUNTIME_INSTANCE:
                continue
            manager.update_job(
                job_id=job.id,
                status="failed",
                error_info={
                    "code": "EXPERT_ASYNC_EXECUTION_INTERRUPTED",
                    "error": "REST async expert execution was interrupted by a worker replacement. Retry the request.",
                    "previous_runtime_instance": str(owner),
                },
                metadata={
                    "expert_async_state": "interrupted",
                    "expert_async_interrupted_at": _utc_now(),
                },
            )
            reconciled += 1
        return reconciled
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# Keys of the per-expert LLM config carried inside llm_params_json. These are APPLIED at
# execution (transactional executor + agent adapters) and must be surfaced on every expert
# response so the WebUI expert form can display and round-trip them (FR-053).
_LLM_VIEW_KEYS = ("temperature", "top_k", "max_tokens", "num_ctx", "num_predict", "think")
ExpertToolEntry = Union[Dict[str, Any], str]


def _llm_view(llm_params_json: Optional[str]) -> Dict[str, Any]:
    """Surface the editable per-expert LLM settings from the stored llm_params JSON."""
    params: Dict[str, Any] = {}
    if llm_params_json:
        try:
            params = json.loads(llm_params_json) or {}
        except Exception:
            params = {}
    safe_params = redact_sensitive_values(params)
    view: Dict[str, Any] = {k: safe_params.get(k) for k in _LLM_VIEW_KEYS}
    view["llm_params"] = safe_params
    return view


def _merge_llm_config(llm_params: Optional[Dict[str, Any]], request: BaseModel) -> Dict[str, Any]:
    """Fold any top-level per-expert LLM settings (temperature/top_k/max_tokens/num_ctx/
    num_predict/think) into the llm_params dict so they are persisted in one place and
    APPLIED at execution (FR-053). Explicit llm_params keys win over the top-level mirror."""
    merged = merge_write_only_values({}, llm_params)
    for key in _LLM_VIEW_KEYS:
        val = getattr(request, key, None)
        if val is not None and key not in merged:
            merged[key] = val
    return merged


def _normalise_tool_entries(tools: Optional[List[ExpertToolEntry]]) -> Optional[List[ExpertToolEntry]]:
    """Validate and copy expert tool entries while preserving legacy string tools."""
    if tools is None:
        return None
    normalised: List[ExpertToolEntry] = []
    for idx, item in enumerate(tools):
        if isinstance(item, str):
            value = item.strip()
            if not value:
                raise ValueError(f"tools[{idx}] must not be empty")
            normalised.append(value)
            continue

        if not isinstance(item, dict):
            raise ValueError(f"tools[{idx}] must be a string or structured object")

        has_sub_expert = item.get("sub_expert_id") is not None
        has_service_tool = item.get("service") is not None or item.get("tool") is not None
        if has_sub_expert and has_service_tool:
            raise ValueError(
                f"tools[{idx}] must use either sub_expert_id or service/tool, not both"
            )
        if has_sub_expert:
            try:
                sub_expert_id = int(item["sub_expert_id"])
            except (TypeError, ValueError):
                raise ValueError(f"tools[{idx}].sub_expert_id must be an integer")
            if sub_expert_id <= 0:
                raise ValueError(f"tools[{idx}].sub_expert_id must be positive")
            copied: Dict[str, Any] = {"sub_expert_id": sub_expert_id}
            if item.get("name"):
                copied["name"] = str(item["name"]).strip()
            if item.get("description"):
                copied["description"] = str(item["description"]).strip()
            normalised.append(copied)
            continue

        service = item.get("service")
        tool = item.get("tool")
        if not isinstance(service, str) or not service.strip():
            raise ValueError(f"tools[{idx}].service is required")
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError(f"tools[{idx}].tool is required")

        copied = dict(item)
        copied["service"] = service.strip()
        copied["tool"] = tool.strip()
        for key in ("default_profile", "default_collection", "default_channel", "collection_template"):
            if key in copied and copied[key] is not None:
                if not isinstance(copied[key], str) or not copied[key].strip():
                    raise ValueError(f"tools[{idx}].{key} must be a non-empty string")
                copied[key] = copied[key].strip()
        if "arguments" in copied and copied["arguments"] is not None and not isinstance(copied["arguments"], dict):
            raise ValueError(f"tools[{idx}].arguments must be an object")
        if "description" in copied and copied["description"] is not None:
            copied["description"] = str(copied["description"]).strip()
        normalised.append(copied)
    return normalised


def _decode_tools_json(raw: Optional[str]) -> List[ExpertToolEntry]:
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except Exception:
        return []
    return items if isinstance(items, list) else []


class CreateExpertRequest(BaseModel):
    name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    llm_provider: Optional[str] = Field(default=None, min_length=1)
    llm_model: Optional[str] = Field(default=None, min_length=1)
    llm_base_url: Optional[str] = None
    llm_params: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None
    top_k: Optional[int] = None
    max_tokens: Optional[int] = None
    num_ctx: Optional[int] = None
    num_predict: Optional[int] = None
    think: Optional[bool] = None
    prompt_template: Optional[str] = None
    tools: Optional[List[ExpertToolEntry]] = None
    enabled: bool = True
    access_control: Optional[Dict[str, Any]] = None


@router.post("")
async def create_expert(
    request: CreateExpertRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Create a new expert configuration."""
    manager = ExpertManager(db)
    try:
        # Build llm_params dict: fold in the per-expert LLM config + optional base_url
        llm_params = _merge_llm_config(request.llm_params, request)
        if request.llm_base_url:
            llm_params["base_url"] = request.llm_base_url

        expert = manager.create_expert(
            name=request.name,
            title=request.title,
            description=request.description,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
            llm_params=llm_params if llm_params else None,
            prompt_template=request.prompt_template,
            tools=_normalise_tool_entries(request.tools),
            enabled=request.enabled,
            access_control=request.access_control,
        )
        try:
            log_audit_event(
                kind="expert.created",
                ref=str(expert.id),
                actor=None,
                data={"name": expert.name, "title": expert.title, "enabled": expert.enabled},
                db=db,
            )
        except Exception:
            pass
        publish_config_change_event(
            action="create",
            resource_type="expert",
            resource_id=int(expert.id),
            actor="system",
        )
        await invalidate_event(CONFIG_CHANGE)
        await invalidate_event(PROMPT_CHANGE)
        return {
            "id": expert.id,
            "name": expert.name,
            "title": expert.title,
            "description": expert.description,
            "llm_provider": expert.llm_provider,
            "llm_model": expert.llm_model,
            **_llm_view(expert.llm_params_json),
            "tools": _decode_tools_json(expert.tools_json),
            "enabled": expert.enabled,
            "created_at": expert.created_at.isoformat() if expert.created_at else None,
            "updated_at": expert.updated_at.isoformat() if expert.updated_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError as e:
        raise HTTPException(status_code=422, detail=f"Data integrity error: {str(e)}")


@router.get("")
async def list_experts(
    enabled_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """List all expert configurations."""
    manager = ExpertManager(db)
    experts = manager.list_experts(enabled_only=enabled_only, skip=skip, limit=limit)
    return {
        "experts": [
            {
                "id": e.id,
                "name": e.name,
                "title": e.title,
                "description": e.description,
                "llm_provider": e.llm_provider,
                "llm_model": e.llm_model,
                "tools": _decode_tools_json(e.tools_json),
                "enabled": e.enabled,
                **_llm_view(e.llm_params_json),
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in experts
        ],
        "count": len(experts),
    }


@router.get("/{expert_id}")
async def get_expert(
    expert_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get expert configuration by ID."""
    manager = ExpertManager(db)
    expert = manager.get_expert(expert_id=expert_id)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    llm_params = _llm_view(expert.llm_params_json)["llm_params"]

    access_control = {}
    if expert.access_control_json:
        try:
            access_control = json.loads(expert.access_control_json)
        except Exception:
            pass

    tools = _decode_tools_json(expert.tools_json)

    return {
        "id": expert.id,
        "name": expert.name,
        "title": expert.title,
        "description": expert.description,
        "llm_provider": expert.llm_provider,
        "llm_model": expert.llm_model,
        "llm_params": llm_params,
        "prompt_template": expert.prompt_template,
        "tools": tools,
        "enabled": expert.enabled,
        "access_control": access_control,
        "created_at": expert.created_at.isoformat() if expert.created_at else None,
        "updated_at": expert.updated_at.isoformat() if expert.updated_at else None,
    }


class UpdateExpertRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = Field(None, min_length=1)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_params: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None
    top_k: Optional[int] = None
    max_tokens: Optional[int] = None
    num_ctx: Optional[int] = None
    num_predict: Optional[int] = None
    think: Optional[bool] = None
    prompt_template: Optional[str] = None
    tools: Optional[List[ExpertToolEntry]] = None
    enabled: Optional[bool] = None
    access_control: Optional[Dict[str, Any]] = None


class BindServiceRequest(BaseModel):
    service_id: int
    enabled: bool = True
    timeout_seconds: Optional[int] = None
    priority: int = 100
    circuit_breaker_threshold: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class BindSubExpertRequest(BaseModel):
    sub_expert_id: int
    enabled: bool = True
    max_depth: int = 3
    delegation_prompt: Optional[str] = None


class ExecuteExpertRequest(BaseModel):
    input_text: str
    parameters: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    # EXPWEB-029: the WebUI Test Query popup submits the execution as an async job so
    # it can render job/progress and poll GET /jobs/{id}. Default async for browser
    # callers (no explicit sync request) while keeping the synchronous contract for
    # API clients that omit the flag and don't want a job.
    async_mode: Optional[bool] = None
    mode: Optional[str] = None


def _serialize_service_binding(
    binding: ServiceBinding, tools: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    service = binding.service
    return {
        "id": binding.id,
        "expert_config_id": binding.expert_config_id,
        "service_id": binding.service_id,
        "enabled": binding.enabled,
        "timeout_seconds": binding.timeout_seconds,
        "priority": binding.priority,
        "circuit_breaker_threshold": binding.circuit_breaker_threshold,
        "service": {
            "id": service.id if service else None,
            "name": service.name if service else None,
            "service_type": service.type if service else None,
            "endpoint_url": service.endpoint_url if service else None,
            "health_status": service.health_status if service else None,
        },
        "tools": tools or [],
    }


def _serialize_sub_expert_binding(binding: SubExpertBinding) -> Dict[str, Any]:
    child = binding.child_expert
    return {
        "id": binding.id,
        "parent_expert_id": binding.parent_expert_id,
        "sub_expert_id": binding.child_expert_id,
        "enabled": binding.enabled,
        "max_depth": binding.max_depth,
        "delegation_prompt": binding.delegation_prompt,
        "sub_expert": {
            "id": child.id if child else None,
            "name": child.name if child else None,
            "title": child.title if child else None,
        },
    }


@router.put("/{expert_id}")
async def update_expert(
    expert_id: int,
    request: UpdateExpertRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Update an expert configuration."""
    manager = ExpertManager(db)
    try:
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.title is not None:
            update_data["title"] = request.title
        if request.description is not None:
            update_data["description"] = request.description
        if request.llm_provider is not None:
            update_data["llm_provider"] = request.llm_provider
        if request.llm_model is not None:
            update_data["llm_model"] = request.llm_model
        if request.prompt_template is not None:
            update_data["prompt_template"] = request.prompt_template
        if request.enabled is not None:
            update_data["enabled"] = request.enabled
        if request.access_control is not None:
            update_data["access_control"] = request.access_control
        if request.tools is not None:
            update_data["tools"] = _normalise_tool_entries(request.tools)

        # Per-expert LLM config: MERGE incoming settings into the existing llm_params so
        # stored keys (base_url / api_key) are preserved across partial edits (FR-053).
        llm_cfg_present = (
            request.llm_params is not None
            or request.llm_base_url is not None
            or any(getattr(request, k) is not None for k in _LLM_VIEW_KEYS)
        )
        if llm_cfg_present:
            existing = manager.get_expert(expert_id=expert_id)
            merged: Dict[str, Any] = {}
            if existing and existing.llm_params_json:
                try:
                    merged = json.loads(existing.llm_params_json) or {}
                except Exception:
                    merged = {}
            merged = merge_write_only_values(merged, request.llm_params)
            for key in _LLM_VIEW_KEYS:
                val = getattr(request, key, None)
                if val is not None:
                    merged[key] = val
            if request.llm_base_url:
                merged["base_url"] = request.llm_base_url
            update_data["llm_params"] = merged

        expert = manager.update_expert(expert_id, **update_data)
        if not expert:
            raise HTTPException(status_code=404, detail="Expert configuration not found")
        try:
            log_audit_event(
                kind="expert.updated",
                ref=str(expert_id),
                actor=None,
                data={"updated_fields": list(update_data.keys())},
                db=db,
            )
        except Exception:
            pass

        publish_config_change_event(
            action="update",
            resource_type="expert",
            resource_id=int(expert.id),
            actor="system",
        )
        await invalidate_event(CONFIG_CHANGE)
        await invalidate_event(PROMPT_CHANGE)
        return {
            "id": expert.id,
            "name": expert.name,
            "title": expert.title,
            "description": expert.description,
            "llm_provider": expert.llm_provider,
            "llm_model": expert.llm_model,
            **_llm_view(expert.llm_params_json),
            "tools": _decode_tools_json(expert.tools_json),
            "enabled": expert.enabled,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{expert_id}")
async def delete_expert(
    expert_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Delete an expert configuration."""
    manager = ExpertManager(db)
    expert = manager.get_expert(expert_id=expert_id)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    # Delete expert
    db.delete(expert)
    db.commit()
    try:
        log_audit_event(
            kind="expert.deleted",
            ref=str(expert_id),
            actor=None,
            data={"name": expert.name},
            db=db,
        )
    except Exception:
        pass
    publish_config_change_event(
        action="delete",
        resource_type="expert",
        resource_id=int(expert_id),
        actor="system",
    )
    await invalidate_event(CONFIG_CHANGE)
    await invalidate_event(PROMPT_CHANGE)

    return {"message": "Expert configuration deleted successfully", "id": expert_id}


@router.get("/{expert_id}/services")
async def list_expert_services(
    expert_id: int,
    include_tools: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    manager = ExpertManager(db)
    if not manager.get_expert(expert_id=expert_id):
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    composition = ServiceCompositionManager(db)
    bindings = (
        db.query(ServiceBinding)
        .filter(ServiceBinding.expert_config_id == expert_id)
        .order_by(ServiceBinding.priority.asc(), ServiceBinding.id.asc())
        .all()
    )
    services: List[Dict[str, Any]] = []
    for binding in bindings:
        tools = (
            await composition.discover_tools(binding.service_id)
            if include_tools
            else composition.get_cached_tools(binding.service_id)
        )
        services.append(_serialize_service_binding(binding, tools=tools))
    return {"expert_id": expert_id, "services": services, "count": len(services)}


@router.post("/{expert_id}/services")
async def bind_expert_service(
    expert_id: int,
    request: BindServiceRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    manager = ExpertManager(db)
    if not manager.get_expert(expert_id=expert_id):
        raise HTTPException(status_code=404, detail="Expert configuration not found")
    if not db.query(ExternalService).filter(ExternalService.id == request.service_id).first():
        raise HTTPException(status_code=404, detail="Service not found")

    binding = (
        db.query(ServiceBinding)
        .filter(
            ServiceBinding.expert_config_id == expert_id,
            ServiceBinding.service_id == request.service_id,
        )
        .first()
    )
    if binding is None:
        binding = ServiceBinding(expert_config_id=expert_id, service_id=request.service_id)
        db.add(binding)

    binding.enabled = request.enabled
    binding.timeout_seconds = request.timeout_seconds
    binding.priority = request.priority
    binding.circuit_breaker_threshold = request.circuit_breaker_threshold
    binding.metadata_json = json.dumps(request.metadata or {})
    db.commit()
    db.refresh(binding)
    return _serialize_service_binding(binding)


@router.delete("/{expert_id}/services/{service_id}")
async def unbind_expert_service(
    expert_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    binding = (
        db.query(ServiceBinding)
        .filter(
            ServiceBinding.expert_config_id == expert_id,
            ServiceBinding.service_id == service_id,
        )
        .first()
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Service binding not found")
    db.delete(binding)
    db.commit()
    return {"success": True, "expert_id": expert_id, "service_id": service_id}


class BatchServicesRequest(BaseModel):
    service_ids: List[int] = Field(default_factory=list)


@router.put("/{expert_id}/services/batch")
async def batch_set_expert_services(
    expert_id: int,
    request: BatchServicesRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Replace the expert's service bindings with exactly ``service_ids``.

    The WebUI Expert form persists the full checkbox selection in one call
    (EXPWEB-026). Adds missing bindings, removes bindings not in the set, and
    returns the resulting binding list so the form can re-render the count.
    """
    manager = ExpertManager(db)
    if not manager.get_expert(expert_id=expert_id):
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    desired = list(dict.fromkeys(request.service_ids))  # de-dupe, preserve order
    valid_ids = {
        row.id
        for row in db.query(ExternalService.id).filter(ExternalService.id.in_(desired)).all()
    } if desired else set()

    existing = (
        db.query(ServiceBinding)
        .filter(ServiceBinding.expert_config_id == expert_id)
        .all()
    )
    existing_ids = {b.service_id for b in existing}

    for binding in existing:
        if binding.service_id not in valid_ids:
            db.delete(binding)

    for sid in desired:
        if sid in valid_ids and sid not in existing_ids:
            db.add(ServiceBinding(expert_config_id=expert_id, service_id=sid, enabled=True))

    db.commit()

    bindings = (
        db.query(ServiceBinding)
        .filter(ServiceBinding.expert_config_id == expert_id)
        .order_by(ServiceBinding.id.asc())
        .all()
    )
    services = [_serialize_service_binding(binding) for binding in bindings]
    return {"expert_id": expert_id, "services": services, "count": len(services)}


@router.get("/{expert_id}/sub-experts")
async def list_sub_experts(
    expert_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    bindings = (
        db.query(SubExpertBinding)
        .filter(SubExpertBinding.parent_expert_id == expert_id)
        .order_by(SubExpertBinding.id.asc())
        .all()
    )
    payload = [_serialize_sub_expert_binding(binding) for binding in bindings]
    return {"expert_id": expert_id, "sub_experts": payload, "count": len(payload)}


@router.post("/{expert_id}/sub-experts")
async def bind_sub_expert(
    expert_id: int,
    request: BindSubExpertRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    manager = ExpertManager(db)
    if not manager.get_expert(expert_id=expert_id) or not manager.get_expert(
        expert_id=request.sub_expert_id
    ):
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    binding = (
        db.query(SubExpertBinding)
        .filter(
            SubExpertBinding.parent_expert_id == expert_id,
            SubExpertBinding.child_expert_id == request.sub_expert_id,
        )
        .first()
    )
    if binding is None:
        binding = SubExpertBinding(
            parent_expert_id=expert_id, child_expert_id=request.sub_expert_id
        )
        db.add(binding)

    binding.enabled = request.enabled
    binding.max_depth = request.max_depth
    binding.delegation_prompt = request.delegation_prompt
    db.commit()
    db.refresh(binding)
    return _serialize_sub_expert_binding(binding)


@router.delete("/{expert_id}/sub-experts/{sub_id}")
async def unbind_sub_expert(
    expert_id: int,
    sub_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    binding = (
        db.query(SubExpertBinding)
        .filter(
            SubExpertBinding.parent_expert_id == expert_id,
            SubExpertBinding.child_expert_id == sub_id,
        )
        .first()
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Sub-expert binding not found")
    db.delete(binding)
    db.commit()
    return {"success": True, "expert_id": expert_id, "sub_expert_id": sub_id}


class BatchSubExpertsRequest(BaseModel):
    sub_expert_ids: List[int] = Field(default_factory=list)


@router.put("/{expert_id}/sub-experts/batch")
async def batch_set_expert_sub_experts(
    expert_id: int,
    request: BatchSubExpertsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Replace the expert's sub-expert bindings with exactly ``sub_expert_ids``.

    Mirrors the services batch-set so the WebUI Expert form persists the whole
    sub-expert checkbox selection in one call (EXPWEB-026).
    """
    from src.database.models import ExpertConfig

    manager = ExpertManager(db)
    if not manager.get_expert(expert_id=expert_id):
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    desired = [sid for sid in dict.fromkeys(request.sub_expert_ids) if sid != expert_id]
    valid_ids = {
        row.id
        for row in db.query(ExpertConfig.id).filter(ExpertConfig.id.in_(desired)).all()
    } if desired else set()

    existing = (
        db.query(SubExpertBinding)
        .filter(SubExpertBinding.parent_expert_id == expert_id)
        .all()
    )
    existing_ids = {b.child_expert_id for b in existing}

    for binding in existing:
        if binding.child_expert_id not in valid_ids:
            db.delete(binding)

    for sid in desired:
        if sid in valid_ids and sid not in existing_ids:
            db.add(SubExpertBinding(parent_expert_id=expert_id, child_expert_id=sid))

    db.commit()

    bindings = (
        db.query(SubExpertBinding)
        .filter(SubExpertBinding.parent_expert_id == expert_id)
        .order_by(SubExpertBinding.id.asc())
        .all()
    )
    sub_experts = [_serialize_sub_expert_binding(binding) for binding in bindings]
    return {"expert_id": expert_id, "sub_experts": sub_experts, "count": len(sub_experts)}


async def _process_expert_execute_job(
    job_id: int,
    expert_id: int,
    input_text: str,
    parameters: Dict[str, Any],
    context: Dict[str, Any],
    auth_context: Dict[str, Any],
) -> None:
    """Background runner for an async expert execution (EXPWEB-029).

    Uses its own DB session (background tasks outlive the request-scoped session),
    runs the transactional executor, and records the result on the job so the WebUI
    Test Query popup can poll GET /jobs/{id} for progress and the final response.
    """
    from src.core.job.manager import JobManager

    db_gen = get_db()
    db = next(db_gen)
    job_manager = JobManager(db)
    started_at = _utc_now()
    started_monotonic = time.monotonic()
    timeout_seconds = _async_expert_execution_timeout_seconds(parameters)
    try:
        job_manager.update_job(
            job_id=job_id,
            status="processing",
            metadata={
                "expert_async_state": "running",
                "expert_async_runtime_instance": _ASYNC_EXPERT_RUNTIME_INSTANCE,
                "expert_async_started_at": started_at,
                "expert_async_timeout_seconds": timeout_seconds,
            },
        )
        executor = TransactionalExecutor(db)
        result = await asyncio.wait_for(
            executor.execute(
                expert_id=expert_id,
                input_text=input_text,
                parameters=parameters,
                context=context,
                auth_context=auth_context,
            ),
            timeout=timeout_seconds,
        )
        current_job = job_manager.get_job(job_id)
        if current_job and str(current_job.status or "").lower() == "cancelled":
            return
        job_manager.update_job(
            job_id=job_id,
            status="completed",
            response_received=json.dumps(result) if not isinstance(result, str) else result,
            metadata={
                "expert_async_state": "completed",
                "expert_async_finished_at": _utc_now(),
                "expert_async_duration_ms": int((time.monotonic() - started_monotonic) * 1000),
            },
        )
    except asyncio.TimeoutError:
        job_manager.update_job(
            job_id=job_id,
            status="timed_out",
            error_info={
                "code": "EXPERT_ASYNC_EXECUTION_TIMEOUT",
                "error": f"REST async expert execution exceeded {timeout_seconds:g} seconds",
            },
            metadata={
                "expert_async_state": "timed_out",
                "expert_async_finished_at": _utc_now(),
                "expert_async_duration_ms": int((time.monotonic() - started_monotonic) * 1000),
            },
        )
    except asyncio.CancelledError:
        job_manager.update_job(
            job_id=job_id,
            status="failed",
            error_info={
                "code": "EXPERT_ASYNC_EXECUTION_INTERRUPTED",
                "error": "REST async expert execution was cancelled before completion",
            },
            metadata={
                "expert_async_state": "interrupted",
                "expert_async_interrupted_at": _utc_now(),
            },
        )
        raise
    except Exception as exc:  # execution failure is surfaced on the durable job
        error_info = _async_execution_error_info(exc)
        job_manager.update_job(
            job_id=job_id,
            status="failed",
            error_info=error_info,
            metadata={
                "expert_async_state": "failed",
                "expert_async_finished_at": _utc_now(),
                "expert_async_duration_ms": int((time.monotonic() - started_monotonic) * 1000),
                "expert_async_error_type": error_info["exception_type"],
            },
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.post("/{expert_id}/execute")
async def execute_expert(
    expert_id: int,
    request: ExecuteExpertRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    manager = ExpertManager(db)
    if not manager.get_expert(expert_id=expert_id):
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    auth_context = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }

    # EXPWEB-029: resolve execution mode. Explicit async_mode / mode wins; otherwise a
    # browser context (Test Query popup passes context.user_id) defaults to async so the
    # WebUI can render job/progress. Pure-sync API callers keep the transactional result.
    async_mode = request.async_mode
    if request.mode is not None:
        mode_lower = request.mode.lower().strip()
        if mode_lower == "async":
            async_mode = True
        elif mode_lower in ("sync", "transactional"):
            async_mode = False
    if async_mode is None:
        async_mode = bool(request.context and request.context.get("user_id") is not None)

    if async_mode:
        from src.core.job.manager import JobManager

        job_manager = JobManager(db)
        job = job_manager.create_job(
            job_type="expert_execute",
            user_id=current_user.id,
            prompt_sent=request.input_text,
            metadata={
                "expert_id": expert_id,
                "expert_async_state": "queued",
                "expert_async_runtime_instance": _ASYNC_EXPERT_RUNTIME_INSTANCE,
                "expert_async_accepted_at": _utc_now(),
            },
        )
        background_tasks.add_task(
            _process_expert_execute_job,
            job.id,
            expert_id,
            request.input_text,
            request.parameters or {},
            request.context or {},
            auth_context,
        )
        return {
            "mode": "async",
            "job_id": job.id,
            "status": "pending",
            "message": "Job queued. Use GET /jobs/{job_id} to check status.",
        }

    executor = TransactionalExecutor(db)
    return await executor.execute(
        expert_id=expert_id,
        input_text=request.input_text,
        parameters=request.parameters or {},
        context=request.context or {},
        auth_context=auth_context,
    )
