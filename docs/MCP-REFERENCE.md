---
template-id: T-MCP
template-version: 1.0
applies-to: docs/MCP-REFERENCE.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: expert-agent-mcp-server
doc-last-updated: 2026-06-18
doc-git-commit: 087c06c37341867986a35a0664c07933a8c53c69
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# expert-agent-mcp-server — MCP-REFERENCE

> **Template version:** T-MCP v1.0 — MCP tool surface (JSON-RPC 2.0 at `/mcp`).

## 1. Auth model

MCP auth mode: `api_key` via `X-API-Key` request header.

All MCP endpoints (JSON-RPC `/mcp` and bespoke `/mcp/<tool>` REST routes) are gated by `MCPToolAuthMiddleware`. The middleware validates the `X-API-Key` against either (a) the configured service/admin key(s) or (b) a DB-backed user API key. Anonymous callers receive a `401` JSON-RPC error before any tool runs.

RBAC is enforced per-tool via `cloud_dog_idam.rbac.RBACEngine` with the following role hierarchy:

| Role | Permissions |
|------|-------------|
| `admin` | `expert:admin:*` + `expert:tool:read` + `expert:tool:execute` |
| `owner` | `expert:tool:read` + `expert:tool:execute` + `expert:config:write` |
| `user` | `expert:tool:read` + `expert:tool:execute` |
| `viewer` | `expert:tool:read` |

Open paths (no auth required): `/health`, `/mcp/health`, `/mcp/tools`.

## 2. Tools

Tool count: **28** (source-verified from `src/servers/mcp/server.py` `_tool_catalog()` and `_TOOL_PERMISSION_MAP`).

### 2.1 `chat`

- **Description:** Send a message in an active session. Invokes the expert's LLM with full context-window history. Emits a PS-40 `expert.execute` audit event on the MCP path.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer", "description": "Active session ID"},
      "message": {"type": "string", "description": "User message text"},
      "temperature": {"type": "number", "description": "Sampling temperature (optional)"},
      "top_k": {"type": "integer", "description": "Top-K sampling (optional)"},
      "top_p": {"type": "number", "description": "Top-P sampling (optional)"},
      "max_tokens": {"type": "integer", "description": "Maximum tokens (optional)"},
      "response_format": {"type": "string", "enum": ["text", "markdown", "json"], "description": "Response format (optional)"},
      "language": {"type": "string", "description": "Language code e.g. en, fr, pl (optional)"},
      "system_prompt": {"type": "string", "description": "System prompt override (optional)"}
    },
    "required": ["session_id", "message"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "response": {"type": "string"},
      "tokens_used": {"type": ["integer", "null"]},
      "model": {"type": ["string", "null"]}
    }
  }
  ```
- **Errors:** `{"error": "Session not found"}` | `{"error": "Expert configuration not found"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"chat","arguments":{"session_id":1,"message":"Hello"}},"id":1}'
  ```

### 2.2 `start_session`

- **Description:** Start a new conversation session linked to a user and an expert configuration.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "user_id": {"type": "integer", "description": "User ID"},
      "expert_config_id": {"type": "integer", "description": "Expert configuration ID"},
      "title": {"type": ["string", "null"], "description": "Session title (optional)"},
      "channel_id": {"type": ["integer", "null"], "description": "Channel ID (optional)"}
    },
    "required": ["user_id", "expert_config_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "status": {"type": "string"},
      "title": {"type": ["string", "null"]}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"start_session","arguments":{"user_id":1,"expert_config_id":1}},"id":1}'
  ```

### 2.3 `resume_session`

- **Description:** Resume an existing session by setting its state to active.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer", "description": "Session ID to resume"}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "status": {"type": "string"},
      "message_count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "Session not found"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"resume_session","arguments":{"session_id":1}},"id":1}'
  ```

### 2.4 `end_session`

- **Description:** End (complete) an active session.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer", "description": "Session ID to end"}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "status": {"type": "string"}
    }
  }
  ```
- **Errors:** `{"error": "Session not found"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"end_session","arguments":{"session_id":1}},"id":1}'
  ```

### 2.5 `list_sessions`

- **Description:** List sessions, optionally filtered by user ID or status.
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "user_id": {"type": ["integer", "null"], "description": "Filter by user ID (optional)"},
      "status": {"type": ["string", "null"], "description": "Filter by session status (optional)"}
    }
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "sessions": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "integer"},
            "title": {"type": ["string", "null"]},
            "status": {"type": "string"},
            "user_id": {"type": "integer"}
          }
        }
      },
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_sessions","arguments":{"user_id":1}},"id":1}'
  ```

### 2.6 `session_status`

- **Description:** Get status and metadata for a specific session.
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer", "description": "Session ID"}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "status": {"type": "string"},
      "message_count": {"type": "integer"},
      "context_window": {"type": ["integer", "null"]},
      "created_at": {"type": "string", "format": "date-time"}
    }
  }
  ```
- **Errors:** `{"error": "Session not found"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"session_status","arguments":{"session_id":1}},"id":1}'
  ```

### 2.7 `get_history`

- **Description:** Retrieve conversation history (messages) for a session.
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer", "description": "Session ID"},
      "limit": {"type": ["integer", "null"], "description": "Maximum number of messages (optional)"}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "messages": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "role": {"type": "string"},
            "content": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"}
          }
        }
      },
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_history","arguments":{"session_id":1,"limit":50}},"id":1}'
  ```

### 2.8 `list_experts`

- **Description:** List all available expert configurations (public read — no admin required).
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {"type": "object", "properties": {}}
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "experts": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "title": {"type": "string"},
            "llm_provider": {"type": "string"},
            "llm_model": {"type": "string"}
          }
        }
      },
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_experts","arguments":{}},"id":1}'
  ```

### 2.9 `get_expert`

- **Description:** Get a single expert configuration by ID.
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "expert_id": {"type": "integer", "description": "Expert configuration ID"}
    },
    "required": ["expert_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "id": {"type": "integer"},
      "name": {"type": "string"},
      "title": {"type": "string"},
      "llm_provider": {"type": "string"},
      "llm_model": {"type": "string"},
      "enabled": {"type": "boolean"}
    }
  }
  ```
- **Errors:** `{"error": "Expert not found"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_expert","arguments":{"expert_id":1}},"id":1}'
  ```

### 2.10 `admin_list_experts`

- **Description:** List expert configurations with full detail. Requires admin RBAC.
- **RBAC:** `expert:admin:*` — role: admin only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "auth_context": {"type": "object", "description": "Auth context with x_api_key or role"},
      "enabled_only": {"type": "boolean", "default": false},
      "skip": {"type": "integer", "default": 0},
      "limit": {"type": "integer", "default": 100}
    }
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "experts": {"type": "array", "items": {"type": "object"}},
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "Admin access required"}` | `{"error": "Invalid API key"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"admin_list_experts","arguments":{"auth_context":{"x_api_key":"${ADMIN_API_KEY}"}}},"id":1}'
  ```

### 2.11 `admin_create_expert`

- **Description:** Create a new expert configuration. Requires admin RBAC. Publishes a `create/expert` A2A config-change event.
- **RBAC:** `expert:admin:*` — role: admin only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "name": {"type": "string"},
      "title": {"type": "string"},
      "description": {"type": "string"},
      "auth_context": {"type": "object"},
      "llm_provider": {"type": ["string", "null"]},
      "llm_model": {"type": ["string", "null"]},
      "llm_base_url": {"type": ["string", "null"]},
      "llm_params": {"type": ["object", "null"]},
      "prompt_template": {"type": ["string", "null"]},
      "tools": {"type": ["array", "null"], "items": {"type": "string"}},
      "enabled": {"type": "boolean", "default": true},
      "access_control": {"type": ["object", "null"]}
    },
    "required": ["name", "title", "description"]
  }
  ```
- **Output schema:** Full expert object (see `_serialise_expert`): `id`, `name`, `title`, `description`, `llm_provider`, `llm_model`, `llm_params`, `tools`, `enabled`.
- **Errors:** `{"error": "Admin access required"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"admin_create_expert","arguments":{"name":"my-expert","title":"My Expert","description":"Test expert","auth_context":{"x_api_key":"${ADMIN_API_KEY}"}}},"id":1}'
  ```

### 2.12 `admin_update_expert`

- **Description:** Update an existing expert configuration. Requires admin RBAC. Publishes an `update/expert` A2A config-change event.
- **RBAC:** `expert:admin:*` — role: admin only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "expert_id": {"type": "integer"},
      "auth_context": {"type": "object"},
      "name": {"type": "string"},
      "title": {"type": "string"},
      "description": {"type": "string"},
      "llm_provider": {"type": "string"},
      "llm_model": {"type": "string"},
      "llm_base_url": {"type": "string"},
      "llm_params": {"type": "object"},
      "prompt_template": {"type": "string"},
      "tools": {"type": "array", "items": {"type": "string"}},
      "enabled": {"type": "boolean"}
    },
    "required": ["expert_id"]
  }
  ```
- **Output schema:** Full expert object (same as `admin_create_expert`).
- **Errors:** `{"error": "Expert not found"}` | `{"error": "Admin access required"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"admin_update_expert","arguments":{"expert_id":1,"enabled":false,"auth_context":{"x_api_key":"${ADMIN_API_KEY}"}}},"id":1}'
  ```

### 2.13 `admin_delete_expert`

- **Description:** Delete an expert configuration. Requires admin RBAC. Publishes a `delete/expert` A2A config-change event.
- **RBAC:** `expert:admin:*` — role: admin only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "expert_id": {"type": "integer"},
      "auth_context": {"type": "object"}
    },
    "required": ["expert_id"]
  }
  ```
- **Output schema:**
  ```json
  {"type": "object", "properties": {"success": {"type": "boolean"}, "id": {"type": "integer"}, "name": {"type": "string"}}}
  ```
- **Errors:** `{"error": "Expert not found"}` | `{"error": "Admin access required"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"admin_delete_expert","arguments":{"expert_id":1,"auth_context":{"x_api_key":"${ADMIN_API_KEY}"}}},"id":1}'
  ```

### 2.14 `admin_list_users`

- **Description:** List user accounts. Requires admin RBAC.
- **RBAC:** `expert:admin:*` — role: admin only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "auth_context": {"type": "object"},
      "enabled_only": {"type": "boolean", "default": false},
      "role": {"type": ["string", "null"], "description": "Filter by role (optional)"}
    }
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "users": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "integer"},
            "username": {"type": "string"},
            "email": {"type": "string"},
            "display_name": {"type": ["string", "null"]},
            "role": {"type": "string"},
            "enabled": {"type": "boolean"}
          }
        }
      },
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "Admin access required"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"admin_list_users","arguments":{"auth_context":{"x_api_key":"${ADMIN_API_KEY}"}}},"id":1}'
  ```

### 2.15 `admin_create_api_key`

- **Description:** Create a new API key for a user. Requires admin RBAC. Returns the raw key in `key` field (only shown once). Publishes a `create/api_key` A2A config-change event.
- **RBAC:** `expert:admin:*` — role: admin only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "auth_context": {"type": "object"},
      "user_id": {"type": ["integer", "null"]},
      "name": {"type": ["string", "null"]},
      "expires_days": {"type": ["integer", "null"]},
      "read_logs": {"type": "boolean", "default": true},
      "read_histories": {"type": "boolean", "default": true},
      "read_channels": {"type": "boolean", "default": true}
    }
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "id": {"type": "integer"},
      "user_id": {"type": ["integer", "null"]},
      "group_id": {"type": ["integer", "null"]},
      "name": {"type": ["string", "null"]},
      "revoked": {"type": "boolean"},
      "read_channels": {"type": "boolean"},
      "read_logs": {"type": "boolean"},
      "read_histories": {"type": "boolean"},
      "expires_at": {"type": ["string", "null"]},
      "created_at": {"type": ["string", "null"]},
      "key": {"type": "string", "description": "Raw API key — shown only on creation"}
    }
  }
  ```
- **Errors:** `{"error": "Admin access required"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"admin_create_api_key","arguments":{"user_id":1,"name":"my-key","auth_context":{"x_api_key":"${ADMIN_API_KEY}"}}},"id":1}'
  ```

### 2.16 `admin_revoke_api_key`

- **Description:** Revoke an API key by key ID. Requires admin RBAC. Publishes a `delete/api_key` A2A config-change event.
- **RBAC:** `expert:admin:*` — role: admin only
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "key_id": {"type": "integer"},
      "auth_context": {"type": "object"}
    },
    "required": ["key_id"]
  }
  ```
- **Output schema:**
  ```json
  {"type": "object", "properties": {"success": {"type": "boolean"}, "id": {"type": "integer"}, "revoked": {"type": "boolean"}}}
  ```
- **Errors:** `{"error": "API key not found"}` | `{"error": "Admin access required"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"admin_revoke_api_key","arguments":{"key_id":5,"auth_context":{"x_api_key":"${ADMIN_API_KEY}"}}},"id":1}'
  ```

### 2.17 `vector_search`

- **Description:** Search a named vector store collection using semantic similarity.
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Search query text"},
      "collection": {"type": "string", "description": "Collection name"},
      "n_results": {"type": "integer", "default": 5},
      "vector_store_name": {"type": "string", "default": "_DEFAULT_"}
    },
    "required": ["query", "collection"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "results": {"type": "array"},
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"vector_search","arguments":{"query":"machine learning","collection":"docs","n_results":5}},"id":1}'
  ```

### 2.18 `vector_add`

- **Description:** Add documents to a named vector store collection.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "documents": {"type": "array", "items": {"type": "string"}},
      "collection": {"type": "string"},
      "vector_store_name": {"type": "string", "default": "_DEFAULT_"},
      "metadatas": {"type": ["array", "null"], "items": {"type": "object"}}
    },
    "required": ["documents", "collection"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "ids": {"type": "array", "items": {"type": "string"}},
      "count": {"type": "integer"},
      "collection": {"type": "string"}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"vector_add","arguments":{"documents":["Hello world"],"collection":"docs"}},"id":1}'
  ```

### 2.19 `get_session_by_key`

- **Description:** Look up a session by its shareable session key (AT1.11).
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_key": {"type": "string", "description": "Session share key"}
    },
    "required": ["session_key"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "title": {"type": ["string", "null"]},
      "status": {"type": "string"},
      "user_id": {"type": "integer"},
      "expert_config_id": {"type": "integer"},
      "session_key": {"type": "string"},
      "history_key": {"type": ["string", "null"]}
    }
  }
  ```
- **Errors:** `{"error": "Session not found or key expired"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_session_by_key","arguments":{"session_key":"abc123"}},"id":1}'
  ```

### 2.20 `get_history_by_key`

- **Description:** Retrieve conversation history using a shareable history key (AT1.11).
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "history_key": {"type": "string", "description": "History share key"}
    },
    "required": ["history_key"]
  }
  ```
- **Output schema:** History object as returned by `HistoryKeyManager.get_history_by_key` (structure varies by implementation).
- **Errors:** `{"error": "History not found"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_history_by_key","arguments":{"history_key":"xyz789"}},"id":1}'
  ```

### 2.21 `share_session`

- **Description:** Share a session with specified users and/or groups (AT1.11).
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "user_ids": {"type": ["array", "null"], "items": {"type": "integer"}},
      "group_ids": {"type": ["array", "null"], "items": {"type": "integer"}}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:** Result object from `HistorySharingManager.share_session`.
- **Errors:** `{"error": "<ValueError message>"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"share_session","arguments":{"session_id":1,"user_ids":[2,3]}},"id":1}'
  ```

### 2.22 `unshare_session`

- **Description:** Remove sharing of a session with specified users and/or groups (AT1.11).
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "user_ids": {"type": ["array", "null"], "items": {"type": "integer"}},
      "group_ids": {"type": ["array", "null"], "items": {"type": "integer"}}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:** Result object from `HistorySharingManager.unshare_session`.
- **Errors:** `{"error": "<ValueError message>"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"unshare_session","arguments":{"session_id":1,"user_ids":[2]}},"id":1}'
  ```

### 2.23 `summarize_session`

- **Description:** Trigger LLM-based summarization of an older portion of session context to compress the context window (AT1.11).
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "preserve_recent": {"type": "integer", "default": 5, "description": "Number of recent messages to keep verbatim"},
      "max_tokens": {"type": ["integer", "null"], "description": "Token budget for summarization (optional)"}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:** Result object from `ContextSummarizationManager.summarize_session`.
- **Errors:** `{"error": "<ValueError message>"}` | `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"summarize_session","arguments":{"session_id":1,"preserve_recent":5}},"id":1}'
  ```

### 2.24 `get_summaries`

- **Description:** Retrieve all stored summaries for a session (AT1.11).
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"}
    },
    "required": ["session_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "session_id": {"type": "integer"},
      "summaries": {"type": "array"},
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_summaries","arguments":{"session_id":1}},"id":1}'
  ```

### 2.25 `execute_tool`

- **Description:** Transactional expert execution entry point. Routes through `TransactionalExecutor` which orchestrates LLM + service composition with full audit.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "expert_id": {"type": "integer"},
      "input_text": {"type": "string"},
      "parameters": {"type": ["object", "null"]},
      "context": {"type": ["object", "null"]},
      "auth_context": {"type": ["object", "null"]}
    },
    "required": ["expert_id", "input_text"]
  }
  ```
- **Output schema:** Execution result from `TransactionalExecutor.execute` (structure includes `response`, `services_invoked`, `token_usage`, `audit_id` fields).
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"execute_tool","arguments":{"expert_id":1,"input_text":"Summarise this data"}},"id":1}'
  ```

### 2.26 `list_services`

- **Description:** List all MCP/A2A services bound to a given expert configuration.
- **RBAC:** `expert:tool:read` — roles: admin, owner, user, viewer
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "expert_id": {"type": "integer"}
    },
    "required": ["expert_id"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "expert_id": {"type": "integer"},
      "services": {"type": "array"},
      "count": {"type": "integer"}
    }
  }
  ```
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_services","arguments":{"expert_id":1}},"id":1}'
  ```

### 2.27 `invoke_service_tool`

- **Description:** Invoke a tool on a remote bound external service via `ServiceCompositionManager`.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "service_id": {"type": "integer"},
      "tool_name": {"type": "string"},
      "arguments": {"type": ["object", "null"]},
      "auth_context": {"type": ["object", "null"]},
      "session_id": {"type": ["integer", "null"]}
    },
    "required": ["service_id", "tool_name"]
  }
  ```
- **Output schema:** Tool result from the remote service (pass-through).
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"invoke_service_tool","arguments":{"service_id":2,"tool_name":"search","arguments":{"query":"hello"}}},"id":1}'
  ```

### 2.28 `code_execute`

- **Description:** Run code on the code-runner service over A2A. Analyst reasoning tool that sends a `code.execute` request to the configured code-runner backend. Correlation ID is forwarded for cross-service audit linkage.
- **RBAC:** `expert:tool:execute` — roles: admin, owner, user
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "code": {"type": "string", "description": "Code to execute"},
      "language": {"type": ["string", "null"], "description": "Language hint (optional)"},
      "task_id": {"type": ["string", "null"], "description": "Task correlation ID (optional)"},
      "auth_context": {"type": ["object", "null"]}
    },
    "required": ["code"]
  }
  ```
- **Output schema:** Execution result from `CodeRunnerClient.execute` (includes `output`, `exit_code`, `error`).
- **Errors:** `{"error": "<exception message>"}`
- **Example call:**
  ```bash
  curl -X POST https://<host>/mcp \
    -H "Accept: application/json, text/event-stream" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"code_execute","arguments":{"code":"print(1+1)","language":"python"}},"id":1}'
  ```

## 3. Cross-references
- [API-REFERENCE.md](API-REFERENCE.md)
- [A2A-REFERENCE.md](A2A-REFERENCE.md)
- PS-72-mcp-a2a-webui.md

## 4. Project-specific notes

All tool names documented in §2 above exist as string literals in `src/servers/mcp/server.py` (`_tool_catalog()`, `_TOOL_PERMISSION_MAP`, `_dispatch_tool()`) and their implementations exist in `src/servers/mcp/tools.py`. The RBAC permission map in `_TOOL_PERMISSION_MAP` is the authoritative source for per-tool access control.

Transport modes supported: `streamable_http`, `http_jsonrpc`, `legacy_sse` (HTTP) and `stdio` (for MCP desktop clients). JSON-RPC endpoint: `POST /mcp`. Async job mode: pass `"wait": false` in arguments to receive a `job_id` resolved via `GET /jobs/{job_id}`.
