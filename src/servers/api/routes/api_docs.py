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
API Documentation Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Developer API documentation and examples

Related Requirements: FR1.24, UC1.18
Related Tasks: T062
Related Architecture: CC1.1.1
Related Tests: AT1.19

Recent Changes:
- Initial implementation
"""

from fastapi import Depends, APIRouter
from typing import Dict, Any
from src.servers.api.auth import require_permission

router = APIRouter(prefix="/docs", tags=["documentation"], dependencies=[Depends(require_permission("expert:read"))])


def _api_docs_payload() -> Dict[str, Any]:
    """Build API documentation summary payload."""
    return {
        "title": "Expert Agent MCP Server API",
        "version": "0.1.0",
        "description": "RESTful API for Expert Agent MCP Server",
        "endpoints": {
            "health": "/health",
            "sessions": "/sessions",
            "users": "/users",
            "experts": "/experts",
            "channels": "/channels",
            "openapi": "/openapi.json",
            "swagger": "/docs",
            "redoc": "/redoc",
        },
        "authentication": {
            "type": "API Key",
            "header": "X-API-Key",
            "description": "Include API key in X-API-Key header",
        },
        "examples": {
            "create_session": {
                "method": "POST",
                "url": "/sessions",
                "body": {"user_id": 1, "expert_config_id": 1, "title": "My Session"},
            },
            "create_user": {
                "method": "POST",
                "url": "/users",
                "body": {
                    "username": "user1",
                    "email": "user1@example.com",
                    "password": "secure_password",
                },
            },
            "create_expert": {
                "method": "POST",
                "url": "/experts",
                "body": {
                    "name": "tech_expert",
                    "title": "Technical Expert",
                    "llm_provider": "ollama",
                    "llm_model": "qwen3:14b",
                },
            },
        },
    }


@router.get("/api")
async def api_documentation() -> Dict[str, Any]:
    """Get API documentation summary."""
    return _api_docs_payload()


@router.get("/routes")
async def api_routes_summary() -> Dict[str, Any]:
    """
    Backward-compatible route summary endpoint.

    Some environments and smoke checks call `/docs/routes` directly.
    Keep this alias stable and include the most-used route keys.
    """
    docs = _api_docs_payload()
    endpoints = docs.get("endpoints", {})
    return {
        "service": "Expert Agent MCP Server API",
        "version": docs.get("version"),
        "health": endpoints.get("health"),
        "sessions": endpoints.get("sessions"),
        "users": endpoints.get("users"),
        "experts": endpoints.get("experts"),
        "channels": endpoints.get("channels"),
        "openapi": endpoints.get("openapi"),
        "swagger": endpoints.get("swagger"),
        "redoc": endpoints.get("redoc"),
        "mcp_chat": "/mcp/chat",
        "mcp_health": "/mcp/health",
        "a2a_health": "/a2a/health",
    }
