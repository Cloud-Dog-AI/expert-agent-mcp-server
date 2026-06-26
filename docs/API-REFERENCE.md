---
template-id: T-API
template-version: 1.0
applies-to: docs/API-REFERENCE.md
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

# API Reference — Expert Agent MCP Server

## Scope

This document covers every exposed interface in this repository:
- REST API routes from `src/servers/api/routes/*`
- MCP HTTP/JSON-RPC interface and tool catalogue
- A2A HTTP/WebSocket interface

## REST API

Base URL (local default): `http://127.0.0.1:8083`

Auth model:
- Public endpoints: health/docs roots where explicitly configured
- Protected endpoints: API key (`X-API-Key`) and/or bearer token based on route dependency

Request/response schemas and full component models:
- Static OpenAPI snapshot: [`openapi.json`](./openapi.json)
- API docs route: `/docs/api`

### Complete Endpoint Matrix

| Method | Path | Description | Auth | Request | Success Responses | Error Responses | Source |
|---|---|---|---|---|---|---|---|
| GET | `/api-keys` | List Api Keys | Route-dependent | `None` | `200` | `422` | `openapi.json + api_keys.py` |
| POST | `/api-keys` | Create Api Key | Route-dependent | `application/json:#/components/schemas/CreateAPIKeyRequest` | `200` | `422` | `openapi.json + api_keys.py` |
| GET | `/api-keys/me` | Get My Api Key Permissions | Route-dependent | `None` | `200` | `422` | `openapi.json + api_keys.py` |
| DELETE | `/api-keys/{key_id}` | Revoke Api Key | Route-dependent | `None` | `200` | `422` | `openapi.json + api_keys.py` |
| POST | `/api-keys/{key_id}/rotate` | Rotate Api Key | Route-dependent | `None` | `200` | `422` | `openapi.json + api_keys.py` |
| GET | `/audit` | Get Audit Events | Route-dependent | `None` | `200` | `422` | `openapi.json + audit.py` |
| GET | `/audit/export/{format}` | Export Audit Logs | Route-dependent | `None` | `200` | `422` | `openapi.json + audit.py` |
| GET | `/audit/{event_id}` | Get Audit Event | Route-dependent | `None` | `200` | `422` | `openapi.json + audit.py` |
| GET | `/audit/{event_id}/raw` | Get Audit Event Raw | Route-dependent | `None` | `200` | `422` | `openapi.json + audit.py` |
| GET | `/audit/{event_id}/verify` | Verify Audit Event Signature | Route-dependent | `None` | `200` | `422` | `openapi.json + audit.py` |
| POST | `/auth/admin-reset-password` | Admin Reset Password | Route-dependent | `application/json:#/components/schemas/AdminResetPasswordRequest` | `200` | `422` | `openapi.json + auth.py` |
| POST | `/auth/change-password` | Change Password | Route-dependent | `application/json:#/components/schemas/ChangePasswordRequest` | `200` | `422` | `openapi.json + auth.py` |
| POST | `/auth/login` | Login | Route-dependent | `application/json:#/components/schemas/LoginRequest` | `200` | `422` | `openapi.json + auth.py` |
| POST | `/auth/logout` | Logout | Route-dependent | `application/json:#/components/schemas/LogoutRequest` | `200` | `422` | `openapi.json + auth.py` |
| POST | `/auth/refresh` | Refresh | Route-dependent | `application/json:#/components/schemas/RefreshRequest` | `200` | `422` | `openapi.json + auth.py` |
| POST | `/auth/register` | Register | Route-dependent | `application/json:#/components/schemas/RegisterRequest` | `200` | `422` | `openapi.json + auth.py` |
| GET | `/auth/validate` | Validate | Route-dependent | `None` | `200` | `422` | `openapi.json + auth.py` |
| GET | `/channels` | List Channels | Route-dependent | `None` | `200` | `422` | `openapi.json + channels.py` |
| POST | `/channels` | Create Channel | Route-dependent | `application/json:#/components/schemas/CreateChannelRequest` | `200` | `422` | `openapi.json + channels.py` |
| DELETE | `/channels/{channel_id}` | Delete Channel | Route-dependent | `None` | `200` | `422` | `openapi.json + channels.py` |
| GET | `/channels/{channel_id}` | Get Channel | Route-dependent | `None` | `200` | `422` | `openapi.json + channels.py` |
| POST | `/channels/{channel_id}/chat` | Channel Chat | Route-dependent | `application/json:#/components/schemas/ChannelChatRequest` | `200` | `422` | `openapi.json + channels.py` |
| GET | `/channels/{channel_id}/history` | Get Channel History | Route-dependent | `None` | `200` | `422` | `openapi.json + channels.py` |
| GET | `/channels/{channel_id}/llm-config` | Get Channel Llm Config | Route-dependent | `None` | `200` | `422` | `openapi.json + channels.py` |
| GET | `/channels/{channel_id}/services` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `channels.py` |
| DELETE | `/channels/{channel_id}/services/{service_id}` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `channels.py` |
| POST | `/channels/{channel_id}/services/{service_id}` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `channels.py` |
| GET | `/channels/{channel_id}/tools` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `channels.py` |
| DELETE | `/channels/{channel_id}/tools/{tool_name}` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `channels.py` |
| GET | `/channels/{channel_id}/vector-stores` | Get Channel Vector Stores | Route-dependent | `None` | `200` | `422` | `openapi.json + channels.py` |
| POST | `/channels/{channel_id}/vector-stores` | Add Channel Vector Store | Route-dependent | `application/json:#/components/schemas/AddVectorStoreRequest` | `200` | `422` | `openapi.json + channels.py` |
| DELETE | `/channels/{channel_id}/vector-stores/{vector_store_id}` | Remove Channel Vector Store | Route-dependent | `None` | `200` | `422` | `openapi.json + channels.py` |
| GET | `/docs/api` | Api Documentation | Route-dependent | `None` | `200` | `-` | `openapi.json + api_docs.py` |
| GET | `/docs/routes` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `api_docs.py` |
| GET | `/experts` | List Experts | Route-dependent | `None` | `200` | `422` | `openapi.json + experts.py` |
| POST | `/experts` | Create Expert | Route-dependent | `application/json:#/components/schemas/CreateExpertRequest` | `200` | `422` | `openapi.json + experts.py` |
| DELETE | `/experts/{expert_id}` | Delete Expert | Route-dependent | `None` | `200` | `422` | `openapi.json + experts.py` |
| GET | `/experts/{expert_id}` | Get Expert | Route-dependent | `None` | `200` | `422` | `openapi.json + experts.py` |
| PUT | `/experts/{expert_id}` | Update Expert | Route-dependent | `application/json:#/components/schemas/UpdateExpertRequest` | `200` | `422` | `openapi.json + experts.py` |
| GET | `/files` | List Files | Route-dependent | `None` | `200` | `422` | `openapi.json + files.py` |
| POST | `/files/bulk-delete` | Bulk Delete Files | Route-dependent | `application/json:File Ids` | `200` | `422` | `openapi.json + files.py` |
| GET | `/files/storage/stats` | Get Storage Stats | Route-dependent | `None` | `200` | `422` | `openapi.json + files.py` |
| POST | `/files/upload` | Upload File | Route-dependent | `multipart/form-data:#/components/schemas/Body_upload_file_files_upload_post` | `200` | `422` | `openapi.json + files.py` |
| POST | `/files/upload_base64` | Upload File Base64 | Route-dependent | `application/json:#/components/schemas/UploadBase64Request` | `200` | `422` | `openapi.json + files.py` |
| DELETE | `/files/{file_id}` | Delete File | Route-dependent | `None` | `200` | `422` | `openapi.json + files.py` |
| GET | `/files/{file_id}` | Get File Metadata | Route-dependent | `None` | `200` | `422` | `openapi.json + files.py` |
| GET | `/files/{file_id}/download` | Download File | Route-dependent | `None` | `200` | `422` | `openapi.json + files.py` |
| POST | `/files/{file_id}/ingest_to_knowledge` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `files.py` |
| POST | `/files/{file_id}/ingest_to_vector_store` | Ingest File To Vector Store | Route-dependent | `application/json:#/components/schemas/IngestFileToVectorStoreRequest` | `200` | `422` | `openapi.json + files.py` |
| POST | `/files/{file_id}/translate` | Translate File | Route-dependent | `application/json:#/components/schemas/TranslateFileRequest` | `200` | `422` | `openapi.json + files.py` |
| GET | `/groups` | List Groups | Route-dependent | `None` | `200` | `422` | `openapi.json + groups.py` |
| POST | `/groups` | Create Group | Route-dependent | `application/json:#/components/schemas/CreateGroupRequest` | `200` | `422` | `openapi.json + groups.py` |
| DELETE | `/groups/{group_id}` | Delete Group | Route-dependent | `None` | `200` | `422` | `openapi.json + groups.py` |
| GET | `/groups/{group_id}` | Get Group | Route-dependent | `None` | `200` | `422` | `openapi.json + groups.py` |
| PUT | `/groups/{group_id}` | Update Group | Route-dependent | `application/json:#/components/schemas/UpdateGroupRequest` | `200` | `422` | `openapi.json + groups.py` |
| GET | `/groups/{group_id}/admins` | Get Group Admins | Route-dependent | `None` | `200` | `422` | `openapi.json + groups.py` |
| POST | `/groups/{group_id}/admins` | Assign Group Admin | Route-dependent | `application/json:#/components/schemas/AssignGroupAdminRequest` | `200` | `422` | `openapi.json + groups.py` |
| DELETE | `/groups/{group_id}/admins/{user_id}` | Remove Group Admin | Route-dependent | `None` | `200` | `422` | `openapi.json + groups.py` |
| GET | `/groups/{group_id}/members` | Get Group Members | Route-dependent | `None` | `200` | `422` | `openapi.json + groups.py` |
| POST | `/groups/{group_id}/members` | Add Group Member | Route-dependent | `application/json:Request` | `200` | `422` | `openapi.json + groups.py` |
| DELETE | `/groups/{group_id}/members/{user_id}` | Remove Group Member | Route-dependent | `None` | `200` | `422` | `openapi.json + groups.py` |
| PUT | `/groups/{group_id}/members/{user_id}/role` | Update Member Role | Route-dependent | `application/json:#/components/schemas/UpdateMemberRoleRequest` | `200` | `422` | `openapi.json + groups.py` |
| GET | `/health` | Health | Route-dependent | `None` | `200` | `-` | `openapi.json + health.py` |
| GET | `/health/status` | Status | Route-dependent | `None` | `200` | `-` | `openapi.json + health.py` |
| GET | `/jobs` | List Jobs | Route-dependent | `None` | `200` | `422` | `openapi.json + jobs.py` |
| GET | `/jobs/queue/status` | Get Queue Status | Route-dependent | `None` | `200` | `422` | `openapi.json + jobs.py` |
| DELETE | `/jobs/{job_id}` | Remove Job | Route-dependent | `None` | `200` | `422` | `openapi.json + jobs.py` |
| GET | `/jobs/{job_id}` | Get Job | Route-dependent | `None` | `200` | `422` | `openapi.json + jobs.py` |
| POST | `/jobs/{job_id}/resubmit` | Resubmit Job | Route-dependent | `application/json:#/components/schemas/ResubmitJobRequest` | `200` | `422` | `openapi.json + jobs.py` |
| POST | `/jobs/{job_id}/stop` | Stop Job | Route-dependent | `None` | `200` | `422` | `openapi.json + jobs.py` |
| GET | `/knowledge` | List Knowledge | Route-dependent | `None` | `200` | `422` | `openapi.json + knowledge.py` |
| POST | `/knowledge` | Add Knowledge | Route-dependent | `application/json:#/components/schemas/AddKnowledgeRequest` | `200` | `422` | `openapi.json + knowledge.py` |
| PUT | `/knowledge/{knowledge_id}` | Replace Knowledge | Route-dependent | `application/json:#/components/schemas/ReplaceKnowledgeRequest` | `200` | `422` | `openapi.json + knowledge.py` |
| POST | `/knowledge/{knowledge_id}/merge` | Merge Knowledge | Route-dependent | `application/json:#/components/schemas/MergeKnowledgeRequest` | `200` | `422` | `openapi.json + knowledge.py` |
| DELETE | `/knowledge/{knowledge_type}/{knowledge_id}` | Delete Knowledge | Route-dependent | `None` | `200` | `422` | `openapi.json + knowledge.py` |
| GET | `/knowledge/{knowledge_type}/{knowledge_id}` | Get Knowledge History | Route-dependent | `None` | `200` | `422` | `openapi.json + knowledge.py` |
| POST | `/knowledge/{knowledge_type}/{knowledge_id}/rollback` | Rollback Knowledge | Route-dependent | `application/json:#/components/schemas/RollbackKnowledgeRequest` | `200` | `422` | `openapi.json + knowledge.py` |
| GET | `/knowledge/{knowledge_type}/{knowledge_id}/versions` | List Knowledge Versions | Route-dependent | `None` | `200` | `422` | `openapi.json + knowledge.py` |
| PUT | `/knowledge/{knowledge_type}/{knowledge_id}/{entry_id}` | Update Knowledge | Route-dependent | `application/json:#/components/schemas/UpdateKnowledgeRequest` | `200` | `422` | `openapi.json + knowledge.py` |
| GET | `/operations` | List Operations | Route-dependent | `None` | `200` | `422` | `openapi.json + operations.py` |
| GET | `/operations/{operation_id}` | Get Operation Status | Route-dependent | `None` | `200` | `422` | `openapi.json + operations.py` |
| POST | `/operations/{operation_id}/cancel` | Cancel Operation | Route-dependent | `application/json:#/components/schemas/CancelOperationRequest` | `200` | `422` | `openapi.json + operations.py` |
| POST | `/prompts/generate` | Generate Prompt | Route-dependent | `application/json:#/components/schemas/GeneratePromptRequest` | `200` | `422` | `openapi.json + prompts.py` |
| POST | `/prompts/test-cases` | Generate Test Cases | Route-dependent | `application/json:#/components/schemas/GenerateTestCasesRequest` | `200` | `422` | `openapi.json + prompts.py` |
| POST | `/prompts/validate` | Validate Prompt | Route-dependent | `application/json:#/components/schemas/src__servers__api__routes__validation__ValidatePromptRequest` | `200` | `422` | `openapi.json + prompts.py` |
| POST | `/quality/evaluate` | Evaluate Response | Route-dependent | `application/json:#/components/schemas/EvaluateResponseRequest` | `200` | `422` | `openapi.json + quality.py` |
| POST | `/quality/feedback` | Submit Feedback | Route-dependent | `application/json:#/components/schemas/UserFeedbackRequest` | `200` | `422` | `openapi.json + quality.py` |
| GET | `/quality/job/{job_id}` | Get Quality Metrics | Route-dependent | `None` | `200` | `422` | `openapi.json + quality.py` |
| GET | `/services` | List Services | Route-dependent | `None` | `200` | `422` | `openapi.json + services.py` |
| POST | `/services` | Create Service | Route-dependent | `application/json:#/components/schemas/CreateServiceRequest` | `200` | `422` | `openapi.json + services.py` |
| DELETE | `/services/{service_id}` | Delete Service | Route-dependent | `None` | `200` | `422` | `openapi.json + services.py` |
| GET | `/services/{service_id}` | Get Service | Route-dependent | `None` | `200` | `422` | `openapi.json + services.py` |
| PUT | `/services/{service_id}` | Update Service | Route-dependent | `application/json:#/components/schemas/UpdateServiceRequest` | `200` | `422` | `openapi.json + services.py` |
| POST | `/services/{service_id}/health` | Check Service Health | Route-dependent | `None` | `200` | `422` | `openapi.json + services.py` |
| GET | `/sessions` | List Sessions | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| POST | `/sessions` | Create Session | Route-dependent | `application/json:#/components/schemas/CreateSessionRequest` | `200` | `422` | `openapi.json + sessions.py` |
| GET | `/sessions/history/{history_key}` | Get History By Key | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| GET | `/sessions/key/{session_key}` | Get Session By Key | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| DELETE | `/sessions/{session_id}` | Delete Session | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| GET | `/sessions/{session_id}` | Get Session | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| GET | `/sessions/{session_id}/messages` | Get Messages | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| POST | `/sessions/{session_id}/messages` | Add Message | Route-dependent | `application/json:#/components/schemas/AddMessageRequest` | `200` | `422` | `openapi.json + sessions.py` |
| POST | `/sessions/{session_id}/rotate-key` | Rotate Session Key | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| POST | `/sessions/{session_id}/share` | Share Session | Route-dependent | `application/json:#/components/schemas/ShareSessionRequest` | `200` | `422` | `openapi.json + sessions.py` |
| GET | `/sessions/{session_id}/summaries` | Get Summaries | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| POST | `/sessions/{session_id}/summarize` | Summarize Session | Route-dependent | `None` | `200` | `422` | `openapi.json + sessions.py` |
| POST | `/testing/expert-suite` | Run Expert Test Suite | Route-dependent | `application/json:#/components/schemas/RunTestSuiteRequest` | `200` | `422` | `openapi.json + testing.py` |
| GET | `/users` | List Users | Route-dependent | `None` | `200` | `422` | `openapi.json + users.py` |
| POST | `/users` | Create User | Route-dependent | `application/json:#/components/schemas/CreateUserRequest` | `200` | `422` | `openapi.json + users.py` |
| DELETE | `/users/{user_id}` | Delete User | Route-dependent | `None` | `200` | `422` | `openapi.json + users.py` |
| GET | `/users/{user_id}` | Get User | Route-dependent | `None` | `200` | `422` | `openapi.json + users.py` |
| PUT | `/users/{user_id}` | Update User | Route-dependent | `application/json:#/components/schemas/UpdateUserRequest` | `200` | `422` | `openapi.json + users.py` |
| DELETE | `/users/{user_id}/gdpr/delete` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `users.py` |
| GET | `/users/{user_id}/gdpr/export` | - | Route-dependent | `See route schema` | `See route schema` | `See route schema` | `users.py` |
| POST | `/validation/llm` | Validate Llm | Route-dependent | `application/json:#/components/schemas/ValidateLLMRequest` | `200` | `422` | `openapi.json + validation.py` |
| POST | `/validation/prompt` | Validate Prompt | Route-dependent | `application/json:#/components/schemas/src__servers__api__routes__validation__ValidatePromptRequest` | `200` | `422` | `openapi.json + validation.py` |
| GET | `/vector-stores` | List Vector Stores | Route-dependent | `None` | `200` | `422` | `openapi.json + vector_stores.py` |
| POST | `/vector-stores` | Create Vector Store | Route-dependent | `application/json:#/components/schemas/CreateVectorStoreRequest` | `200` | `422` | `openapi.json + vector_stores.py` |
| DELETE | `/vector-stores/{store_id}` | Delete Vector Store | Route-dependent | `None` | `200` | `422` | `openapi.json + vector_stores.py` |
| GET | `/vector-stores/{store_id}` | Get Vector Store | Route-dependent | `None` | `200` | `422` | `openapi.json + vector_stores.py` |
| PUT | `/vector-stores/{store_id}` | Update Vector Store | Route-dependent | `application/json:#/components/schemas/UpdateVectorStoreRequest` | `200` | `422` | `openapi.json + vector_stores.py` |
| POST | `/vector-stores/{store_id}/documents` | Add Document | Route-dependent | `application/json:#/components/schemas/AddDocumentRequest` | `200` | `422` | `openapi.json + vector_stores.py` |
| DELETE | `/vector-stores/{store_id}/documents/{doc_id}` | Delete Document | Route-dependent | `None` | `200` | `422` | `openapi.json + vector_stores.py` |
| PUT | `/vector-stores/{store_id}/documents/{doc_id}` | Update Document | Route-dependent | `application/json:#/components/schemas/UpdateDocumentRequest` | `200` | `422` | `openapi.json + vector_stores.py` |
| GET | `/vector-stores/{store_id}/health` | Health Check Vector Store | Route-dependent | `None` | `200` | `422` | `openapi.json + vector_stores.py` |
| POST | `/vector-stores/{store_id}/query` | Query Documents | Route-dependent | `application/json:#/components/schemas/QueryDocumentRequest` | `200` | `422` | `openapi.json + vector_stores.py` |

## MCP Tools

MCP base URL (local default): `http://127.0.0.1:8081`

Protocol operations:
- JSON-RPC method: `tools/list`
- JSON-RPC method: `tools/call`
- Initialisation method: `initialize`

### Tool Catalogue

| Tool | Description | Parameters | Returns |
|---|---|---|---|
| `chat` | Chat turn execution | `session_id`, `message`, optional `temperature`, `top_k`, `top_p`, `max_tokens`, `response_format`, `language`, `system_prompt` | `response`, `tokens_used`, `model` |
| `start_session` | Create session | `user_id`, `expert_config_id`, optional `title`, `channel_id` | `session_id`, `status`, `title` |
| `resume_session` | Resume existing session | `session_id` | session status payload |
| `end_session` | Complete session | `session_id` | completion status payload |
| `list_sessions` | Query sessions | optional `user_id`, `status` | session list + count |
| `session_status` | Read session status | `session_id` | status details |
| `get_history` | Read session history | `session_id`, optional `limit` | message history list |
| `list_experts` | List experts | none | expert list |
| `get_expert` | Get expert detail | `expert_id` | expert payload |
| `vector_search` | Search vector store | `query`, `collection`, optional `n_results`, `vector_store_name` | search hits |
| `vector_add` | Add vector documents | `documents`, `collection`, optional `vector_store_name`, `metadatas` | upsert status |
| `get_session_by_key` | Session lookup by key | `session_key` | session payload |
| `get_history_by_key` | History lookup by key | `history_key` | history payload |
| `share_session` | Share session | `session_id`, optional `user_ids`, `group_ids` | share status |
| `unshare_session` | Unshare session | `session_id`, optional `user_ids`, `group_ids` | unshare status |
| `summarize_session` | Trigger summarisation | `session_id`, optional `preserve_recent`, `max_tokens` | summary job/result |
| `get_summaries` | List summaries | `session_id` | summaries list |

### MCP HTTP Endpoints

| Method | Path |
|---|---|
| GET | `/health` |
| GET | `/jobs/{job_id}` |
| DELETE | `/mcp` |
| POST | `/mcp` |
| POST | `/mcp/chat` |
| POST | `/mcp/end_session` |
| GET | `/mcp/expert/{expert_id}` |
| GET | `/mcp/experts` |
| GET | `/mcp/health` |
| GET | `/mcp/history/key/{history_key}` |
| POST | `/mcp/resume_session` |
| GET | `/mcp/session/key/{session_key}` |
| GET | `/mcp/session/{session_id}/history` |
| POST | `/mcp/session/{session_id}/share` |
| GET | `/mcp/session/{session_id}/status` |
| GET | `/mcp/session/{session_id}/summaries` |
| POST | `/mcp/session/{session_id}/summarize` |
| POST | `/mcp/session/{session_id}/unshare` |
| GET | `/mcp/sessions` |
| POST | `/mcp/start_session` |
| GET | `/mcp/tools` |
| POST | `/mcp/vector/add` |
| POST | `/mcp/vector/search` |
| POST | `/message` |
| POST | `/messages` |
| GET | `/sse` |

## A2A Endpoints

A2A base URL (local default): `http://127.0.0.1:8082`

| Method | Path |
|---|---|
| POST | `/a2a/broadcast/{topic}` |
| GET | `/a2a/health` |
| GET | `/a2a/topics` |
| WEBSOCKET | `/a2a/ws/{topic}` |
| GET | `/health` |

## OpenAPI

- OpenAPI source: [`openapi.json`](./openapi.json)
- Regenerate snapshot (local):
  ```bash
  .venv/bin/python scripts/generate_openapi.py
  ```



<!-- W28C-1710a recovery: full content from archive/2026-06-12/API_DOCUMENTATION.md (archived sha256=1acacd3818f2, 217 lines) -->

## Recovered domain content — `archive/2026-06-12/API_DOCUMENTATION.md` (217 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/API_DOCUMENTATION.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# API Documentation

## Base URLs
- Local development: `http://localhost:8083`
- Deployed: `https://expertagent.example.com`

## Authentication
Use a session cookie for browser-driven flows or `Authorization: Bearer <your-api-key>` for programmatic access.

## Verification Basis
- Source files reviewed: `src/servers/a2a/server.py`, `src/servers/api/routes/__init__.py`, `src/servers/api/routes/api_docs.py`, `src/servers/api/routes/api_keys.py`, `src/servers/api/routes/audit.py`, `src/servers/api/routes/auth.py`, `src/servers/api/routes/channels.py`, `src/servers/api/routes/experts.py`, `src/servers/api/routes/files.py`, `src/servers/api/routes/groups.py`, `src/servers/api/routes/health.py`, `src/servers/api/routes/jobs.py`
- Route inventory size: 186

## Route Inventory
| Method | Path | Notes |
|--------|------|-------|
| GET | `/a2a/topics` | Handler `list_topics` in `src/servers/a2a/server.py`. |
| POST | `/a2a/broadcast/{topic}` | Handler `broadcast_message` in `src/servers/a2a/server.py`. |
| GET | `/a2a/health` | Handler `a2a_health` in `src/servers/a2a/server.py`. |
| GET | `/health` | Handler `health` in `src/servers/a2a/server.py`. |
| POST | `/mcp/chat` | Handler `mcp_chat` in `src/servers/mcp/server.py`. |
| POST | `/mcp/start_session` | Handler `mcp_start_session` in `src/servers/mcp/server.py`. |
| POST | `/mcp/resume_session` | Handler `mcp_resume_session` in `src/servers/mcp/server.py`. |
| POST | `/mcp/end_session` | Handler `mcp_end_session` in `src/servers/mcp/server.py`. |
| GET | `/mcp/sessions` | Handler `mcp_list_sessions` in `src/servers/mcp/server.py`. |
| GET | `/mcp/session/{session_id}/status` | Handler `mcp_session_status` in `src/servers/mcp/server.py`. |
| GET | `/mcp/session/{session_id}/history` | Handler `mcp_get_history` in `src/servers/mcp/server.py`. |
| GET | `/mcp/experts` | Handler `mcp_list_experts` in `src/servers/mcp/server.py`. |
| GET | `/mcp/expert/{expert_id}` | Handler `mcp_get_expert` in `src/servers/mcp/server.py`. |
| POST | `/mcp/vector/search` | Handler `mcp_vector_search` in `src/servers/mcp/server.py`. |
| POST | `/mcp/vector/add` | Handler `mcp_vector_add` in `src/servers/mcp/server.py`. |
| GET | `/mcp/health` | Handler `mcp_health` in `src/servers/mcp/server.py`. |
| GET | `/health` | Handler `health` in `src/servers/mcp/server.py`. |
| POST | `/mcp` | Handler `mcp_streamable_http` in `src/servers/mcp/server.py`. |
| POST | `/messages` | Handler `mcp_http_jsonrpc` in `src/servers/mcp/server.py`. |
| DELETE | `/mcp` | Handler `mcp_delete_session` in `src/servers/mcp/server.py`. |
| GET | `/jobs/{job_id}` | Handler `mcp_get_async_job_status` in `src/servers/mcp/server.py`. |
| GET | `/sse` | Handler `mcp_legacy_sse` in `src/servers/mcp/server.py`. |
| POST | `/message` | Handler `mcp_legacy_message` in `src/servers/mcp/server.py`. |
| GET | `/mcp/session/key/{session_key}` | Handler `mcp_get_session_by_key` in `src/servers/mcp/server.py`. |
| GET | `/mcp/history/key/{history_key}` | Handler `mcp_get_history_by_key` in `src/servers/mcp/server.py`. |
| POST | `/mcp/session/{session_id}/share` | Handler `mcp_share_session` in `src/servers/mcp/server.py`. |
| POST | `/mcp/session/{session_id}/unshare` | Handler `mcp_unshare_session` in `src/servers/mcp/server.py`. |
| POST | `/mcp/session/{session_id}/summarize` | Handler `mcp_summarize_session` in `src/servers/mcp/server.py`. |
| GET | `/mcp/session/{session_id}/summaries` | Handler `mcp_get_summaries` in `src/servers/mcp/server.py`. |
| GET | `/mcp/tools` | Handler `mcp_list_tools` in `src/servers/mcp/server.py`. |
| GET | `/` | Handler `index` in `src/servers/web/server.py`. |
| GET | `/login` | Handler `login_page` in `src/servers/web/server.py`. |
| GET | `/web/auth/login` | Handler `web_login_page` in `src/servers/web/server.py`. |
| GET | `/runtime-config.js` | Handler `runtime_config` in `src/servers/web/server.py`. |
| GET | `/ui` | Handler `ui_alias_root` in `src/servers/web/server.py`. |
| GET | `/ui/{path:path}` | Handler `ui_alias_path` in `src/servers/web/server.py`. |
| POST | `/web/auth/login` | Handler `web_login` in `src/servers/web/server.py`. |
| POST | `/web/auth/logout` | Handler `web_logout` in `src/servers/web/server.py`. |
| GET | `/web/auth/me` | Handler `web_auth_me` in `src/servers/web/server.py`. |
| GET | `/web/auth/status` | Handler `web_auth_status` in `src/servers/web/server.py`. |
| GET | `/health` | Handler `health` in `src/servers/web/server.py`. |
| GET | `/{path:path}` | Handler `spa_fallback` in `src/servers/web/server.py`. |
| POST | `/mcp/chat` | Handler `mcp_chat` in `src/servers/api/server.py`. |
| GET | `/mcp/health` | Handler `mcp_health` in `src/servers/api/server.py`. |
| GET | `/a2a/health` | Handler `a2a_health` in `src/servers/api/server.py`. |
| GET | `/` | Handler `root` in `src/servers/api/server.py`. |
| GET | `/metrics` | Handler `metrics` in `src/servers/api/server.py`. |
| GET | `` | Handler `list_sessions` in `src/servers/api/routes/sessions.py`. |
| POST | `` | Handler `create_session` in `src/servers/api/routes/sessions.py`. |
| GET | `/{session_id}` | Handler `get_session` in `src/servers/api/routes/sessions.py`. |
| POST | `/{session_id}/messages` | Handler `add_message` in `src/servers/api/routes/sessions.py`. |
| GET | `/{session_id}/messages` | Handler `get_messages` in `src/servers/api/routes/sessions.py`. |
| GET | `/key/{session_key}` | Handler `get_session_by_key` in `src/servers/api/routes/sessions.py`. |
| GET | `/history/{history_key}` | Handler `get_history_by_key` in `src/servers/api/routes/sessions.py`. |
| POST | `/{session_id}/share` | Handler `share_session` in `src/servers/api/routes/sessions.py`. |
| POST | `/{session_id}/rotate-key` | Handler `rotate_session_key` in `src/servers/api/routes/sessions.py`. |
| POST | `/{session_id}/summarize` | Handler `summarize_session` in `src/servers/api/routes/sessions.py`. |
| GET | `/{session_id}/summaries` | Handler `get_summaries` in `src/servers/api/routes/sessions.py`. |
| DELETE | `/{session_id}` | Handler `delete_session` in `src/servers/api/routes/sessions.py`. |
| GET | `` | Handler `list_operations` in `src/servers/api/routes/operations.py`. |
| GET | `/{operation_id}` | Handler `get_operation_status` in `src/servers/api/routes/operations.py`. |
| POST | `/{operation_id}/cancel` | Handler `cancel_operation` in `src/servers/api/routes/operations.py`. |
| GET | `/{knowledge_type}/{knowledge_id}` | Handler `get_knowledge_history` in `src/servers/api/routes/knowledge.py`. |
| POST | `` | Handler `add_knowledge` in `src/servers/api/routes/knowledge.py`. |
| PUT | `/{knowledge_type}/{knowledge_id}/{entry_id}` | Handler `update_knowledge` in `src/servers/api/routes/knowledge.py`. |
| DELETE | `/{knowledge_type}/{knowledge_id}` | Handler `delete_knowledge` in `src/servers/api/routes/knowledge.py`. |
| GET | `` | Handler `list_knowledge` in `src/servers/api/routes/knowledge.py`. |
| GET | `/{knowledge_type}/{knowledge_id}/versions` | Handler `list_knowledge_versions` in `src/servers/api/routes/knowledge.py`. |
| POST | `/{knowledge_type}/{knowledge_id}/rollback` | Handler `rollback_knowledge` in `src/servers/api/routes/knowledge.py`. |
| PUT | `/{knowledge_id}` | Handler `replace_knowledge` in `src/servers/api/routes/knowledge.py`. |
| POST | `/{knowledge_id}/merge` | Handler `merge_knowledge` in `src/servers/api/routes/knowledge.py`. |
| POST | `/upload_base64` | Handler `upload_file_base64` in `src/servers/api/routes/files.py`. |
| POST | `/upload` | Handler `upload_file` in `src/servers/api/routes/files.py`. |
| POST | `/{file_id}/translate` | Handler `translate_file` in `src/servers/api/routes/files.py`. |
| POST | `/{file_id}/ingest_to_vector_store` | Handler `ingest_file_to_vector_store` in `src/servers/api/routes/files.py`. |
| POST | `/{file_id}/ingest_to_knowledge` | Handler `ingest_file_to_knowledge` in `src/servers/api/routes/files.py`. |
| GET | `` | Handler `list_files` in `src/servers/api/routes/files.py`. |
| GET | `/{file_id}` | Handler `get_file_metadata` in `src/servers/api/routes/files.py`. |
| GET | `/{file_id}/download` | Handler `download_file` in `src/servers/api/routes/files.py`. |
| DELETE | `/{file_id}` | Handler `delete_file` in `src/servers/api/routes/files.py`. |
| POST | `/bulk-delete` | Handler `bulk_delete_files` in `src/servers/api/routes/files.py`. |
| GET | `/storage/stats` | Handler `get_storage_stats` in `src/servers/api/routes/files.py`. |
| GET | `` | Handler `health` in `src/servers/api/routes/health.py`. |
| GET | `/status` | Handler `status` in `src/servers/api/routes/health.py`. |
| POST | `` | Handler `create_vector_store` in `src/servers/api/routes/vector_stores.py`. |
| GET | `` | Handler `list_vector_stores` in `src/servers/api/routes/vector_stores.py`. |
| GET | `/{store_id}` | Handler `get_vector_store` in `src/servers/api/routes/vector_stores.py`. |
| GET | `/{store_id}/health` | Handler `health_check_vector_store` in `src/servers/api/routes/vector_stores.py`. |
| PUT | `/{store_id}` | Handler `update_vector_store` in `src/servers/api/routes/vector_stores.py`. |
| DELETE | `/{store_id}` | Handler `delete_vector_store` in `src/servers/api/routes/vector_stores.py`. |
| POST | `/{store_id}/documents` | Handler `add_document` in `src/servers/api/routes/vector_stores.py`. |
| PUT | `/{store_id}/documents/{doc_id}` | Handler `update_document` in `src/servers/api/routes/vector_stores.py`. |
| DELETE | `/{store_id}/documents/{doc_id}` | Handler `delete_document` in `src/servers/api/routes/vector_stores.py`. |
| POST | `/{store_id}/query` | Handler `query_documents` in `src/servers/api/routes/vector_stores.py`. |
| POST | `` | Handler `create_api_key` in `src/servers/api/routes/api_keys.py`. |
| GET | `` | Handler `list_api_keys` in `src/servers/api/routes/api_keys.py`. |
| DELETE | `/{key_id}` | Handler `revoke_api_key` in `src/servers/api/routes/api_keys.py`. |
| POST | `/{key_id}/rotate` | Handler `rotate_api_key` in `src/servers/api/routes/api_keys.py`. |
| GET | `/me` | Handler `get_my_api_key_permissions` in `src/servers/api/routes/api_keys.py`. |
| GET | `` | Handler `list_users` in `src/servers/api/routes/users.py`. |
| POST | `` | Handler `create_user` in `src/servers/api/routes/users.py`. |
| GET | `/{user_id}` | Handler `get_user` in `src/servers/api/routes/users.py`. |
| PUT | `/{user_id}` | Handler `update_user` in `src/servers/api/routes/users.py`. |
| DELETE | `/{user_id}` | Handler `delete_user` in `src/servers/api/routes/users.py`. |
| GET | `/{user_id}/gdpr/export` | Handler `export_user_gdpr_data` in `src/servers/api/routes/users.py`. |
| DELETE | `/{user_id}/gdpr/delete` | Handler `gdpr_delete_user_data` in `src/servers/api/routes/users.py`. |
| POST | `/generate` | Handler `generate_prompt` in `src/servers/api/routes/prompts.py`. |
| POST | `/test-cases` | Handler `generate_test_cases` in `src/servers/api/routes/prompts.py`. |
| POST | `/validate` | Handler `validate_prompt` in `src/servers/api/routes/prompts.py`. |
| GET | `` | Handler `list_prompt_templates` in `src/servers/api/routes/prompts.py`. |
| POST | `` | Handler `create_prompt_template` in `src/servers/api/routes/prompts.py`. |
| GET | `/{prompt_id}` | Handler `get_prompt_template` in `src/servers/api/routes/prompts.py`. |
| PUT | `/{prompt_id}` | Handler `update_prompt_template` in `src/servers/api/routes/prompts.py`. |
| DELETE | `/{prompt_id}` | Handler `delete_prompt_template` in `src/servers/api/routes/prompts.py`. |
| POST | `/{prompt_id}/test` | Handler `test_prompt_template` in `src/servers/api/routes/prompts.py`. |
| POST | `` | Handler `create_expert` in `src/servers/api/routes/experts.py`. |
| GET | `` | Handler `list_experts` in `src/servers/api/routes/experts.py`. |
| GET | `/{expert_id}` | Handler `get_expert` in `src/servers/api/routes/experts.py`. |
| PUT | `/{expert_id}` | Handler `update_expert` in `src/servers/api/routes/experts.py`. |
| DELETE | `/{expert_id}` | Handler `delete_expert` in `src/servers/api/routes/experts.py`. |
| GET | `/{expert_id}/services` | Handler `list_expert_services` in `src/servers/api/routes/experts.py`. |
| POST | `/{expert_id}/services` | Handler `bind_expert_service` in `src/servers/api/routes/experts.py`. |
| DELETE | `/{expert_id}/services/{service_id}` | Handler `unbind_expert_service` in `src/servers/api/routes/experts.py`. |
| GET | `/{expert_id}/sub-experts` | Handler `list_sub_experts` in `src/servers/api/routes/experts.py`. |
| POST | `/{expert_id}/sub-experts` | Handler `bind_sub_expert` in `src/servers/api/routes/experts.py`. |
| DELETE | `/{expert_id}/sub-experts/{sub_id}` | Handler `unbind_sub_expert` in `src/servers/api/routes/experts.py`. |
| POST | `/{expert_id}/execute` | Handler `execute_expert` in `src/servers/api/routes/experts.py`. |
| POST | `/evaluate` | Handler `evaluate_response` in `src/servers/api/routes/quality.py`. |
| POST | `/feedback` | Handler `submit_feedback` in `src/servers/api/routes/quality.py`. |
| GET | `/job/{job_id}` | Handler `get_quality_metrics` in `src/servers/api/routes/quality.py`. |
| GET | `/api` | Handler `api_documentation` in `src/servers/api/routes/api_docs.py`. |
| GET | `/routes` | Handler `api_routes_summary` in `src/servers/api/routes/api_docs.py`. |
| POST | `` | Handler `create_channel` in `src/servers/api/routes/channels.py`. |
| GET | `` | Handler `list_channels` in `src/servers/api/routes/channels.py`. |
| GET | `/{channel_id}` | Handler `get_channel` in `src/servers/api/routes/channels.py`. |
| GET | `/{channel_id}/llm-config` | Handler `get_channel_llm_config` in `src/servers/api/routes/channels.py`. |
| POST | `/{channel_id}/chat` | Handler `channel_chat` in `src/servers/api/routes/channels.py`. |
| GET | `/{channel_id}/history` | Handler `get_channel_history` in `src/servers/api/routes/channels.py`. |
| POST | `/{channel_id}/vector-stores` | Handler `add_channel_vector_store` in `src/servers/api/routes/channels.py`. |
| GET | `/{channel_id}/vector-stores` | Handler `get_channel_vector_stores` in `src/servers/api/routes/channels.py`. |
| DELETE | `/{channel_id}/vector-stores/{vector_store_id}` | Handler `remove_channel_vector_store` in `src/servers/api/routes/channels.py`. |
| GET | `/{channel_id}/tools` | Handler `list_channel_tools` in `src/servers/api/routes/channels.py`. |
| DELETE | `/{channel_id}/tools/{tool_name}` | Handler `remove_channel_tool` in `src/servers/api/routes/channels.py`. |
| POST | `/{channel_id}/services/{service_id}` | Handler `attach_service_to_channel` in `src/servers/api/routes/channels.py`. |
| GET | `/{channel_id}/services` | Handler `list_channel_services` in `src/servers/api/routes/channels.py`. |
| DELETE | `/{channel_id}/services/{service_id}` | Handler `detach_service_from_channel` in `src/servers/api/routes/channels.py`. |
| DELETE | `/{channel_id}` | Handler `delete_channel` in `src/servers/api/routes/channels.py`. |
| POST | `/register` | Handler `register` in `src/servers/api/routes/auth.py`. |
| POST | `/login` | Handler `login` in `src/servers/api/routes/auth.py`. |
| POST | `/logout` | Handler `logout` in `src/servers/api/routes/auth.py`. |
| GET | `/validate` | Handler `validate` in `src/servers/api/routes/auth.py`. |
| POST | `/refresh` | Handler `refresh` in `src/servers/api/routes/auth.py`. |
| POST | `/change-password` | Handler `change_password` in `src/servers/api/routes/auth.py`. |
| POST | `/admin-reset-password` | Handler `admin_reset_password` in `src/servers/api/routes/auth.py`. |
| POST | `/expert-suite` | Handler `run_expert_test_suite` in `src/servers/api/routes/testing.py`. |
| POST | `` | Handler `create_service` in `src/servers/api/routes/services.py`. |
| GET | `` | Handler `list_services` in `src/servers/api/routes/services.py`. |
| GET | `/{service_id}` | Handler `get_service` in `src/servers/api/routes/services.py`. |
| PUT | `/{service_id}` | Handler `update_service` in `src/servers/api/routes/services.py`. |
| DELETE | `/{service_id}` | Handler `delete_service` in `src/servers/api/routes/services.py`. |
| POST | `/{service_id}/health` | Handler `check_service_health` in `src/servers/api/routes/services.py`. |
| POST | `/llm` | Handler `validate_llm` in `src/servers/api/routes/validation.py`. |
| POST | `/prompt` | Handler `validate_prompt` in `src/servers/api/routes/validation.py`. |
| GET | `` | Handler `list_jobs` in `src/servers/api/routes/jobs.py`. |
| GET | `/{job_id}` | Handler `get_job` in `src/servers/api/routes/jobs.py`. |
| DELETE | `/{job_id}` | Handler `remove_job` in `src/servers/api/routes/jobs.py`. |
| POST | `/{job_id}/resubmit` | Handler `resubmit_job` in `src/servers/api/routes/jobs.py`. |
| POST | `/{job_id}/stop` | Handler `stop_job` in `src/servers/api/routes/jobs.py`. |
| GET | `/queue/status` | Handler `get_queue_status` in `src/servers/api/routes/jobs.py`. |
| GET | `` | Handler `get_audit_events` in `src/servers/api/routes/audit.py`. |
| GET | `/{event_id}` | Handler `get_audit_event` in `src/servers/api/routes/audit.py`. |
| GET | `/{event_id}/raw` | Handler `get_audit_event_raw` in `src/servers/api/routes/audit.py`. |
| GET | `/{event_id}/verify` | Handler `verify_audit_event_signature` in `src/servers/api/routes/audit.py`. |
| GET | `/export/{format}` | Handler `export_audit_logs` in `src/servers/api/routes/audit.py`. |
| POST | `` | Handler `create_group` in `src/servers/api/routes/groups.py`. |
| GET | `` | Handler `list_groups` in `src/servers/api/routes/groups.py`. |
| GET | `/{group_id}` | Handler `get_group` in `src/servers/api/routes/groups.py`. |
| PUT | `/{group_id}` | Handler `update_group` in `src/servers/api/routes/groups.py`. |
| DELETE | `/{group_id}` | Handler `delete_group` in `src/servers/api/routes/groups.py`. |
| GET | `/{group_id}/members` | Handler `get_group_members` in `src/servers/api/routes/groups.py`. |
| POST | `/{group_id}/members` | Handler `add_group_member` in `src/servers/api/routes/groups.py`. |
| POST | `/{group_id}/admins` | Handler `assign_group_admin` in `src/servers/api/routes/groups.py`. |
| GET | `/{group_id}/admins` | Handler `get_group_admins` in `src/servers/api/routes/groups.py`. |
| DELETE | `/{group_id}/admins/{user_id}` | Handler `remove_group_admin` in `src/servers/api/routes/groups.py`. |
| PUT | `/{group_id}/members/{user_id}/role` | Handler `update_member_role` in `src/servers/api/routes/groups.py`. |
| DELETE | `/{group_id}/members/{user_id}` | Handler `remove_group_member` in `src/servers/api/routes/groups.py`. |

## Example Request
```bash
curl -H "Authorization: Bearer your-api-key" http://localhost:8083/health
```

## Example Response
```json
{
  "ok": true,
  "result": {
    "status": "healthy"
  }
}
```


<!-- W28C-1710a recovery: full content from archive/2026-06-12/API_SERVER.md (archived sha256=21d7f55532d3, 389 lines) -->

## Recovered domain content — `archive/2026-06-12/API_SERVER.md` (389 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/API_SERVER.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# API Server Documentation
**Version:** 0.1 • 2025-01-XX

## Overview

The API Server provides RESTful endpoints for conversation management, configuration APIs, and inbound callbacks for the Expert Agent MCP Server.

**Port:** 8083 (configurable via `CLOUD_DOG__EXPERT__API_SERVER__PORT`)

## Quick Start

### Running the API Server

```bash
# Using server control script (required by RULES.md)
./server_control.sh --env private/env-test start api
```

### Configuration

API Server configuration is loaded from:
1. Environment Variables (`CLOUD_DOG__EXPERT__*`)
2. `.env` file
3. `config.yaml`
4. `default.yaml`

**Key Configuration Options:**
```bash
CLOUD_DOG__EXPERT__API_SERVER__PORT=8083
CLOUD_DOG__EXPERT__API_SERVER__HOST=0.0.0.0
CLOUD_DOG__EXPERT__API_SERVER__API_KEY=your-secret-key
```

### Health Check

```bash
# Check server health (no auth required)
curl http://localhost:8083/health

# Check system status (no auth required)
curl http://localhost:8083/health/status
```

## Key Features

### 1. Session Management
- Create, retrieve, update, and delete conversation sessions
- Session history management
- Session state tracking

### 2. Expert Configuration Management
- List and manage expert configurations
- Configure LLM providers and parameters
- Manage prompts and system messages

### 3. Vector Database Integration
- Knowledge base management
- Vector store operations
- Collection management

### 4. User & Group Management
- User CRUD operations
- Group membership management
- RBAC (Role-Based Access Control)

### 5. System Monitoring
- Health checks
- Queue depth and status
- LLM availability status
- Metrics and observability

## Architecture

### Components

- **FastAPI Application**: REST API framework
- **Session Manager**: Manages conversation sessions
- **LLM Orchestrator**: Coordinates LLM interactions
- **Vector Store Manager**: Handles knowledge retrieval
- **User Manager**: Authentication and authorization
- **Database Layer**: Data persistence

### Data Flow

```
Client Request
  ↓
API Server (FastAPI)
  ↓
Authentication (API Key)
  ↓
Route Handler
  ↓
Business Logic (Session/Expert/Vector Manager)
  ↓
Database/LLM/Vector Store
  ↓
Response
```

## Protocol/Interface Details

### Authentication

All endpoints (except `/health`) require API key authentication via `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8083/sessions
```

### Request/Response Formats

- **Content-Type**: `application/json`
- **Response Format**: JSON
- **Error Format**: JSON with `detail` field

### Core Endpoints

#### Health & Status
- `GET /health` - Server health check (public, no auth)
- `GET /status` - Queue depth and system status (requires API key)
- `GET /llm/status` - LLM queue status (requires API key)

#### Sessions
- `POST /sessions` - Create a new session
- `GET /sessions/{id}` - Get session details
- `GET /sessions/{id}/history` - Get conversation history
- `PUT /sessions/{id}` - Update session
- `DELETE /sessions/{id}` - Delete session
- `POST /sessions/{id}/end` - End an active session

#### Expert Configurations
- `GET /experts` - List expert configurations
- `GET /experts/{name}` - Get expert configuration details
- `POST /experts` - Create expert configuration
- `PUT /experts/{name}` - Update expert configuration
- `DELETE /experts/{name}` - Delete expert configuration

#### Vector Database / Knowledge Base
- `GET /knowledge` - List knowledge base entries
- `POST /knowledge` - Add knowledge base entry
- `GET /knowledge/{id}` - Get knowledge entry
- `DELETE /knowledge/{id}` - Delete knowledge entry

#### Users & Groups
- `GET /users` - List users
- `GET /users/{id}` - Get user details
- `POST /users` - Create user
- `PUT /users/{id}` - Update user
- `DELETE /users/{id}` - Delete user
- `GET /groups` - List groups
- `POST /groups` - Create group
- `GET /groups/{id}` - Get group details

## Key Flows

### Session Creation Flow
```
POST /sessions
  ↓
Validate request & authenticate
  ↓
Create session via Session Manager
  ↓
Initialize with expert configuration
  ↓
Return session_id and status
```

### Conversation Flow
```
POST /sessions/{id}/messages
  ↓
Validate session is active
  ↓
Queue message via Session Manager
  ↓
LLM Orchestrator processes message
  ↓
Vector Store retrieves relevant context
  ↓
Return response
```

## Usage Examples

### Create Session
```bash
curl -X POST http://localhost:8083/sessions \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "expert_name": "_DEFAULT_",
    "user_id": "user@example.com"
  }'
```

### Get Session History
```bash
curl -X GET http://localhost:8083/sessions/{session_id}/history \
  -H "X-API-Key: your-api-key"
```

## Configuration

### Environment Variables

All configuration uses `CLOUD_DOG__EXPERT__` prefix:

```bash
# API Server
CLOUD_DOG__EXPERT__API_SERVER__PORT=8083
CLOUD_DOG__EXPERT__API_SERVER__HOST=0.0.0.0
CLOUD_DOG__EXPERT__API_SERVER__API_KEY=your-secret-key

# Database
CLOUD_DOG__EXPERT__DB__URI=sqlite:///expert.db

# LLM
CLOUD_DOG__EXPERT__LLM__PROVIDER=ollama
CLOUD_DOG__EXPERT__LLM__BASE_URL=http://localhost:11434
CLOUD_DOG__EXPERT__LLM__MODEL=qwen3:14b
```

See [PARAMETERS.md](PARAMETERS.md) for complete configuration reference.

## Startup & Deployment

### Development
```bash
./server_control.sh start api
```

### Production
- Use `server_control.sh` for service management
- Configure via environment variables or `config.yaml`
- Ensure database is accessible
- Verify LLM provider connectivity

## Error Handling

### Error Response Format
```json
{
  "detail": "Error message description"
}
```

### Common HTTP Status Codes
- `200 OK` - Success
- `201 Created` - Resource created
- `400 Bad Request` - Invalid request
- `401 Unauthorized` - Missing or invalid API key
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Performance

### Optimization
- Connection pooling for database
- Async request handling
- Caching for expert configurations
- Rate limiting (configurable)

### Benchmarks
- Typical response time: < 100ms (non-LLM endpoints)
- LLM endpoints: 5-30 seconds (depending on model)
- Concurrent requests: Configurable via pool size

## Monitoring & Troubleshooting

### Health Checks
```bash
# Basic health
curl http://localhost:8083/health

# Detailed status
curl -H "X-API-Key: your-api-key" http://localhost:8083/status
```

### Logging
- Log files: `logs/api_server.log`
- Log level: Configurable via `CLOUD_DOG__EXPERT__LOG__LEVEL`
- Format: JSON or standard (configurable)

### Metrics
- Prometheus metrics endpoint: `/metrics` (if enabled)
- Queue depth monitoring
- Request rate tracking

### Common Issues

1. **Port already in use**: Change port via configuration
2. **Database connection failed**: Verify `CLOUD_DOG__EXPERT__DB__URI`
3. **LLM provider unavailable**: Check LLM provider connectivity
4. **API key authentication failed**: Verify `X-API-Key` header

## Security Considerations

### Authentication
- API key authentication required for all endpoints (except `/health`)
- API keys should be stored securely (environment variables, not in code)
- Use HTTPS in production

### Authorization
- RBAC (Role-Based Access Control) for user/group management
- Expert configuration access control
- Vector database collection-based separation

### Data Protection
- PII removal options (configurable)
- Data encryption at rest (configurable)
- Audit logging for compliance

## Scaling

### Horizontal Scaling
- Multiple API server instances can run concurrently
- Shared database backend
- Stateless design (sessions stored in database)

### Vertical Scaling
- Increase connection pool size
- Adjust worker processes
- Optimize database queries

## Advanced Features

### Async Processing
- Long-running operations use async processing
- Job queue for LLM operations
- Webhook callbacks (if configured)

### Customization
- Custom expert configurations
- Custom prompts and system messages
- Vector store provider selection

## Best Practices

### API Usage
- Always include `X-API-Key` header
- Use appropriate HTTP methods
- Handle errors gracefully
- Implement retry logic with backoff

### Security
- Never commit API keys to version control
- Use environment variables for sensitive data
- Enable HTTPS in production
- Regularly rotate API keys

### Development
- Use `server_control.sh` for server management
- Test locally before deploying
- Monitor logs for errors
- Use health checks in CI/CD

## Future Enhancements

- WebSocket support for real-time updates
- GraphQL API option
- Enhanced rate limiting
- API versioning
- OpenAPI/Swagger UI improvements

## Resources

- **Source Code**: `src/servers/api/`
- **Configuration**: `default.yaml`, `config.yaml`, `.env`
- **Related Documentation**:
  - [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - Complete API reference
  - [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
  - [PARAMETERS.md](PARAMETERS.md) - Configuration parameters
  - [RULES.md](../RULES.md) - Project rules

## Support

- **Repository**: Expert Agent MCP Server
- **Issues**: GitHub Issues (if applicable)
- **License**: Apache 2.0

---

**Related Documentation:**
- [MCP_SERVER.md](MCP_SERVER.md) - MCP Server specification
- [A2A_SERVER.md](A2A_SERVER.md) - A2A Server specification
- [WEB_UI.md](WEB_UI.md) - Web UI Server specification
