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
Prompt Generation Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Prompt and test case generation endpoints

Related Requirements: FR1.15, FR1.28, UC1.9, UC1.22
Related Tasks: T053, T115
Related Architecture: CC3.1.4
Related Tests: AT1.15, AT1.25

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from cloud_dog_cache.invalidation import PROMPT_CHANGE, invalidate_event

from src.core.audit.logger import log_audit_event
from src.database.connection import get_db
from src.core.prompt.manager import PromptManager
from src.core.prompts.generator import PromptGenerator
from src.servers.api.auth import require_permission, verify_api_key
from src.database.models import User

router = APIRouter(prefix="/prompts", tags=["prompts"], dependencies=[Depends(require_permission("experts:read"))])


def get_prompt_store() -> Optional[Any]:
    """Opt-in shared prompt store provider (W28B-319 / D5).

    Returns ``None`` by default, so prompt template CRUD keeps using the
    service-local DB-backed path with no behavioural change. A deployment that
    wants to back CRUD with ``cloud_dog_agent.prompts.PromptStore`` overrides
    this dependency (``app.dependency_overrides[get_prompt_store] = ...``) to
    return a store instance; only then is the shared store consulted.
    """
    return None


class GeneratePromptRequest(BaseModel):
    title: str
    details: str
    context_type: Optional[str] = None
    expected_outcomes: Optional[str] = None
    available_tools: Optional[List[str]] = None


class GenerateTestCasesRequest(BaseModel):
    title: Optional[str] = None
    details: Optional[str] = None
    prompt: str
    context_type: Optional[str] = None
    expected_outcomes: Optional[str] = None
    num_cases: int = 5


class ValidatePromptRequest(BaseModel):
    prompt: str
    requirements: Optional[List[str]] = None


class PromptTemplateRequest(BaseModel):
    name: str
    content: str
    variables_schema: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None


class PromptTemplateUpdateRequest(BaseModel):
    content: Optional[str] = None
    variables_schema: Optional[Dict[str, Any]] = None


class PromptTestRunRequest(BaseModel):
    expert_id: Optional[int] = None
    input_text: str
    variables: Optional[Dict[str, Any]] = None


def _serialize_template(template) -> Dict[str, Any]:
    import json

    return {
        "id": template.id,
        "name": template.name,
        "version": template.version,
        "content": template.content,
        "variables_schema": json.loads(template.variables_schema) if template.variables_schema else {},
        "created_by": template.created_by,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


@router.post("/generate")
async def generate_prompt(
    request: GeneratePromptRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Generate a prompt from expert description."""
    generator = PromptGenerator()
    try:
        result = await generator.generate_prompt(
            title=request.title,
            details=request.details,
            context_type=request.context_type,
            expected_outcomes=request.expected_outcomes,
            available_tools=request.available_tools,
        )
        return {
            "success": True,
            "prompt": result.get("prompt", ""),
            "temperature": result.get("temperature", 0.7),
            "max_tokens": result.get("max_tokens", 1024),
            "tool_recommendations": result.get("tool_recommendations", []),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate prompt: {str(e)}")


@router.post("/test-cases")
async def generate_test_cases(
    request: GenerateTestCasesRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Generate test cases for expert configuration."""
    generator = PromptGenerator()
    try:
        title = request.title or "Prompt template"
        details = request.details or request.prompt
        test_cases = await generator.generate_test_cases(
            title=title,
            details=details,
            prompt=request.prompt,
            context_type=request.context_type,
            expected_outcomes=request.expected_outcomes,
            num_cases=request.num_cases,
        )
        return {"success": True, "test_cases": test_cases, "items": test_cases, "count": len(test_cases)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate test cases: {str(e)}")


@router.post("/validate")
async def validate_prompt(
    request: ValidatePromptRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Validate a prompt against requirements."""
    generator = PromptGenerator()
    try:
        result = await generator.validate_prompt(
            prompt=request.prompt, requirements=request.requirements
        )
        is_valid = bool(result.get("is_valid", result.get("valid", True)))
        return {
            "success": True,
            "is_valid": is_valid,
            "valid": is_valid,
            "score": result.get("score", 0),
            "strengths": result.get("strengths", []),
            "weaknesses": result.get("weaknesses", []),
            "recommendations": result.get("recommendations", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate prompt: {str(e)}")


@router.get("")
async def list_prompt_templates(
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
    store: Optional[Any] = Depends(get_prompt_store),
) -> Dict[str, Any]:
    manager = PromptManager(db, store=store)
    templates = manager.list_prompt_templates()
    return {"count": len(templates), "prompts": [_serialize_template(t) for t in templates]}


@router.post("")
async def create_prompt_template(
    request: PromptTemplateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
    store: Optional[Any] = Depends(get_prompt_store),
) -> Dict[str, Any]:
    manager = PromptManager(db, store=store)
    template = manager.create_prompt_template(
        name=request.name,
        content=request.content,
        variables_schema=request.variables_schema,
        created_by=request.created_by or user.username,
    )
    try:
        log_audit_event(
            kind="prompt.created",
            ref=str(template.id),
            actor=str(user.id),
            data={
                "name": template.name,
                "version": template.version,
                "created_by": template.created_by,
            },
            db=db,
        )
    except Exception:
        pass
    await invalidate_event(PROMPT_CHANGE)
    return _serialize_template(template)


@router.get("/{prompt_id}")
async def get_prompt_template(
    prompt_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
    store: Optional[Any] = Depends(get_prompt_store),
) -> Dict[str, Any]:
    manager = PromptManager(db, store=store)
    template = manager.get_prompt_template(prompt_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    await invalidate_event(PROMPT_CHANGE)
    return _serialize_template(template)


@router.put("/{prompt_id}")
async def update_prompt_template(
    prompt_id: int,
    request: PromptTemplateUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
    store: Optional[Any] = Depends(get_prompt_store),
) -> Dict[str, Any]:
    manager = PromptManager(db, store=store)
    template = manager.update_prompt_template(
        prompt_id,
        content=request.content,
        variables_schema=request.variables_schema,
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return _serialize_template(template)


@router.delete("/{prompt_id}")
async def delete_prompt_template(
    prompt_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
    store: Optional[Any] = Depends(get_prompt_store),
) -> Dict[str, Any]:
    manager = PromptManager(db, store=store)
    if not manager.delete_prompt_template(prompt_id):
        raise HTTPException(status_code=404, detail="Prompt template not found")
    await invalidate_event(PROMPT_CHANGE)
    return {"success": True, "id": prompt_id}


@router.post("/{prompt_id}/test")
async def test_prompt_template(
    prompt_id: int,
    request: PromptTestRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    manager = PromptManager(db)
    template = manager.get_prompt_template(prompt_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    variables = request.variables or {}
    if request.expert_id is not None:
        variables.update(
            manager.build_prompt_variables(
                request.expert_id,
                user={"id": user.id, "username": user.username, "role": user.role},
                session={"mode": "prompt-test"},
            )
        )
    rendered = manager.render_template(template.content, variables)
    return {
        "prompt_id": prompt_id,
        "rendered_prompt": rendered,
        "input_text": request.input_text,
        "preview": f"{rendered}\n\nUser Input:\n{request.input_text}",
    }
