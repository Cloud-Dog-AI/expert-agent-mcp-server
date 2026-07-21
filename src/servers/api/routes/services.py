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
External Service Registry Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: External service registry CRUD and health-check endpoints
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.audit.logger import log_audit_event
from src.core.security.redaction import merge_write_only_values, redact_sensitive_values
from src.core.service.manager import ServiceManager
from src.database.connection import get_db
from src.database.models import ExternalService, User
from src.servers.api.auth import require_permission, verify_admin

router = APIRouter(prefix="/services", tags=["services"], dependencies=[Depends(require_permission("expert:read"))])


class CreateServiceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    service_type: str = Field(min_length=1, max_length=100)
    endpoint_url: str = Field(min_length=1, max_length=500)
    auth_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateServiceRequest(BaseModel):
    endpoint_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    auth_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class TestServiceEndpointRequest(BaseModel):
    endpoint_url: str = Field(min_length=1, max_length=500)
    service_type: Optional[str] = Field(default=None, max_length=100)
    auth_config: Optional[Dict[str, Any]] = None


def _endpoint_auth_headers(auth_config: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Build the outbound probe header without returning secret material."""
    if not auth_config:
        return {}

    auth_type = str(auth_config.get("type") or "none").strip().lower()
    value = str(auth_config.get("value") or "").strip()
    if not value or auth_type == "none":
        return {}

    if auth_type == "bearer":
        scheme = str(auth_config.get("scheme") or "Bearer").strip()
        return {"Authorization": f"{scheme} {value}"}
    if auth_type in {"api_key", "custom_header"}:
        header_name = str(auth_config.get("header_name") or "X-API-Key").strip()
        scheme = str(auth_config.get("scheme") or "").strip()
        return {header_name: f"{scheme} {value}".strip()}
    return {}


def _serialize_service(service: ExternalService) -> Dict[str, Any]:
    expert_bindings = []
    for binding in service.service_bindings or []:
        expert = binding.expert_config
        expert_bindings.append(
            {
                "id": binding.id,
                "expert_id": binding.expert_config_id,
                "expert_name": expert.name if expert else None,
                "enabled": binding.enabled,
                "priority": binding.priority,
                "timeout_seconds": binding.timeout_seconds,
            }
        )
    auth_config = json.loads(service.auth_config_json) if service.auth_config_json else {}
    metadata = json.loads(service.metadata_json) if service.metadata_json else {}
    return {
        "id": service.id,
        "name": service.name,
        "service_type": service.type,
        "endpoint_url": service.endpoint_url,
        "health_status": service.health_status,
        "expert_bindings": expert_bindings,
        "auth_config": redact_sensitive_values(auth_config, extra_sensitive_keys={"value"}),
        "metadata": redact_sensitive_values(metadata),
        "usage_statistics": json.loads(service.usage_statistics_json)
        if service.usage_statistics_json
        else {},
        "created_at": service.created_at.isoformat() if service.created_at else None,
        "updated_at": service.updated_at.isoformat() if service.updated_at else None,
    }


 # Covers: FR1.19
@router.post("")
async def create_service(
    request: CreateServiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    manager = ServiceManager(db)
    try:
        service = manager.create_service(
            name=request.name,
            service_type=request.service_type,
            endpoint_url=request.endpoint_url,
            auth_config=merge_write_only_values(
                {}, request.auth_config, extra_sensitive_keys={"value"}
            ),
            metadata=merge_write_only_values({}, request.metadata),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        log_audit_event(
            kind="service.created",
            ref=str(service.id),
            actor=str(current_user.id),
            data={
                "name": service.name,
                "service_type": service.type,
                "endpoint_url": service.endpoint_url,
            },
            db=db,
        )
    except Exception:
        pass
    return _serialize_service(service)


@router.get("")
async def list_services(
    service_type: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    manager = ServiceManager(db)
    services = manager.list_services(service_type=service_type)
    return {"total": len(services), "services": [_serialize_service(s) for s in services]}


@router.post("/test-endpoint")
async def test_service_endpoint(
    request: TestServiceEndpointRequest,
    _: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Probe an endpoint from the service editor without persisting changes."""
    endpoint_url = request.endpoint_url.strip()
    parsed = urlparse(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Endpoint URL must use HTTP or HTTPS")

    service_type = str(request.service_type or "rest").strip().lower()
    manager = ServiceManager()
    try:
        response = await manager.client.get(
            endpoint_url,
            headers=_endpoint_auth_headers(request.auth_config),
            timeout=5.0,
        )
        healthy = response.status_code < 500
        return {
            "endpoint_url": endpoint_url,
            "resolved_url": str(response.url),
            "detected_type": service_type,
            "healthy": healthy,
            "health_status": "healthy" if healthy else "unhealthy",
            "status_code": response.status_code,
            "detail": f"Endpoint returned HTTP {response.status_code}",
        }
    except Exception as exc:
        return {
            "endpoint_url": endpoint_url,
            "resolved_url": endpoint_url,
            "detected_type": service_type,
            "healthy": False,
            "health_status": "unhealthy",
            "status_code": None,
            "detail": f"Endpoint probe failed: {type(exc).__name__}",
        }


@router.get("/{service_id}")
async def get_service(
    service_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    manager = ServiceManager(db)
    service = manager.get_service(service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return _serialize_service(service)


@router.put("/{service_id}")
async def update_service(
    service_id: int,
    request: UpdateServiceRequest,
    db: Session = Depends(get_db),
    _: User = Depends(verify_admin),
) -> Dict[str, Any]:
    service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    if request.endpoint_url is not None:
        service.endpoint_url = request.endpoint_url
    if request.auth_config is not None:
        existing_auth = json.loads(service.auth_config_json) if service.auth_config_json else {}
        service.auth_config_json = json.dumps(
            merge_write_only_values(
                existing_auth,
                request.auth_config,
                extra_sensitive_keys={"value"},
            )
        )
    if request.metadata is not None:
        existing_metadata = json.loads(service.metadata_json) if service.metadata_json else {}
        service.metadata_json = json.dumps(
            merge_write_only_values(existing_metadata, request.metadata)
        )
    db.commit()
    db.refresh(service)
    return _serialize_service(service)


@router.delete("/{service_id}")
async def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(verify_admin),
) -> Dict[str, Any]:
    service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return {"success": True, "id": service_id}


@router.post("/{service_id}/health")
async def check_service_health(
    service_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(verify_admin),
) -> Dict[str, Any]:
    manager = ServiceManager(db)
    service = manager.get_service(service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    healthy = await manager.check_health(service_id)
    db.refresh(service)
    return {"service_id": service_id, "healthy": healthy, "health_status": service.health_status}
