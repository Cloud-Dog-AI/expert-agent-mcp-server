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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Dict, Any, List, Optional
import json
from pydantic import BaseModel, Field
from cloud_dog_cache.invalidation import CONFIG_CHANGE, PROMPT_CHANGE, invalidate_event

from src.database.connection import get_db
from src.common.a2a_client import publish_config_change_event
from src.core.expert.manager import ExpertManager
from src.core.execution.transactional import TransactionalExecutor
from src.core.service.composition import ServiceCompositionManager
from src.core.audit.logger import log_audit_event
from src.database.models import ExternalService, ServiceBinding, SubExpertBinding, User
from src.servers.api.auth import require_permission, verify_admin, verify_api_key

router = APIRouter(prefix="/experts", tags=["experts"], dependencies=[Depends(require_permission("experts:read"))])


class CreateExpertRequest(BaseModel):
    name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    llm_provider: Optional[str] = Field(default=None, min_length=1)
    llm_model: Optional[str] = Field(default=None, min_length=1)
    llm_base_url: Optional[str] = None
    llm_params: Optional[Dict[str, Any]] = None
    prompt_template: Optional[str] = None
    tools: Optional[List[str]] = None
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
        # Build llm_params dict if llm_base_url is provided
        llm_params = request.llm_params or {}
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
            tools=request.tools,
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
                "enabled": e.enabled,
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

    llm_params = {}
    if expert.llm_params_json:
        try:
            llm_params = json.loads(expert.llm_params_json)
        except Exception:
            pass

    access_control = {}
    if expert.access_control_json:
        try:
            access_control = json.loads(expert.access_control_json)
        except Exception:
            pass

    tools: List[str] = []
    if expert.tools_json:
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
    prompt_template: Optional[str] = None
    tools: Optional[List[str]] = None
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
            update_data["tools"] = request.tools

        # Handle llm_params with base_url
        if request.llm_params is not None or request.llm_base_url is not None:
            llm_params = request.llm_params or {}
            if request.llm_base_url:
                llm_params["base_url"] = request.llm_base_url
            update_data["llm_params"] = llm_params

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

        llm_params = {}
        if expert.llm_params_json:
            try:
                llm_params = json.loads(expert.llm_params_json)
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
            "llm_params": llm_params,
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


@router.post("/{expert_id}/execute")
async def execute_expert(
    expert_id: int,
    request: ExecuteExpertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    manager = ExpertManager(db)
    if not manager.get_expert(expert_id=expert_id):
        raise HTTPException(status_code=404, detail="Expert configuration not found")

    executor = TransactionalExecutor(db)
    return await executor.execute(
        expert_id=expert_id,
        input_text=request.input_text,
        parameters=request.parameters or {},
        context=request.context or {},
        auth_context={
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    )
