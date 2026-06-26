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
LLM Validation Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: LLM validation testing endpoints

Related Requirements: FR1.29, UC1.23
Related Tasks: T116
Related Architecture: CC3.1.4
Related Tests: AT1.26

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel

from src.database.connection import get_db
from src.core.validation.llm_validator import LLMValidator
from src.core.prompts.generator import PromptGenerator
from src.servers.api.auth import require_permission, verify_api_key
from src.database.models import User

router = APIRouter(prefix="/validation", tags=["validation"], dependencies=[Depends(require_permission("expert:execute"))])


class ValidateLLMRequest(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key: Optional[str] = None
    prompt: Optional[str] = None


@router.post("/llm")
async def validate_llm(
    request: ValidateLLMRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Validate LLM configuration before channel activation."""
    validator = LLMValidator()
    try:
        results = await validator.validate_llm_config(
            provider=request.provider,
            base_url=request.base_url,
            model=request.model,
            api_key=request.api_key,
            prompt=request.prompt,
        )
        return {
            "success": results.get("success", False),
            "connectivity": results.get("connectivity", False),
            "prompt_rendering": results.get("prompt_rendering", False),
            "response_generation": results.get("response_generation", False),
            "errors": results.get("errors", []),
            "details": results.get("details", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


class ValidatePromptRequest(BaseModel):
    prompt: str
    requirements: Optional[list[str]] = None


@router.post("/prompt")
async def validate_prompt(
    request: ValidatePromptRequest,
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Validate a prompt against requirements using the configured LLM.

    This is the canonical REST entrypoint for AT1.45/AT1.46.
    """
    if not request.prompt or str(request.prompt).strip() == "":
        raise HTTPException(status_code=400, detail="prompt is required")
    generator = PromptGenerator()
    result = await generator.validate_prompt(
        prompt=request.prompt, requirements=request.requirements
    )
    return result
