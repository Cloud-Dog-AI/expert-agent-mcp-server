---
template-id: T-REQ
template-version: 1.1
applies-to: docs/REQUIREMENTS.md
project: expert-agent-mcp-server
doc-last-updated: 2026-06-21
doc-git-commit: b7435e2385704de114dd5255d5005d11b73fd39a
doc-git-branch: main
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-21T00:00:00Z
req-trace-version: 1.0
req-id-prefixes-used: [SV, BO, BR, FR, UC, CS, NF, R, F]
surface-coverage: [api, mcp, a2a, webui]
---

# Expert Agent MCP Server — REQUIREMENTS.md
## W28A-421 Review Status
- Reviewed for external/shareable publication during W28A-421.
- Source basis: `defaults.yaml`, 29 server source files, 186 discovered routes/endpoints, and 29 MCP tools.
- Internal-only absolute paths, environment-specific hosts, and private registries have been removed from this shareable document set.

**Version:** 0.3 • 2026-02-11
**Status:** Active Development
**Last Updated:** 2026-02-11
**Organization:** Cloud-Dog / Cloud-Dog Engineering

<!-- DIRECTIVE: No Changes must be made without approval. The process will always be plan, build tests, develop, check tests, evaluate. -->
<!-- DIRECTIVE: Do Not proceed beyond what you have been told to do at any time without clear authorisation. -->
<!-- DIRECTIVE: Maintain the tasks and tests with easy to follow trackers. -->
<!-- DIRECTIVE: There is a working folder for all reports, tests, working documents which must be used by the agent. -->
<!-- DIRECTIVE: Any Private information must be stored in the private folder (including for example env-build, env-docker and the such which have u/p/urls etc). -->
<!-- DIRECTIVE: There should be an archive folder, where all unwanted docs/files/folders get placed. -->
<!-- DIRECTIVE: The docs folder must not expand unless requested. Key information will be folded into the tasks, the requirements or the architecture. Don't expand and generate rubbish. -->

---

## Executive Summary

The Expert Agent MCP Server is an intelligent conversational AI platform that enables users to interact with multiple expert configurations through natural language conversations. Powered by Large Language Models (LLMs) and enhanced with vector database integration, the system provides persistent session history, contextual awareness, and knowledge retrieval capabilities.

**Key Capabilities:**
- ✅ Multi-expert configuration system with distinct LLM settings, prompts, and behaviors
- ✅ Persistent session management with configurable retention and context window handling
- ✅ Vector database integration (Chroma, Weaviate, Qdrant, OpenSearch, Elastic, PGVector) for knowledge retrieval
- ✅ Multi-protocol access (REST API, Web UI, MCP, A2A) for diverse integration scenarios
- ✅ Comprehensive user and group management with role-based access control
- ✅ Multiple authentication providers (local, Google, LinkedIn, Keycloak SAML/OpenID)
- ✅ Real-time conversation management with rate limiting and circuit breaker patterns
- ✅ Production-ready with Docker deployment support and comprehensive monitoring
- ✅ Cryptographic audit trail with non-repudiation for compliance
- ✅ PII removal and data protection for GDPR/CCPA compliance

**Architecture Highlights:**
- Four-server composition: API (18083), Web UI (18080), MCP (18081), A2A (18082)
- Session-based conversation orchestration with concurrency control
- Vector store integration with collection-based group isolation
- LLM orchestration with prompt engineering and safety controls
- Comprehensive observability (metrics, logging, tracing)

---

## Document Structure

This document follows the structure defined in RULES.md:
- **SV** = Scope/Vision (Section 1)
- **BO** = Business Goals/Objectives (Section 2)
- **BR** = Business/Application Requirements (Section 3)
- **FR** = Project/Functional Requirements/Features
- **UC** = Use Cases (Section 4)
- **CS** = Cyber Security (Section 5)
- **NF** = Non-Functional Requirements: Operational, Audit, Deployment (Section 6)
- **CM** = Common Requirements

**Numbering Logic**: Each prefix restarts from 1.1 (e.g., SV1.1, SV1.2, BO1.1, BO1.2, BR1.1, BR1.2, FR1.1, FR1.2, UC1.1, UC1.2, CS1.1, NF1.1, CM1.1)

---

## CM1.1: Common LLM Client Module (MANDATORY)

**Requirement ID**: CM1.1  
**Priority**: CRITICAL  
**Status**: IMPLEMENTED

**Description**:
ALL code in the codebase MUST use the centralized LLM client module (`src.common.llm_client`) for LLM interactions. This module provides configuration-driven, consistent, and properly-configured LLM access.

**Mandatory Requirements**:
1. **NO hardcoded LLM connection details** - All configuration from config system
2. **NO direct httpx.AsyncClient creation** for LLM operations
3. **ALL src/ code** MUST use `from src.common.llm_client import get_llm_client`
4. **ALL tests** MUST use `from src.common.llm_client import get_llm_client`
5. **Proper timeout configuration** - Separate connect (30s) and read (300s) timeouts
6. **Consistent error handling** - Retry logic for transient failures
7. **Provider abstraction** - Support for Ollama, OpenAI, OpenRouter

**Usage Pattern**:
```python
from src.common.llm_client import get_llm_client

# Get client (loads from config)
async with get_llm_client() as client:
    response = await client.chat(
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.7,
        max_tokens=1024
    )
```

**Configuration**:
- `llm.provider` - Provider name (ollama, openai, openrouter)
- `llm.base_url` - LLM service URL
- `llm.model` - Model name
- `llm.api_key` - API key (if required)
- `llm.timeout` - Timeout in seconds (default: 300)

**Benefits**:
- Prevents timeout bugs (httpx read timeout issues)
- Eliminates hardcoded values
- Ensures consistent configuration
- Centralized error handling
- Easy to test and mock

**Compliance**:
- See RULES.md: "NEVER hardcode LLM connection details"
- See ARCHITECTURE.md: CC1.8 - Common LLM Client

---

## 1. Scope/Vision (SV)

### SV1.1: System Overview
An intelligent conversational agent platform composed of four servers (API/REST, MCP, A2A, Web UI/Admin). It provides access to one or more LLMs with persistent session history, contextual awareness, and vector database integration for knowledge retrieval and storage. The system supports multiple expert configurations with different LLMs, parameters, and prompts to exhibit different behaviors and expertise domains.

**Alignment**: [ARCH:OV1.1](ARCHITECTURE.md#ov11), [TASK:T001](TASKS.md#t001)

### SV1.2: In-Scope (v1)
- Four-server architecture: API/REST, MCP, A2A, Web UI/Admin
- Multiple expert configurations with distinct LLM settings, prompts, and parameters
- Session history management with configurable retention policies
- Vector database integration (Chroma, Weaviate, Qdrant, OpenSearch, Elastic, PGVector)
- Knowledge base management with lifecycle options (purge, compress, consolidate)
- User authentication via local database, external providers (Google, LinkedIn), or SAML/OpenID
- Group-based access control for configurations, vector stores, and history
- Comprehensive audit logging of all interactions including user/client details
- Web UI resembling OpenAI Chat interface with configuration management capabilities
- Prometheus metrics exposure for monitoring
- Configuration management hierarchy: environment variables → .env file → config.yaml → defaults.yaml
- SQLite3 for development/testing with MySQL/PostgreSQL support for production
- Redis/Valkey for queue management with SQL transactional fallback

**Alignment**: [ARCH:SA1.1](ARCHITECTURE.md#sa11), [TASK:T001](TASKS.md#t001)

### SV1.3: Out-of-Scope (v1)
- Multimodal support (images, files) - planned for v1.1
- Advanced journey orchestration - planned for v1.2
- Full multi-tenant isolation - planned for v1.2

**Alignment**: [ARCH:OV1.1](ARCHITECTURE.md#ov11)

---

## 2. Business Goals/Objectives (BO)

### BO1.1: Intelligent Conversations
Provide intelligent, context-aware conversations with persistent session history.

**Alignment**: [ARCH:CC2.1](ARCHITECTURE.md#cc21), [TASK:T022](TASKS.md#t022), [TEST:AT1.1](TESTS.md#at11)

### BO1.2: Multiple Expert Configurations
Support multiple expert configurations with customizable LLMs, parameters, and prompts to exhibit different behaviors and expertise domains.

**Alignment**: [ARCH:CC3.1](ARCHITECTURE.md#cc31), [TASK:T007](TASKS.md#t007), [TEST:AT1.2](TESTS.md#at12)

### BO1.3: Vector Database Integration
Provide vector database integration for knowledge retrieval, storage, and contextual enhancement.

**Alignment**: [ARCH:CC4.1](ARCHITECTURE.md#cc41), [TASK:T014](TASKS.md#t014), [TEST:IT2.1](TESTS.md#it21)

### BO1.4: Operational Controls
Provide clear operational controls (rate limits, circuit breakers, TTL, retries, session limits).

**Alignment**: [ARCH:CP1.1](ARCHITECTURE.md#cp11), [TASK:T027](TASKS.md#t027), [TEST:ST1.1](TESTS.md#st11)

### BO1.5: Admin Experience
Deliver first-class admin experience in Web UI with configuration management.

**Alignment**: [ARCH:CC1.2](ARCHITECTURE.md#cc12), [TASK:T030](TASKS.md#t030), [TEST:AT1.3](TESTS.md#at13)

### BO1.6: Code Reuse
Strong reuse of existing Notification Agent and SQL Agent MCP project patterns.

**Alignment**: [ARCH:DO1.1](ARCHITECTURE.md#do11), [TASK:T001](TASKS.md#t001)

---

## 3. Business/Application Requirements (BR)

### BR1.1: Multi-Expert Support
System shall support multiple expert configurations with distinct LLM settings, prompts, and parameters.

**Alignment**: [ARCH:CC3.1](ARCHITECTURE.md#cc31), [TASK:T007](TASKS.md#t007), [TEST:IT2.2](TESTS.md#it22)

### BR1.2: User Management
System shall provide comprehensive user management including local users, external identity providers (Google, LinkedIn, Keycloak), groups, and preferences.

**Alignment**: [ARCH:CC5.1](ARCHITECTURE.md#cc51), [TASK:T005](TASKS.md#t005), [TEST:AT1.4](TESTS.md#at14)

### BR1.3: Session Management
System shall provide persistent session history with configurable retention policies and context window management.

**Alignment**: [ARCH:CC2.1](ARCHITECTURE.md#cc21), [TASK:T022](TASKS.md#t022), [TEST:AT1.5](TESTS.md#at15)

### BR1.4: Vector Database Integration
System shall support multiple vector database providers (Chroma, Weaviate, Qdrant, OpenSearch, Elastic, PGVector) with lifecycle management.

**Alignment**: [ARCH:CC4.1](ARCHITECTURE.md#cc41), [TASK:T014](TASKS.md#t014), [TEST:IT2.3](TESTS.md#it23)

---

## 4. Functional Requirements/Features (FR)

### FR1.1: Expert Configurations
System shall support expert configurations with title, description, scope, LLM settings, prompts, and tool configurations. Support multiple LLM providers (Ollama, OpenAI-compatible, custom). Configure different parameters per expert (temperature, max tokens, etc.). Enable/disable configurations with access control. Auto-generate example prompts from configuration title/description. Validate user-provided prompts against safety and format guidelines.

**Prompt engineering (local/API):**
- Enforce **mandatory** `title` and `description` for expert creation/update
- Reject low-signal configurations via a simple **entropy** threshold (config-driven)
- Auto-generate `prompt_template` from `title` + `description` when omitted
- Config keys:
  - `prompts.min_description_chars`
  - `prompts.entropy_min_unique_words`
- REST endpoints:
  - `POST /prompts/generate` (generate example prompt)
  - `POST /validation/prompt` (LLM-backed prompt validation against requirements)

**Alignment**: [ARCH:CC3.1](ARCHITECTURE.md#cc31), [TASK:T007](TASKS.md#t007), [TASK:T012](TASKS.md#t012), [TEST:IT2.4](TESTS.md#it24)

### FR1.2: Conversation Management
System shall provide persistent session history with configurable retention periods. Shared or personal history contexts based on authentication. Context window management with automatic summarization for long conversations. Real-time conversation state synchronization across distributed servers. Conversation tagging and categorization for organization. All logs/history access must be separated by users/groups - users only see their stuff or stuff they are allowed to see. Option to remove PII from session, history, returned results, or audit based on use case. Controls for maximum number of concurrent sessions per user/group. Session queuing and resource management when concurrency limits are reached. Graceful handling of session limits with appropriate user notifications.

**Concurrency controls (local/API):**
- Enforce configurable per-user/per-group session limits (`session.max_sessions_per_user`, `session.max_sessions_per_group`)
- Support queuing when limits are exceeded (`session.queue_enabled`)
- Ensure high-frequency requests do not produce 5xx and return deterministic queued/limited responses

**Alignment**: [ARCH:CC2.1](ARCHITECTURE.md#cc21), [TASK:T022](TASKS.md#t022), [TASK:T027](TASKS.md#t027), [TEST:IT2.5](TESTS.md#it25)

### FR1.3: Vector Database Integration
System shall support Chroma (dev/test), Weaviate, Qdrant, OpenSearch, Elastic, PGVector. Map vector databases to specific configurations/sessions. Lifecycle management: purge after time, compress/consolidate after time. Indexing options exposing all provider-specific parameters and metadata fields. Search, filter, and removal of threads/context within vector stores. Access control for read/write permissions on vector stores. Use collections to separate each vector instance across groups. Ensure no cross-talk/data between different groups/databases on the same host. Vector database will use Chroma locally by default/dev/test and be configurable for all other providers.

**Alignment**: [ARCH:CC4.1](ARCHITECTURE.md#cc41), [TASK:T014](TASKS.md#t014), [TASK:T019](TASKS.md#t019), [TEST:IT2.6](TESTS.md#it26)

### FR1.4: Knowledge Management
System shall provide historical context used to enhance learning and responses. Knowledge base ingestion from various sources (documents, APIs, other agents). Automated knowledge consolidation and optimization. Versioning and rollback capabilities for knowledge bases. Removal of unwanted/bad information based on keywords, times, channels, etc.

**Alignment**: [ARCH:CC4.2](ARCHITECTURE.md#cc42), [TASK:T017](TASKS.md#t017), [TASK:T018](TASKS.md#t018), [TEST:AT1.6](TESTS.md#at16)

### FR1.5: User & Group Management
System shall provide local user authentication (username/password/email) with admin roles. External authentication providers (Google, LinkedIn, etc.). SAML/OpenID integration with identity providers (Keycloak, etc.). Group membership with role-based access control. Group administrators who can manage group memberships. Unauthorized user access with per-configuration read/write permissions. Group authentication read from mapped fields in the identity provider.

**Alignment**: [ARCH:CC5.1](ARCHITECTURE.md#cc51), [TASK:T005](TASKS.md#t005), [TASK:T006](TASKS.md#t006), [TEST:AT1.7](TESTS.md#at17)

### FR1.6: Access Control & Authorization
System shall provide configuration access by individual users or groups. Vector store read/write permissions by users or groups. Session history access controls (personal vs shared). Role-based permissions for administration functions. Audit trails for all access and administrative actions.

**Alignment**: [ARCH:SE1.1](ARCHITECTURE.md#se11), [TASK:T006](TASKS.md#t006), [TEST:ST1.2](TESTS.md#st12)

### FR1.7: API & Integration
System shall provide RESTful API endpoints for all core functionality. MCP tools for agent-to-agent interactions. A2A streaming for real-time events and status updates. Webhook support for external integrations. Natural language commands for conversation initiation and control. Support for both synchronous and asynchronous API calls. Async response handling with callback mechanisms. Long-running operation support with status polling.

MCP transport and protocol compliance requirements:
- Support MCP transport modes: `streamable_http`, `http_jsonrpc`, `legacy_sse`, and `stdio`.
- For HTTP JSON-RPC flows, support `initialize`, `notifications/initialized`, `tools/list`, and `tools/call`.
- Return structured JSON-RPC errors for invalid methods/params (no silent success/null).
- Support session lifecycle semantics for streamable HTTP:
  - Session creation/continuation via `Mcp-Session-Id`
  - Session termination via `DELETE /mcp`
  - Expired/invalid session response contract after termination
- Support optional async job resolution for `tools/call` with `wait=false`:
  - Immediate job reference payload (`job_id`/`guid`)
  - Polling endpoint (`GET /jobs/{job_id}`) returning `running` or final `completed`/`failed` result contract
- Support legacy SSE compatibility mode:
  - SSE bootstrap endpoint (`/sse`) emitting endpoint/session metadata
  - Message ingress endpoint (`/message`) with JSON-RPC request correlation by `id`
  - Structured JSON-RPC responses emitted on the active SSE stream
 - Support HTTP JSON-RPC "messages" compatibility mode:
   - Request endpoint: `POST /messages` with JSON-RPC payloads
   - Session tracking via explicit `session_id` query parameter (recommended)
   - If `session_id` is omitted on `initialize`, server returns a generated session id via `Mcp-Session-Id` response header

**Alignment**: [ARCH:AI1.1](ARCHITECTURE.md#ai11), [ARCH:CC1.1.3](ARCHITECTURE.md#cc113), [TASK:T030](TASKS.md#t030), [TEST:ST1.2](TESTS.md#st12)

### FR1.8: Web UI & Administration
System shall provide chat interface resembling OpenAI Chat or OpenWebUI. Left sidebar for chat session navigation. Configuration selection per user permissions. Admin panel for user/group management, logs, and service configuration. Customizable UI elements (name, title, logo) via config files. Real-time monitoring dashboards with metrics visualization.

Web authentication requirements:
- Web UI login MUST use username/password (no direct API-key prompt in browser UI).
- Successful login MUST establish a secure server-managed web session (cookie/session middleware).
- Web UI API calls MUST flow through server-side authenticated proxy routes (`/web/api/*`) using session token, not exposing API keys in browser storage or JS constants.
- Logout MUST clear web session and block further proxied API calls until re-authenticated.
- API key management remains available for admin/programmatic use, but not required for normal Web UI user login.

**Alignment**: [ARCH:CC1.2](ARCHITECTURE.md#cc12), [TASK:T030](TASKS.md#t030), [TEST:AT1.8](TESTS.md#at18)

### FR1.9: Observability & Monitoring
System shall provide structured logging with redaction of sensitive information. Prometheus metrics exposure for all core services. Health check endpoints for each server component. Performance metrics (response time, throughput, error rates). Resource utilization monitoring (CPU, memory, disk, network).

**Alignment**: [ARCH:MO1.1](ARCHITECTURE.md#mo11), [TASK:T040](TASKS.md#t040), [TEST:ST1.3](TESTS.md#st13)

### FR1.10: Audit & Compliance
System shall provide comprehensive audit logging of all user interactions. Client details capture (IP, user agent, endpoint accessed). Request/response logging with timestamp and user context. Cryptographic signing of audit entries for non-repudiation. Configurable retention policies for audit logs. GDPR-compliant data export and deletion capabilities. Option to remove PII from audit logs based on use case.

**Alignment**: [ARCH:SE1.3](ARCHITECTURE.md#se13), [TASK:T041](TASKS.md#t041), [TEST:ST1.4](TESTS.md#st14)

### FR1.11: Reliability & Controls
System shall provide per-user and per-group rate limits (N per minute/hour/day). Circuit breaker: soft/hard error thresholds flip to degraded/unavailable. Backoff with jitter; categorise errors as transient/permanent. TTL expiry transitions pending sessions to expired state. Configurable maximum concurrent session limits per user/group. Resource throttling and queue management for session control. Support for both sync and async processing models.

**Alignment**: [ARCH:CP1.1](ARCHITECTURE.md#cp11), [TASK:T027](TASKS.md#t027), [TASK:T042](TASKS.md#t042), [TEST:ST1.5](TESTS.md#st15)

### FR1.12: Channel-Based Expert Configurations
System shall support channel-based expert configurations where each channel represents a specific use case or scenario. Channels shall have distinct LLM settings, parameters, prompts, and tool configurations. History can be defined on a user, channel, or session basis with configurable limitations (e.g., only remember last 3 weeks). History can be shared across different expert channels by session key or user. Each channel can have multiple vector database knowledge bases that augment search. Channels may use rerank models for improved retrieval. Channels may have one or more tools and other agents they can call to resolve queries.

**Alignment**: [ARCH:CC3.1](ARCHITECTURE.md#cc31), [TASK:T050](TASKS.md#t050), [TEST:AT1.13](TESTS.md#at113)

### FR1.13: Multimedia Processing
System shall support processing and returning multimedia information including images, audio, and movies in expert conversations. System shall handle file uploads, storage, processing, and return of multimedia content. Support for image analysis, audio transcription, and video processing. Integration with LLM providers that support multimodal inputs (e.g., GPT-4 Vision, Claude with vision).

**Alignment**: [ARCH:CC3.1.3](ARCHITECTURE.md#cc313), [TASK:T051](TASKS.md#t051), [TEST:AT1.105](TESTS.md#at1105)

### FR1.14: Comprehensive Job/Call Logging
System shall record each session with a full log containing all significant events. For each LLM/Expert call, system shall save a complete job/call record with all information including: prompts sent, responses received, metadata (timestamps, user, channel, session), performance metrics (latency, token counts, costs), vector retrieval context, tool calls made, and error information. All job records shall be searchable, filterable, and downloadable.

**Alignment**: [ARCH:CC7.1](ARCHITECTURE.md#cc71), [TASK:T052](TASKS.md#t052), [TEST:ST1.20](TESTS.md#st120)

### FR1.15: Auto-Prompt Generation
System shall provide an interface to take an expert description (title, details, context type, expected outcomes) and automatically generate an example prompt and settings that encapsulate the prompt, tool calls (from available set), and configuration recommendations. System shall use LLM validation to check prompt conformity to patterns/requirements. Generated prompts shall include appropriate tool selections based on context type and expected outcomes.

**Alignment**: [ARCH:CC3.1.4](ARCHITECTURE.md#cc314), [TASK:T053](TASKS.md#t053), [TEST:AT1.107](TESTS.md#at1107)

### FR1.16: Tool & External Service Management
System shall allow users to add tool definitions to channels. System shall support adding external A2A/MCP services into the system with health checking to verify they are working/responding. Services can be applied to one or more channels to make them available. System shall provide prompt evaluation capabilities to assess if channel prompts need enhancing when new tools/services are added. Tool definitions shall include input/output schemas, authentication requirements, and usage guidelines.

**Alignment**: [ARCH:CC8.1](ARCHITECTURE.md#cc81), [TASK:T054](TASKS.md#t054), [TEST:AT1.110](TESTS.md#at1110)

### FR1.17: API Key Management
System shall provide API key management for users and groups. API keys shall provide read and/or write access to channels, logs, and histories. Group admins can manage API keys for their groups. System users can define API keys with appropriate scopes. API keys shall support rotation, expiration, and revocation. Keys shall be securely stored and masked in logs.

**Scope and behaviour:**
- Create, list, rotate, revoke, and expire keys for users and groups.
- Enforce scope-based access control per key (read/write for channels, logs, histories, jobs).
- Support per-key metadata (owner, group, created_at, expires_at, last_used_at, status).
- Keys are shown only once on creation and never stored in plaintext.

**Security and audit:**
- Store keys as salted hashes; compare via constant-time checks.
- Mask keys in logs and responses (show prefix only).
- Emit audit events for create, rotate, revoke, expire, and use (success/failure).

**Configuration:**
- Default expiry, minimum length, and allowed scopes are config-driven.
- Per-environment limits for number of active keys per user/group.

**Error handling:**
- Invalid or expired key returns 401 with a reason code.
- Insufficient scope returns 403 with required scope details.

**Acceptance criteria:**
- All key lifecycle operations are available via API with strict auth.
- Revoked or expired keys are rejected immediately.
- Audit trail contains all key events with masked identifiers.

**Alignment**: [ARCH:CC5.1.3](ARCHITECTURE.md#cc513), [TASK:T055](TASKS.md#t055), [TEST:ST1.31](TESTS.md#st131), [TEST:IT2.24](TESTS.md#it224), [TEST:AT1.94](TESTS.md#at194)

### FR1.18: OpenRouter Integration
System shall support creating Ollama and OpenAI-compatible channels/Experts using an OpenRouter.ai endpoint. System shall handle OpenRouter authentication, model selection, and routing. Support for all OpenRouter-compatible models with proper parameter mapping.

**Alignment**: [ARCH:IP1.1.4](ARCHITECTURE.md#ip114), [TASK:T056](TASKS.md#t056), [TEST:IT2.8](TESTS.md#it28)

### FR1.19: External Service Registry
System shall maintain a registry of known external MCP and A2A services. Users can select services from the registry, add authentication keys if necessary, apply group/user access rights, confirm history/context memory settings, verify endpoints work, and add/use services in expert channels they have permission to modify. Service registry shall include service metadata, health status, and usage statistics.

**Scope and behaviour:**
- Registry entries include service type (MCP/A2A), transport, base URL, health endpoint, and auth scheme.
- Services can be enabled/disabled per group and per channel.
- Registry supports ownership, access control, and usage statistics.

**Health and verification:**
- Health checks must be scheduled and on-demand.
- Failures are recorded with timestamps and last error summary.
- Verification must test authentication and a read-only capability.

**Security and audit:**
- Credentials stored in `private/` env files and never logged.
- All registry CRUD and attach/detach operations are audited.

**Error handling:**
- Invalid endpoint or auth produces clear 4xx with error code.
- Health failures do not block unrelated services.

**Acceptance criteria:**
- Registry CRUD, health checks, and channel attach/detach work end-to-end.
- Access control prevents unauthorised service usage.

**Alignment**: [ARCH:CC8.1](ARCHITECTURE.md#cc81), [TASK:T057](TASKS.md#t057), [TEST:ST1.32](TESTS.md#st132), [TEST:IT2.25](TESTS.md#it225), [TEST:AT1.95](TESTS.md#at195)

### FR1.20: Log History Management
System shall provide comprehensive log history search and download capabilities. Users/group admins/super admins can view all log history relevant to them based on access controls. System shall support searching logs by date range, user, channel, session, keyword, and other filters. Users can download log data in various formats (JSON, CSV, etc.). System shall provide access to all jobs/calls outputs that users have permission to view.

**Scope and behaviour:**
- Search by date range, user, group, channel, session, job ID, and keyword.
- Pagination with stable ordering and total counts.
- Download in JSON and CSV with deterministic field ordering.
- Job/call outputs are accessible only to authorised users.

**Security and audit:**
- Access is scoped to user/group permissions.
- Download events are audited with query parameters.
- Redaction rules must apply to exports.

**Performance:**
- Query responses must include timing metadata.
- Large exports must support streaming or async export jobs.

**Acceptance criteria:**
- Search results and downloads match filters and access rules.
- Exported data is complete, redacted, and reproducible.

**Alignment**: [ARCH:CC7.1](ARCHITECTURE.md#cc71), [TASK:T058](TASKS.md#t058), [TEST:ST1.33](TESTS.md#st133), [TEST:IT2.26](TESTS.md#it226), [TEST:AT1.96](TESTS.md#at196)

### FR1.21: Web UI Channel Management
System shall provide web interface capabilities for users to extend channel configurations and manage access as permitted by their roles. Users can create, edit, and delete channels through the web UI. Channel configuration includes LLM settings, prompts, tools, vector stores, and access controls. Changes are validated and require appropriate permissions.

**Status:** ✅ Implemented and under expansion  
**Implementation Notes:** Web UI channel operations are backed by API endpoints and validated by browser E2E and integration suites.

**Scope and behaviour:**
- UI supports create, edit, view, and delete channels with role-based access.
- UI surfaces LLM settings, prompts, tools, vector stores, and access rules.
- Validation errors are shown inline with actionable messages.

**Security and audit:**
- UI respects API permissions; no client-side bypass.
- All changes emit audit events with before/after deltas.

**Usability requirements:**
- Clear diff/preview before save.
- Required fields are marked and validated before submit.

**Acceptance criteria:**
- All channel CRUD operations are possible via Web UI without direct API use.
- Permissions prevent unauthorised edits or deletes.

**Alignment**: [ARCH:CC1.1.2](ARCHITECTURE.md#cc112), [TASK:T059](TASKS.md#t059), [TEST:ST1.28](TESTS.md#st128), [TEST:IT2.21](TESTS.md#it221), [TEST:AT1.91](TESTS.md#at191), [TEST:AT1.94](TESTS.md#at194)

### FR1.22: Web UI Testing Interface
System shall provide a web interface for users to run tests on all interfaces/experts/calls. Users can add content to test each expert configuration. Testing interface shall support testing with various input types (text, multimedia), viewing responses, and validating expert behavior. Test results shall be logged and available for review.

**Status:** ✅ Implemented and under expansion  
**Implementation Notes:** Web UI testing interface and API contract paths are validated by integration/application suites.

**Scope and behaviour:**
- UI lets users run ad-hoc tests against channels and tools.
- Supports text inputs now; multimedia inputs when enabled.
- Shows inputs, outputs, validations, and linked artefacts.

**Security and audit:**
- Only authorised users can run tests on permitted channels.
- All test runs are logged with inputs and outputs (redacted as configured).

**Acceptance criteria:**
- Users can run a test, view results, and download artefacts.
- Tests require configured services; failures are explicit.

**Alignment**: [ARCH:CC1.1.2](ARCHITECTURE.md#cc112), [TASK:T060](TASKS.md#t060), [TEST:ST1.29](TESTS.md#st129), [TEST:IT2.22](TESTS.md#it222), [TEST:AT1.92](TESTS.md#at192), [TEST:AT1.94](TESTS.md#at194)

### FR1.43: Web UI Full Functional Coverage and Operational Safety
System shall provide a complete Web UI surface that allows authorised users/admins to operate all major capabilities without direct API use, with strict RBAC and audit controls.

**Mandatory Web UI capabilities:**
- CRUD for core entities: users, groups, experts, channels, files, and supported knowledge entries.
- Audit/admin operations: jobs list/view actions, system status, queue status, and log visibility according to role.
- Full message management/review: channel chat send/receive, session selection, and readable history context in UI flows.
- Configuration testing: run test suites from UI and inspect structured test outputs.
- Channel/user management: create/manage channels and assign/use users/groups with permission enforcement.
- Prompt generation support from UI (`/prompts/generate`) with visible results.
- Multi-language operation support: UI workflows must allow multilingual prompts/messages and preserve UTF-8 content through upload/download flows.
- Config/env updates (admin-only): UI may expose configuration controls where implemented; all such actions must require admin rights and be audited.

**Quality and stability requirements:**
- No page crashes during core flows.
- No unhandled JS runtime errors during tested flows.
- No failed UI-triggered API requests for covered happy paths.
- Clear error surfacing for invalid input/authorisation/service failures.

**Acceptance criteria:**
- Browser-driven E2E suites (Selenium/Playwright) cover panel loads, critical CRUD/testing flows, and endpoint-path smoke checks.
- Coverage is traceable in `docs/TESTS.md` with executable test IDs and files.

**Alignment**: [ARCH:CC1.1.2](ARCHITECTURE.md#cc112), [ARCH:AI1.4](ARCHITECTURE.md#ai14), [TASK:T124](TASKS.md#t124), [TEST:IT2.17](TESTS.md#it217), [TEST:AT1.94](TESTS.md#at194)

### FR1.23: Channel Analytics and Statistics
System shall provide statistics and analytics for each expert channel including: usage metrics (number of calls, active sessions), success rates, cost metrics (token usage, API costs), performance metrics (average latency, error rates), and user engagement metrics. Statistics shall be available to channel owners, group admins, and super admins based on access controls.

**Scope and behaviour:**
- Metrics per channel: calls, active sessions, error rate, latency, token usage.
- Aggregations by time window (hour/day/week/month) and filters.
- Cost metrics based on model pricing configuration.

**Security and audit:**
- Access limited to channel owner, group admins, and super admins.
- Export actions are audited.

**Acceptance criteria:**
- Metrics match underlying job records and are reproducible.
- Access control prevents cross-channel leakage.

**Alignment**: [ARCH:MO1.4](ARCHITECTURE.md#mo14), [TASK:T061](TASKS.md#t061), [TEST:ST1.30](TESTS.md#st130), [TEST:IT2.23](TESTS.md#it223), [TEST:AT1.93](TESTS.md#at193)

### FR1.24: Developer API Access
System shall provide comprehensive API access for developers with proper authentication. All endpoints shall be accessible via API with appropriate authentication (API keys, OAuth, etc.). API documentation shall be complete with examples, schemas, and authentication requirements. Developer access shall support all CRUD operations on resources the developer has permission to access.

**Alignment**: [ARCH:AI1.1](ARCHITECTURE.md#ai11), [TASK:T062](TASKS.md#t062), [TEST:IT2.9](TESTS.md#it29)

### FR1.25: External Agentic Integration
System shall support external agentic flows calling experts via MCP or API interfaces with proper credentials. MCP interface shall provide tools for expert interaction. API interface shall support both synchronous and asynchronous calls. System shall handle authentication, rate limiting, and access control for external agentic flows.

**Scope and behaviour:**
- External agents can call via MCP tools or REST API.
- Both sync and async modes are supported with consistent payloads.
- Rate limits and quotas apply per API key and per group.

**Security and audit:**
- Auth required for all external calls (API key or JWT where applicable).
- All external calls are audited with caller metadata.

**Acceptance criteria:**
- MCP tool calls and API calls return consistent results.
- Access control and rate limits are enforced under load.

**Alignment**: [ARCH:AI1.2](ARCHITECTURE.md#ai12), [TASK:T063](TASKS.md#t063), [TEST:ST1.34](TESTS.md#st134), [TEST:IT2.27](TESTS.md#it227), [TEST:AT1.97](TESTS.md#at197)

### FR1.26: Queue Management with CRUD Operations
System shall manage all requests and jobs in a queue that supports CRUD (Create, Read, Update, Delete) actions from all authenticated users/interfaces. Queue shall support job creation, status checking, updating job metadata, and cancellation/deletion. Queue operations shall respect access controls and permissions. Queue shall provide visibility into job status, progress, and results.

**Scope and behaviour:**
- CRUD for jobs: create, list, get, update metadata, cancel, delete.
- Progress and status fields are consistent across API/MCP.
- Queue supports prioritisation and basic filtering.

**Security and audit:**
- Access enforced by ownership and role.
- All queue actions are audited with before/after metadata.

**Acceptance criteria:**
- Jobs transition through valid states only.
- Cancelled jobs stop processing within defined timeout.

**Alignment**: [ARCH:CC2.1.2](ARCHITECTURE.md#cc212), [TASK:T064](TASKS.md#t064), [TEST:ST1.35](TESTS.md#st135), [TEST:IT2.28](TESTS.md#it228), [TEST:AT1.98](TESTS.md#at198)

### FR1.27: Group Admin Role Management
System shall support group admin roles where group admins have administrative privileges for their assigned groups only. Group admins can manage users, channels, API keys, and configurations within their groups. System admins can create groups and assign group admins. Group admins have full control over their group's resources but cannot access other groups' resources.

**Scope and behaviour:**
- Group admins can create/update users, channels, and API keys within their group.
- Group admins cannot view or modify other groups' resources.
- System admins can assign and revoke group admin status.

**Security and audit:**
- All role changes are audited with actor and target.
- Permission checks enforced server-side only.

**Acceptance criteria:**
- Group admin actions succeed within their group and fail outside it.
- Audit trail is complete for role changes and admin actions.

**Alignment**: [ARCH:SE1.1](ARCHITECTURE.md#se11), [TASK:T114](TASKS.md#t114), [TEST:ST1.36](TESTS.md#st136), [TEST:IT2.29](TESTS.md#it229), [TEST:AT1.99](TESTS.md#at199)

### FR1.28: Prompt Test Case Generation
System shall generate example test cases when creating expert configurations. Test cases shall exercise the LLM, knowledge base, and tools. Test cases can be edited and used for validation. System shall use LLM to generate appropriate test scenarios based on expert description and configuration.

**Scope and behaviour:**
- Generate a minimum set of test cases per expert (happy path, edge case, tool use).
- Store generated cases with versioning and edit history.
- Allow manual edits and re-generation with provenance.

**Security and audit:**
- Only authorised users can generate or edit test cases.
- All generation and edits are audited.

**Acceptance criteria:**
- Generated cases include inputs, expected output shape, and validation hints.
- Cases are runnable via API and Web UI test interfaces.

**Alignment**: [ARCH:CC3.1.4](ARCHITECTURE.md#cc314), [TASK:T115](TASKS.md#t115), [TEST:ST1.37](TESTS.md#st137), [TEST:IT2.30](TESTS.md#it230), [TEST:AT1.100](TESTS.md#at1100)

### FR1.29: LLM Validation Testing
System shall provide capability to run short validation tests for LLM configurations before channel activation. Tests shall validate LLM connectivity, prompt rendering, and basic response generation. Test results shall indicate success/failure with details. Tests can be run on-demand during channel setup.

**Scope and behaviour:**
- Test suite includes connectivity, prompt rendering, and deterministic response check.
- Results stored with timestamps, configuration snapshot, and error details.
- Channel activation requires passing validation unless explicitly overridden by admin.

**Security and audit:**
- Validation runs are audited with actor and configuration reference.
- No secrets are logged in validation artefacts.

**Acceptance criteria:**
- Validation failures block activation by default.
- Results are available via API and Web UI.

**Alignment**: [ARCH:CC3.1.4](ARCHITECTURE.md#cc314), [TASK:T116](TASKS.md#t116), [TEST:ST1.38](TESTS.md#st138), [TEST:IT2.31](TESTS.md#it231), [TEST:AT1.101](TESTS.md#at1101)

### FR1.30: Response Quality Evaluation
System shall evaluate each LLM response for quality metrics including relevance, completeness, and accuracy. System shall support user feedback and automated quality checks. Quality scores shall be stored with job records and available in analytics. System shall provide quality confirmation indicators.

**Scope and behaviour:**
- Compute quality metrics per response (relevance, completeness, accuracy score).
- Collect user feedback and link to response/job IDs.
- Surface indicators in analytics and response metadata.

**Security and audit:**
- Feedback updates are audited.
- Scores are immutable once published for a job.

**Acceptance criteria:**
- Quality scores are stored and retrievable by authorised users.
- Analytics aggregates match underlying job records.

**Alignment**: [ARCH:MO1.4](ARCHITECTURE.md#mo14), [TASK:T117](TASKS.md#t117), [TEST:ST1.39](TESTS.md#st139), [TEST:IT2.32](TESTS.md#it232), [TEST:AT1.102](TESTS.md#at1102)

### FR1.31: Knowledge History CRUD with Permissions
System shall provide CRUD operations for knowledge history on user/group/session basis with permission-based access control. Users can view/manage their own knowledge, group admins can manage group knowledge, and session participants can manage session knowledge. Knowledge can be removed/deleted based on permissions. All operations respect access controls.

**Versioning / rollback / removal:**
- Any write/delete/removal creates a **new immutable version** of the knowledge base
- System shall support listing versions and rolling back the “current” version
- System shall support removing unwanted/bad information by filter (e.g. keyword, channel)
- REST endpoints (knowledge history):
  - `GET /knowledge/{knowledge_type}/{knowledge_id}` (current version entries)
  - `POST /knowledge` (append entry -> new version)
  - `GET /knowledge/{knowledge_type}/{knowledge_id}/versions`
  - `POST /knowledge/{knowledge_type}/{knowledge_id}/rollback`
  - `DELETE /knowledge/{knowledge_type}/{knowledge_id}?keyword=...&channel_id=...` (remove -> new version)

**Access rules:**
- User scope: owner can read/write; others forbidden.
- Group scope: group admins can read/write; members read-only.
- Session scope: participants can read/write while session active.

**Audit and retention:**
- All knowledge updates create auditable events with version IDs.
- Retention policies apply per scope and are configurable.

**Acceptance criteria:**
- CRUD operations enforce scope-based permissions.
- Version listing and rollback work with full audit trail.

**Alignment**: [ARCH:CC4.1](ARCHITECTURE.md#cc41), [TASK:T118](TASKS.md#t118), [TEST:ST1.40](TESTS.md#st140), [TEST:IT2.33](TESTS.md#it233), [TEST:AT1.103](TESTS.md#at1103)

### FR1.32: Job Queue CRUD Operations (Admin)
System shall provide comprehensive CRUD operations for job queue management by admins. Admins can view all jobs with full details (user, channel, session, settings, outputs, thinking), remove unwanted jobs, resubmit failed jobs, and stop running jobs. All operations shall be audited. Queue operations support filtering, searching, and bulk actions.

**Scope and behaviour:**
- Admins can view, filter, resubmit, cancel, and delete jobs.
- Bulk actions supported with dry-run previews.
- Job details include inputs, outputs, and metrics where permitted.

**Security and audit:**
- Admin actions are audited with before/after state.
- Sensitive fields are redacted per policy.

**Acceptance criteria:**
- Admin operations enforce role checks and are fully audited.
- Resubmitted jobs preserve original metadata with a new job ID.

**Alignment**: [ARCH:CC2.1.2](ARCHITECTURE.md#cc212), [TASK:T119](TASKS.md#t119), [TEST:ST1.41](TESTS.md#st141), [TEST:IT2.34](TESTS.md#it234), [TEST:AT1.104](TESTS.md#at1104)

### FR1.32A: Job Control WebUI (PS-76)
System shall provide a PS-76-compliant Job Control WebUI in the shared frontend application. The Jobs page shall use `@cloud-dog/ui` `DataTable`, standard status badges, bulk actions, summary metrics, and a job detail `EntityDialog`.

**Scope and behaviour:**
- Common PS-76 columns must appear in standard order: Job ID, Type, Status, Priority, Submitted By, Created, Started, Duration, Attempt, Outcome.
- Project-specific columns for expert-agent are `Session ID` and `User ID`, placed after the common columns.
- Summary metrics must show Total Jobs, Queue Depth, Active Jobs, and Failed (24h).
- Row actions must support Detail, Cancel, Retry, and Delete, with bulk Cancel/Retry/Delete/Export where permitted.

**Security and audit:**
- Viewing job data requires `read_jobs` or admin-equivalent access.
- Cancel and Retry require `write_jobs`.
- Delete requires admin.
- All mutating actions are audit-logged.

**Acceptance criteria:**
- The WebUI uses the shared `DataTable` and `EntityDialog`, not bespoke table widgets.
- Status badge colouring follows PS-76 mappings.
- Session and user identifiers are visible in the Jobs table and detail dialog.

**Alignment**: [REQ:FR1.32](REQUIREMENTS.md#fr132), [ARCH:CC2.1.2](ARCHITECTURE.md#cc212), [TASK:T119](TASKS.md#t119), [TEST:ST1.41](TESTS.md#st141), [TEST:AT1.104](TESTS.md#at1104)

### FR1.33: Channel REST Endpoint (Async/Sync)
System shall provide a REST endpoint for channel interactions that supports both synchronous and asynchronous modes. Endpoint shall accept API key authentication and return responses immediately (sync) or job ID for status checking (async). Both modes support same request format. Async mode supports webhook callbacks for completion notification.

**Scope and behaviour:**
- Single endpoint supports `mode=sync|async` with shared payload schema.
- Async mode returns `job_id` and status URL; sync returns response content.
- Webhook callbacks deliver signed payloads to configured URLs.

**Security and audit:**
- All calls require API key auth and enforce scope.
- Webhook signatures use configured secret; retries are logged.

**Error handling:**
- Invalid payload returns 400 with field-level errors.
- Webhook failures retry with backoff and have terminal failure status.

**Acceptance criteria:**
- Sync and async modes produce equivalent content.
- Webhook callbacks are delivered and verifiable when enabled.

**Alignment**: [ARCH:CC1.1.1](ARCHITECTURE.md#cc111), [TASK:T120](TASKS.md#t120), [TEST:ST1.27](TESTS.md#st127), [TEST:IT2.20](TESTS.md#it220), [TEST:AT1.90](TESTS.md#at190)

### FR1.34: File Store Management (Admin)
System shall provide admin interface and API for managing files in the local file store.

**Mandatory capabilities:**
- **Upload**:
  - Multipart upload (`POST /files/upload`) for UI-driven workflows.
  - Base64 upload (`POST /files/upload_base64`) for agent/tool workflows.
- **List + metadata** (`GET /files`, `GET /files/{id}`): include id, type, size, timestamps, processing status, and metadata.
- **Download** (`GET /files/{id}/download`) for authenticated users with appropriate permissions.
- **Delete** (`DELETE /files/{id}`) with audit trail.
- **Translate** (`POST /files/{id}/translate`) for UTF-8 text documents using the selected expert config (LLM provider/model must be config-driven).
- **Ingest to vector store** (`POST /files/{id}/ingest_to_vector_store`) for UTF-8 text documents; ingestion must target a configured vector store (no embedded secrets in persisted configs; runtime secrets sourced from env profiles per RULES.md).
- **Query evidence**: ingested content must be retrievable via vector search endpoints/tools when configured.

**Hard constraints (RULES.md):**
- No credentials embedded in persisted DB configs or committed docs/tests.
- If a backend is configured in the active `--env`, failures must be surfaced as failures (no silent skips for required services).
- All file operations must be authenticated and audited where applicable.

**Alignment**: [TASK:T121](TASKS.md#t121), [TEST:ST1.45](TESTS.md#st145), [TEST:ST1.46](TESTS.md#st146), [TEST:IT2.37](TESTS.md#it237), [TEST:AT1.114](TESTS.md#at1114), [TEST:AT1.116](TESTS.md#at1116), [TEST:AT1.94](TESTS.md#at194)

### FR1.42: Comprehensive Expert Test Suite
System shall provide extensive test suite framework for validating expert configurations. Tests shall validate LLM responses, tool calls, vector retrieval, knowledge sharing, history management, and multimedia processing. Test results shall be stored and reportable. Tests can be run against known/test expert examples to confirm functionality and capability.

**Alignment**: [ARCH:TS1.1](ARCHITECTURE.md#ts11), [TASK:T122](TASKS.md#t122), [TEST:PT1.20](TESTS.md#pt120)

---

## 5. Use Cases (UC)

### UC1.1: Start Conversation with Expert
As a user, I want to start a conversation with an expert assistant so that I can get intelligent, context-aware responses.

**Alignment**: [REQ:FR1.1](REQUIREMENTS.md#fr11), [ARCH:AI1.1](ARCHITECTURE.md#ai11), [TASK:T022](TASKS.md#t022), [TEST:AT1.9](TESTS.md#at19)

### UC1.2: Access Knowledge Base
As a user, I want to access knowledge base information during conversations so that responses are enhanced with relevant context.

**Alignment**: [REQ:FR1.3](REQUIREMENTS.md#fr13), [ARCH:CC4.1](ARCHITECTURE.md#cc41), [TASK:T014](TASKS.md#t014), [TEST:AT1.10](TESTS.md#at110)

### UC1.3: Manage Expert Configurations
As an administrator, I want to manage expert configurations including LLM settings, prompts, and access control so that different expertise domains are available to users.

**Alignment**: [REQ:FR1.1](REQUIREMENTS.md#fr11), [ARCH:CC3.1](ARCHITECTURE.md#cc31), [TASK:T007](TASKS.md#t007), [TEST:AT1.11](TESTS.md#at111)

### UC1.4: Manage User Preferences
As an administrator, I want to manage user preferences including language, timezone, and access permissions so that users have appropriate access to expert configurations.

**Alignment**: [REQ:FR1.5](REQUIREMENTS.md#fr15), [ARCH:CC5.1](ARCHITECTURE.md#cc51), [TASK:T005](TASKS.md#t005), [TEST:AT1.12](TESTS.md#at112)

### UC1.5: Monitor System Health
As an administrator, I want to monitor system health, metrics, and performance so that I can ensure optimal system operation.

**Alignment**: [REQ:FR1.9](REQUIREMENTS.md#fr19), [ARCH:MO1.1](ARCHITECTURE.md#mo11), [TASK:T040](TASKS.md#t040), [TEST:ST1.6](TESTS.md#st16)

### UC1.6: Agentic Flow with Channel-Based Expert
As part of an agentic flow, I want to call an expert system with an LLM and attached knowledge base to help answer a particular question. The expert system has a specific LLM with specific parameters, configured on a per-channel basis. I can set up and use new channels for different scenarios. The expert can have a history of knowledge defined on a user, channel, or session basis with definable limitations (e.g., only remember last 3 weeks). This history can be shared across different expert channels (by session key or user). The expert will have multiple defined knowledge bases stored in vector databases that can augment the search. The expert may call on a rerank model. The expert may have one or more tools and other agents it can call to resolve queries.

**Alignment**: [REQ:FR1.12](REQUIREMENTS.md#fr112), [REQ:FR1.2](REQUIREMENTS.md#fr12), [ARCH:CC3.1](ARCHITECTURE.md#cc31), [TASK:T050](TASKS.md#t050), [TEST:AT1.13](TESTS.md#at113)

### UC1.7: Multimedia Processing
As a user, I want to send and receive multimedia information including images, audio, and movies for processing and returning in expert conversations.

**Alignment**: [REQ:FR1.13](REQUIREMENTS.md#fr113), [ARCH:CC3.1.3](ARCHITECTURE.md#cc313), [TASK:T051](TASKS.md#t051), [TEST:AT1.105](TESTS.md#at1105)

### UC1.8: Comprehensive Session and Job Logging
As the system, I need to record each session with a full log, and for each LLM/Expert call save a full job/call record with all information including prompts, responses, metadata, and performance metrics.

**Alignment**: [REQ:FR1.14](REQUIREMENTS.md#fr114), [ARCH:CC7.1](ARCHITECTURE.md#cc71), [TASK:T052](TASKS.md#t052), [TEST:ST1.20](TESTS.md#st120)

### UC1.9: Auto-Generate Expert Prompts
As a user, I want to provide an expert description (title, details, context type, expected outcomes) and have the system generate an example prompt and settings that encapsulate the prompt, tool calls (from available set), to help define the expert configuration.

**Alignment**: [REQ:FR1.15](REQUIREMENTS.md#fr115), [ARCH:CC3.1.4](ARCHITECTURE.md#cc314), [TASK:T053](TASKS.md#t053), [TEST:AT1.107](TESTS.md#at1107)

### UC1.10: Tool and External Service Management
As a user, I want to add a tool definition to a channel. As a user, I want to add an external A2A/MCP service into the system, check it is working/responding, apply it to one or more channels to make it available, and then prompt/evaluate the channel prompt to see if it needs enhancing.

**Alignment**: [REQ:FR1.16](REQUIREMENTS.md#fr116), [ARCH:CC8.1](ARCHITECTURE.md#cc81), [TASK:T054](TASKS.md#t054), [TEST:AT1.110](TESTS.md#at1110)

### UC1.11: Group and User API Key Management
As a user, I am a member of a number of groups. As a defined group admin, I can manage the users of the group. You can define system users. Users and Groups can define API keys that provide read and/or write access to channels, logs, histories.

**Alignment**: [REQ:FR1.17](REQUIREMENTS.md#fr117), [ARCH:CC5.1.3](ARCHITECTURE.md#cc513), [TASK:T055](TASKS.md#t055), [TEST:AT1.17](TESTS.md#at117)

### UC1.12: OpenRouter Integration
As a user, I want to create Ollama and OpenAI-compatible channels/Experts using an OpenRouter.ai endpoint.

**Alignment**: [REQ:FR1.18](REQUIREMENTS.md#fr118), [ARCH:IP1.1.4](ARCHITECTURE.md#ip114), [TASK:T056](TASKS.md#t056), [TEST:IT2.8](TESTS.md#it28)

### UC1.13: External Service Registry
As a user, I want to pick an external MCP service or A2A service from a known list, add a key if necessary, apply group/user access rights, confirm any history/context memory, confirm the endpoint works, and then add/use the service in one or more of the expert channels that I am allowed to update/add this to (either as the owner/originator, or group admin member).

**Alignment**: [REQ:FR1.19](REQUIREMENTS.md#fr119), [ARCH:CC8.1](ARCHITECTURE.md#cc81), [TASK:T057](TASKS.md#t057), [TEST:AT1.95](TESTS.md#at195)

### UC1.14: Log History Search and Download
As a user/group admin/super admin, I want to be able to see all the log history that is relevant to me, search it, and download it. I want to be able to see all the jobs/calls outputs that I have access to.

**Alignment**: [REQ:FR1.20](REQUIREMENTS.md#fr120), [ARCH:CC7.1](ARCHITECTURE.md#cc71), [TASK:T058](TASKS.md#t058), [TEST:AT1.96](TESTS.md#at196)

### UC1.15: Web UI Channel Configuration
From the web interface, as a user, I want to be able to extend the configuration of channels and access as I am allowed to do.

**Alignment**: [REQ:FR1.21](REQUIREMENTS.md#fr121), [ARCH:CC1.1.2](ARCHITECTURE.md#cc112), [TASK:T059](TASKS.md#t059), [TEST:AT1.91](TESTS.md#at191)

### UC1.16: Web UI Testing Interface
From the web interface, as a user, I want to be able to run tests on all the interfaces/experts/calls including adding content to try each expert.

**Alignment**: [REQ:FR1.22](REQUIREMENTS.md#fr122), [ARCH:CC1.1.2](ARCHITECTURE.md#cc112), [TASK:T060](TASKS.md#t060), [TEST:AT1.92](TESTS.md#at192)

### UC1.17: Channel Analytics and Statistics
As a group/channel owner, I want to be able to see statistics on use, success, cost (tokens) of each expert channel.

**Alignment**: [REQ:FR1.23](REQUIREMENTS.md#fr123), [ARCH:MO1.4](ARCHITECTURE.md#mo14), [TASK:T061](TASKS.md#t061), [TEST:AT1.93](TESTS.md#at193)

### UC1.18: Developer API Access
As a developer, I want to have access to all endpoints with the right authentication via the API.

**Alignment**: [REQ:FR1.24](REQUIREMENTS.md#fr124), [ARCH:AI1.1](ARCHITECTURE.md#ai11), [TASK:T062](TASKS.md#t062), [TEST:IT2.9](TESTS.md#it29)

### UC1.19: External Agentic Flow Integration
As an external agentic flow, I want to be able to call an expert with the right credentials via MCP or API interface.

**Alignment**: [REQ:FR1.25](REQUIREMENTS.md#fr125), [ARCH:AI1.2](ARCHITECTURE.md#ai12), [TASK:T063](TASKS.md#t063), [TEST:AT1.97](TESTS.md#at197)

### UC1.20: Queue Management with CRUD Operations
As the system, I need to manage all the requests and jobs in a queue that can support CRUD actions from all authenticated users/interfaces.

**Alignment**: [REQ:FR1.26](REQUIREMENTS.md#fr126), [ARCH:CC2.1.2](ARCHITECTURE.md#cc212), [TASK:T064](TASKS.md#t064), [TEST:ST1.35](TESTS.md#st135), [TEST:AT1.98](TESTS.md#at198)

### UC1.21: Group Admin Management
As a system admin, I want to create groups and assign group admin users so that group admins can manage their own groups independently.

**Alignment**: [REQ:FR1.27](REQUIREMENTS.md#fr127), [REQ:FR1.5](REQUIREMENTS.md#fr15), [ARCH:SE1.1](ARCHITECTURE.md#se11), [TASK:T114](TASKS.md#t114), [TEST:AT1.99](TESTS.md#at199)

### UC1.22: Channel Setup with Tools and History
As a group admin, I want to create a channel/expert with scope, tools, and history preferences so that the expert can respond intelligently with appropriate context.

**Alignment**: [REQ:FR1.12](REQUIREMENTS.md#fr112), [REQ:FR1.15](REQUIREMENTS.md#fr115), [REQ:FR1.16](REQUIREMENTS.md#fr116), [ARCH:CC3.1](ARCHITECTURE.md#cc31), [TASK:T050](TASKS.md#t050), [TASK:T053](TASKS.md#t053), [TEST:AT1.13](TESTS.md#at113)

### UC1.23: LLM Validation Testing
As a group admin, I want to run a short test to validate the LLM before deploying the channel so that I can ensure the expert configuration works correctly.

**Alignment**: [REQ:FR1.29](REQUIREMENTS.md#fr129), [REQ:FR1.15](REQUIREMENTS.md#fr115), [ARCH:CC3.1.4](ARCHITECTURE.md#cc314), [TASK:T116](TASKS.md#t116), [TEST:AT1.101](TESTS.md#at1101)

### UC1.24: User API Key Management
As a group admin or user, I want to create and manage API keys for users with specific access scopes so that users can access channels/groups via API with appropriate permissions.

**Alignment**: [REQ:FR1.17](REQUIREMENTS.md#fr117), [ARCH:CC5.1.3](ARCHITECTURE.md#cc513), [TASK:T055](TASKS.md#t055), [TEST:AT1.94](TESTS.md#at194)

### UC1.25: Multi-Group/Channel User Access
As a user, I want to be a member of multiple groups with access to multiple channels so that I can interact with different experts for different purposes.

**Alignment**: [REQ:FR1.12](REQUIREMENTS.md#fr112), [REQ:FR1.5](REQUIREMENTS.md#fr15), [ARCH:CC3.1.3](ARCHITECTURE.md#cc313), [TASK:T050](TASKS.md#t050), [TEST:AT1.13](TESTS.md#at113)

### UC1.26: Knowledge History Management with Permissions
As a user or admin, I want to manage knowledge history on user/group/session basis with appropriate permissions so that I can control what knowledge is retained and accessible.

**Alignment**: [REQ:FR1.31](REQUIREMENTS.md#fr131), [REQ:FR1.12](REQUIREMENTS.md#fr112), [ARCH:CC4.1](ARCHITECTURE.md#cc41), [TASK:T118](TASKS.md#t118), [TEST:AT1.103](TESTS.md#at1103)

### UC1.27: Job Queue Management (Admin)
As an admin, I want to view, remove, resubmit, and stop jobs in the queue so that I can manage system workload and handle problematic requests.

**Alignment**: [REQ:FR1.32](REQUIREMENTS.md#fr132), [REQ:FR1.26](REQUIREMENTS.md#fr126), [ARCH:CC2.1.2](ARCHITECTURE.md#cc212), [TASK:T119](TASKS.md#t119), [TEST:AT1.104](TESTS.md#at1104)

### UC1.28: Response Quality Evaluation
As a system, I want to evaluate responses to each job for quality/confirmation so that I can provide feedback on response quality and improve over time.

**Alignment**: [REQ:FR1.30](REQUIREMENTS.md#fr130), [REQ:FR1.23](REQUIREMENTS.md#fr123), [ARCH:MO1.4](ARCHITECTURE.md#mo14), [TASK:T117](TASKS.md#t117), [TEST:AT1.102](TESTS.md#at1102)

### UC1.29: Channel REST Endpoint (Async/Sync)
As a developer, I want to call a channel via REST API with API key in both async and sync modes so that I can integrate expert capabilities into my applications.

**Alignment**: [REQ:FR1.33](REQUIREMENTS.md#fr133), [REQ:FR1.24](REQUIREMENTS.md#fr124), [ARCH:CC1.1.1](ARCHITECTURE.md#cc111), [TASK:T120](TASKS.md#t120), [TEST:IT2.20](TESTS.md#it220)

### UC1.30: File Store Management (Admin)
As an admin, I want to audit, view, upload, download, delete, translate, and ingest files so that I can manage storage, ensure compliance, and enable document-driven expert workflows (RAG).

**Acceptance criteria:**
- Upload supports both multipart and base64 modes.
- Download returns the original bytes for stored files.
- Delete removes the file record and the stored file from disk (where applicable) with an auditable event.
- Translate produces a new stored file record and preserves stable tokens/technical terms.
- Ingest stores document content into the configured vector store and the content is queryable (API and MCP tooling).

**Alignment**: [REQ:FR1.34](REQUIREMENTS.md#fr134), [REQ:FR1.13](REQUIREMENTS.md#fr113), [TASK:T121](TASKS.md#t121), [TEST:ST1.45](TESTS.md#st145), [TEST:ST1.46](TESTS.md#st146), [TEST:IT2.37](TESTS.md#it237), [TEST:AT1.114](TESTS.md#at1114), [TEST:AT1.116](TESTS.md#at1116), [TEST:AT1.94](TESTS.md#at194)

### UC1.31: Comprehensive Expert Test Suite
As a system developer, I want to have extensive tests against known/test experts/examples so that I can confirm functionality and capability of each expert channel.

**Alignment**: [REQ:FR1.42](REQUIREMENTS.md#fr142), [REQ:NF1.6](REQUIREMENTS.md#nf16), [ARCH:TS1.1](ARCHITECTURE.md#ts11), [TASK:T122](TASKS.md#t122), [TEST:PT1.20](TESTS.md#pt120)

### UC1.32: Complete API Coverage
As a developer, I want to perform all administrative and user actions via API so that I can automate and integrate expert capabilities.

**Alignment**: [REQ:FR1.24](REQUIREMENTS.md#fr124), [ARCH:AI1.1](ARCHITECTURE.md#ai11), [TASK:T123](TASKS.md#t123), [TEST:IT2.15](TESTS.md#it215)

### UC1.33: Complete Web UI Coverage
As a user or admin, I want to perform all actions via Web UI so that I can manage the system without using API directly.

**Alignment**: [REQ:FR1.21](REQUIREMENTS.md#fr121), [REQ:FR1.22](REQUIREMENTS.md#fr122), [ARCH:CC1.1.2](ARCHITECTURE.md#cc112), [TASK:T124](TASKS.md#t124), [TEST:IT2.16](TESTS.md#it216)

---

## 6. Cyber Security (CS)

### CS1.1: Authentication
System shall provide local auth (bcrypt/argon2) and API-key/JWT based API authentication. Local auth must enforce configured password policy and support account hard-disable, token refresh, and password change/reset flows. External authentication providers (Google, LinkedIn, Keycloak) with session mapping are supported but are implemented and tested separately.

**Local auth specifics (local-only focus):**
- Password policy enforced via config (`auth.password_min_length`, `auth.password_require_complexity`)
- User-initiated password change requires current password (API)
- Admin password reset supported (API)
- Token refresh supported (API) and respects revocation
- Account lockout supported (config-driven, local node) after repeated failed login attempts
- Disabled accounts cannot authenticate and cannot use previously issued Bearer/API key credentials

**Alignment**: [ARCH:SE1.1](ARCHITECTURE.md#se11), [TASK:T006](TASKS.md#t006), [TEST:ST1.7](TESTS.md#st17)

### CS1.2: Secret Management
System shall provide secret management; TLS in production. Secrets storage; masked logs; HTTPS in prod.

**Alignment**: [ARCH:SE1.2](ARCHITECTURE.md#se12), [TASK:T043](TASKS.md#t043), [TEST:ST1.8](TESTS.md#st18)

### CS1.3: Audit Events
System shall provide audit events for all admin actions. Per-session auditable log containing all significant events: session creation, message exchanges, LLM interactions, vector store operations, state transitions, and errors. Each auditable log entry must be signed with a cryptographic certificate generated from a provided or generated key, ensuring authenticity and non-repudiation.

**Alignment**: [ARCH:SE1.3](ARCHITECTURE.md#se13), [TASK:T041](TASKS.md#t041), [TEST:ST1.9](TESTS.md#st19)

### CS1.4: Data Protection
System shall provide PII minimisation; GDPR-friendly exports; configurable retention; redact or hash sensitive content at rest. Vector store access controls; session-based data isolation. All logs/history access separated by users/groups - users only see their stuff or stuff they are allowed to see.

**Alignment**: [ARCH:SE1.4](ARCHITECTURE.md#se14), [TASK:T026](TASKS.md#t026), [TEST:ST1.10](TESTS.md#st110)

### CS1.5: Identity Provider Authorization
System shall support two authorization modes when using external identity providers (Keycloak): IDP Authorization Mode (use roles from identity provider) and Local Authorization Mode (use local authorization with remote authentication). Role mapping from IDP roles to system permissions. Role retrieval from tokens/user info.

**Alignment**: [ARCH:SE1.5](ARCHITECTURE.md#se15), [TASK:T006](TASKS.md#t006), [TEST:ST1.11](TESTS.md#st111)

---

## 7. Non-Functional Requirements (NF)

### NF1.1: Performance
System shall provide response time < 200ms p95 for simple queries; LLM generation dependent. Submit-to-queue < 50ms p95; adapter latency surfaced in metrics.

**Alignment**: [ARCH:SP1.1](ARCHITECTURE.md#sp11), [TASK:T044](TASKS.md#t044), [TEST:ST1.12](TESTS.md#st112)

### NF1.2: Availability
System shall provide 99.9% uptime with health checks and failover mechanisms. Health checks, degraded modes, default expert configuration required.

**Alignment**: [ARCH:RR1.1](ARCHITECTURE.md#rr11), [TASK:T045](TASKS.md#t045), [TEST:ST1.13](TESTS.md#st113)

### NF1.3: Scalability
System shall support horizontal scaling of all components; support for 1000+ concurrent sessions. Horizontal workers; stateless API nodes; work-queue backed.

**Alignment**: [ARCH:SP1.2](ARCHITECTURE.md#sp12), [TASK:T046](TASKS.md#t046), [TEST:ST1.14](TESTS.md#st114)

### NF1.4: Compliance
System shall provide GDPR, CCPA compliance with data minimization and right to deletion. Configurable retention; PII minimisation; GDPR-friendly exports.

**Alignment**: [ARCH:SE1.4](ARCHITECTURE.md#se14), [TASK:T026](TASKS.md#t026), [TEST:ST1.15](TESTS.md#st115)

### NF1.5: Portability
System shall be containerized deployment with Docker; Kubernetes support. Config hierarchy: default → file → env; env prefix `CLOUD_DOG__EXPERT__`.

**Alignment**: [ARCH:DA1.1](ARCHITECTURE.md#da11), [TASK:T047](TASKS.md#t047), [TEST:ST1.16](TESTS.md#st116)

### NF1.6: Testability
System shall provide unit, integration, and end-to-end test coverage > 80%. Unit/integration/E2E suites; provider simulators; fixtures.

**Alignment**: [ARCH:TS1.1](ARCHITECTURE.md#ts11), [TASK:T048](TASKS.md#t048), [TEST:UT1.1](TESTS.md#ut11)

### NF1.7: Auditability
System shall maintain a per-session auditable log containing all significant events: session creation, message exchanges, LLM interactions, vector store operations, state transitions, and errors. Each auditable log entry must be signed with a cryptographic certificate generated from a provided or generated key, ensuring authenticity and non-repudiation. All entries include a precise datetime stamp, referencing the origin session, sender context, and associated records. Allow export or verification of the signed audit trail for compliance and dispute resolution.

**Alignment**: [ARCH:SE1.3](ARCHITECTURE.md#se13), [TASK:T041](TASKS.md#t041), [TEST:ST1.17](TESTS.md#st117)

### NF1.8: Data Retention & Privacy
System shall provide configurable retention windows for sessions, messages, history, and logs. Redact or hash sensitive content at rest where possible; store links for large payloads. Data lifecycle management and deletion based on settings, to remove content inline with DPA.

**Alignment**: [ARCH:DM1.1](ARCHITECTURE.md#dm11), [TASK:T026](TASKS.md#t026), [TEST:ST1.18](TESTS.md#st118)

---

## 8. Coverage Confidence & Quality Gates (CQ)

### CQ1.1: Current Validation Baseline (as of February 9, 2026)
- Application test execution baseline (latest full pass campaign): `618 passed`, `0 failed`, `2 skipped` across executable AT files.
- Skips are currently treated as expected backend-unavailable scenarios only when explicitly marked and justified in tests.
- Multi-backend vector coverage is validated in AT and ST runs for Chroma (local/remote), Qdrant, Weaviate, OpenSearch, and PGVector, with environment-specific availability handling.
- OpenRouter integration is validated with OpenRouter model identifiers and explicit handling of empty `content` responses where providers return `reasoning`.

**Alignment**: [ARCH:TS1.1](ARCHITECTURE.md#ts11), [TASK:T014](TASKS.md#t014), [TASK:T125](TASKS.md#t125), [TEST:AT1.10](TESTS.md#at110), [TEST:AT1.11](TESTS.md#at111), [TEST:AT1.17](TESTS.md#at117)

### CQ1.2: Identified Coverage Gaps
- System tests for MCP/A2A/Web currently include structural checks, but not enough protocol-depth or behavioural-resilience validation.
- Web UI confidence is low for full user workflows because browser-driven E2E coverage is still missing.
- UC-level traceability is incomplete for "complete API coverage" and "complete Web UI coverage" claims (UC1.32, UC1.33) versus executable evidence.
- Cross-interface parity validation (same scenario over REST, MCP, A2A, and Web UI) is not yet enforced as a release gate.

**Alignment**: [ARCH:AI1.2](ARCHITECTURE.md#ai12), [ARCH:AI1.3](ARCHITECTURE.md#ai13), [ARCH:AI1.4](ARCHITECTURE.md#ai14), [TASK:T126](TASKS.md#t126), [TASK:T127](TASKS.md#t127), [TASK:T128](TASKS.md#t128)

### CQ1.3: Mandatory Quality Gates for "High Confidence"
- Gate 1: Zero failing tests in scoped suites (UT/IT/ST/AT), with all skips reviewed and explicitly justified.
- Gate 2: Real protocol tests for MCP and A2A must include reconnect, timeout, backpressure, authz, and error-contract assertions.
- Gate 3: Web UI must have browser E2E coverage for critical user/admin flows, not only route/static checks.
- Gate 4: UC-to-test traceability must be explicit in docs and executable test suites for UC1.32 and UC1.33.
- Gate 5: Release candidate requires backend matrix verification across configured vector stores and active LLM provider profile.

**Alignment**: [ARCH:TS1.2](ARCHITECTURE.md#ts12), [TASK:T129](TASKS.md#t129), [TASK:T130](TASKS.md#t130), [TASK:T131](TASKS.md#t131), [TASK:T132](TASKS.md#t132)

---

## Technical Architecture

### Database Support
- SQLite3 for development/testing environments
- MySQL/MariaDB and PostgreSQL for production deployments
- Migration scripts for schema evolution

### Queue Management
- Redis/Valkey for high-performance queue operations
- SQL transactional tables as fallback mechanism
- Message durability and guaranteed delivery

### Configuration Management
- Hierarchical configuration: OS Environment → .env file → config.yaml → defaults.yaml
- CLOUD_DOG__EXPERT__ prefix for environment variables
- Runtime configuration reloading without service restart

### Vector Database Options
- Chroma: Default for development and testing
- Weaviate: Production-grade vector search with hybrid capabilities
- Qdrant: High-performance vector similarity search
- OpenSearch/Elastic: Full-text + vector search capabilities
- PGVector: PostgreSQL extension for vector storage and similarity search
- Indexing must provide all options on format and metadata setup/fields to add, but generally everything

### LLM Provider Support
- Ollama: Default for development/testing (qwen3:14b)
- OpenAI/OpenAI-compatible providers: Production deployments
- Copy configuration over for dev/test using ollama/qwen3
- System will support Ollama, OpenAI/OpenAI compatible out-of-the-box

### Identity Providers
- Local database: Default for development/testing
- Google: External authentication provider
- LinkedIn: External authentication provider
- Keycloak: SAML/OpenID identity provider
- Dev/Test identity provider will be local
- Future tests will be Google & LinkedIn and Keycloak

---

## Storage Architecture

**Section Identifier:** ST (Storage Architecture)

### ST1.1: Database Storage

**Primary Database** (SQLite3/MySQL/PostgreSQL):
- **Sessions**: Session metadata, status, context window state, retention settings
- **Messages**: Conversation history with role, content, timestamps, token counts
- **Users**: User accounts, preferences, authentication credentials (hashed)
- **Groups**: Group definitions, membership, access control mappings
- **Expert Configurations**: LLM settings, prompts, parameters, access control
- **Vector Store Mappings**: Session-to-vector-store associations
- **Audit Events**: Signed audit trail entries with cryptographic signatures

**File Locations:**
- Development: `database/expert.db` (SQLite3)
- Production: MySQL/PostgreSQL connection string via `CLOUD_DOG__EXPERT__DB__URI`

**Backup Strategy:**
- Automatic backups on schema migrations
- Configurable retention for audit logs
- Point-in-time recovery support (PostgreSQL)

**Alignment**: [REQ:NF1.8](REQUIREMENTS.md#nf18), [ARCH:CC6.1.1](ARCHITECTURE.md#cc611), [TASK:T002](TASKS.md#t002)

---

### ST1.2: Vector Store Storage

**Vector Store Locations:**
- **Chroma**: Local filesystem (`storage/chroma/`) or remote server
- **Weaviate**: Remote Weaviate cluster or local instance
- **Qdrant**: Remote Qdrant cluster or local instance
- **OpenSearch/Elastic**: Remote cluster endpoints
- **PGVector**: PostgreSQL database with vector extension

**Collection Strategy:**
- Each group has isolated collections
- Collection naming: `{group_id}_{vector_store_name}`
- No cross-talk between groups/databases on same host
- Collection-level access control

**Data Stored:**
- Embeddings: Vector representations of knowledge entries
- Metadata: Source, timestamp, keywords, access control
- Text chunks: Original content for retrieval
- Indexes: Provider-specific indexes for fast search

**Lifecycle Management:**
- Configurable TTL for automatic purging
- Compression/consolidation after time periods
- Removal based on keywords, times, channels

**Alignment**: [REQ:FR1.3](REQUIREMENTS.md#fr13), [ARCH:CC4.1.1](ARCHITECTURE.md#cc411), [TASK:T014](TASKS.md#t014), [TASK:T019](TASKS.md#t019)

---

### ST1.3: Cache Storage

**Cache Directory** (`cache/`):
- **Context Cache**: Cached expert configuration contexts
- **Prompt Cache**: Cached prompt templates and variations
- **Metadata Cache**: Cached vector store metadata
- **Session Cache**: In-memory session state (optional)

**Cache Management:**
- TTL-based invalidation
- Size limits to prevent disk exhaustion
- Automatic cleanup of expired entries
- Version-controlled cache keys

**Alignment**: [REQ:NF1.5](REQUIREMENTS.md#nf15), [ARCH:CM1.1](ARCHITECTURE.md#cm11), [TASK:T003](TASKS.md#t003)

---

### ST1.4: Log Storage

**Log Directory** (`logs/`):
- **API Server Logs**: `logs/api_server.log`
- **MCP Server Logs**: `logs/mcp_server.log`
- **Web UI Logs**: `logs/web_server.log`
- **A2A Server Logs**: `logs/a2a_server.log`

**Log Management:**
- Structured logging (JSON format)
- Log rotation (size and time-based)
- PII redaction in logs
- Configurable retention periods
- Compression of old logs

**Alignment**: [REQ:FR1.9](REQUIREMENTS.md#fr19), [ARCH:MO1.1](ARCHITECTURE.md#mo11), [TASK:T040](TASKS.md#t040)

---

### ST1.5: Temporary Storage

**Working Directory** (`working/`):
- Temporary working files during development
- Test results and reports
- Can be deleted at any time (transient)
- Excluded from version control

**Storage Directory** (`storage/`):
- Local development/project storage
- Server runtime data
- Excluded from version control

**Temporary Directory** (`tmp/`):
- Project run/delivery temporary files
- Excluded from version control

**Alignment**: [RULES.md](../RULES.md), [ARCH:DO1.1](ARCHITECTURE.md#do11)

---

### ST1.6: Query Response Storage

**Query Responses Directory** (`query_responses/`):
- Individual session response files (optional)
- JSON format with full metadata
- Configurable via `CLOUD_DOG__EXPERT__QUERY__SAVE_RESPONSES`
- Format: `{session_id}_{timestamp}.json`

**Response File Contents:**
- Session metadata
- Message history
- LLM thinking/reasoning
- Vector retrieval context
- Token counts and timing
- Request metadata

**Alignment**: [REQ:FR1.2](REQUIREMENTS.md#fr12), [ARCH:CC2.1.1](ARCHITECTURE.md#cc211), [TASK:T022](TASKS.md#t022)

---

## Future Capabilities (Planned)

- Multimodal support (images, documents, files) - v1.1
- Tool integration framework for A2A and other MCP tools
- Advanced knowledge graph capabilities
- Fine-tuning support for domain-specific expertise
- Multi-tenant isolation for enterprise deployments
- Advanced analytics and insights from conversation patterns

---

## Expanded Coverage Status (2026-02-10)

Verified by executable runs under `--env private/env-test` in this checkpoint:
- `FR1.7` callback + sync/async readiness: `ST1.26`, `ST1.27`, `IT2.20`
- `FR1.17` API key/auth cross-interface readiness: `IT2.24`, `ST1.31`
- `FR1.21`, `FR1.22`, `FR1.23` Web UI + testing + analytics readiness: `IT2.17`, `IT2.21`, `IT2.22`, `IT2.23`, `ST1.28`, `ST1.29`, `ST1.30`
- `FR1.3`, `FR1.14`, `FR1.26` integration readiness: `IT2.6`, `IT2.7`, `IT2.8`, `IT2.4`, `IT2.5`
- `FR1.28`, `FR1.29`, `FR1.31` application readiness evidence: `AT1.44`, `AT1.45`, `AT1.46`, `AT1.40`, `AT1.41`

Not yet at 100% expanded-compliance coverage:
- Dedicated executable coverage remains pending for `FR1.19`, `FR1.20`, `FR1.25`, `FR1.27`, `FR1.30`, `FR1.32`, and `NF1.5` expanded ID sets (`IT2.25+`, `ST1.32+`, `AT1.95+`) as tracked in `docs/TESTS.md`.

---

## Web UI Operational Data Management Requirements (2026-02-12)

### FR1.35: Knowledge Visibility and Operations in Web UI
- The Web UI SHALL display persisted knowledge entries for accessible scopes (`user`, `group`, `session`).
- The Web UI SHALL support:
  - text search
  - sort by date and text
  - paginated browsing (page size + next/previous)
  - per-entry deletion
  - scope-level history/version/rollback actions
- The Web UI SHALL expose semantic knowledge query controls that call configured vector stores.
- Vector query flow SHALL work with any configured backend (`chroma`, `qdrant`, `weaviate`, `opensearch`, `pgvector`) through common `vector-stores` APIs.

### FR1.36: File Lifecycle and Preview in Web UI
- The Web UI SHALL support upload, preview, download, and delete for files.
- The Web UI SHALL provide multi-select deletion with explicit confirmation.
- For text-like files, the Web UI SHALL provide inline preview.
- Chat/data workflows SHALL support file-based exchange via:
  - file reference IDs (uploaded file IDs),
  - base64 upload endpoint for programmatic ingestion.

### FR1.37: Query/Response Traceability by Channel and Expert
- Users/admins SHALL be able to inspect channel conversation history with message-level detail.
- Users/admins SHALL be able to inspect expert-associated job traces (prompt/response/status and detailed job payload).
- The UI SHALL allow drill-down to detailed job records for each processing step.

### FR1.38: Test and Evidence Visibility
- The platform SHALL include executable tests proving:
  - knowledge CRUD visibility and permissions,
  - Web UI operational controls for files/knowledge/session history,
  - end-to-end seeded demo scenarios with uploaded documents and conversation flows.
- Test evidence SHALL be traceable in `docs/TESTS.md` and `CONTEXT-SUMMARY.md`.

### FR1.39: Conversational Memory Scope and Reuse
- The system SHALL support memory persistence at `session`, `user`, and `group` scopes.
- Facts provided in chat or ingested from files SHALL be persistable to an explicit scope selected by the operator.
- Session-scoped knowledge SHALL be reusable during the active session.
- User-scoped knowledge SHALL be reusable across sessions for that same user.
- Group-scoped knowledge SHALL be reusable by authorized group members across sessions.
- The system SHALL support controlled removal/pruning/rollback of persisted knowledge without breaking version history/audit integrity.

### FR1.40: File-to-Knowledge Conversational Lifecycle
- The Web UI SHALL support upload -> ingest-to-knowledge -> query/reuse flow without requiring direct API key entry in browser UI.
- Files panel SHALL provide per-file and multi-file ingest controls with explicit target scope (`user|group|session`) and scope identifier.
- Knowledge UI SHALL show source linkage for file-ingested knowledge (source file id and filename metadata) to support traceability.
- Conversational workflows SHALL support output as text response and downloadable file; downloaded files SHALL be re-uploadable and ingestible.

### FR1.41: CRUD+ Endpoint Completeness and Response Standards
- The API SHALL explicitly support session resume semantics (FR-P001), session termination (FR-P002), paginated/filterable session listing (FR-P003), and session detail retrieval (FR-P004).
- The API SHALL support admin session deletion with cascade and audit trace (FR-P005).
- The API SHALL explicitly support expert GET/list/delete semantics including filtering and cascade-protection checks (FR-P006, FR-P007, FR-P008).
- The API SHALL explicitly support user view/list/delete semantics with field-level access and GDPR-safe cascade behavior (FR-P009, FR-P010, FR-P011).
- The API SHALL explicitly support group detail/list/update/delete semantics with cascade-safe behavior (FR-P012, FR-P013, FR-P014, FR-P015).
- The API SHALL explicitly support vector-store list/update/delete CRUD+ semantics including cascade checks (FR-P016, FR-P017, FR-P018).
- The API SHALL explicitly support API key delete (hard-delete) in addition to revocation/expiry flows (FR-P019).
- The API SHALL explicitly support channel tool list/remove operations (FR-P020, FR-P021).
- The API SHALL explicitly support channel service detach operations (FR-P022).
- Audit log query operations SHALL provide explicit server-side filtering parameters and deterministic query behavior (FR-P023).
- Web UI requirements SHALL explicitly define dashboard layout/content, expert-management workflows, and audit-log viewer behavior (FR-P024, FR-P025, FR-P026).
- Server control operations SHALL explicitly define start/stop/restart/status and force-stop semantics (FR-P027, FR-P028).
- All CRUD list endpoints SHALL support deterministic pagination (`skip`, `limit`) and optional filtering parameters per resource.
- All CRUD read/write endpoints SHALL return normalized error payloads with HTTP status code, `detail`, and stable validation error semantics.

### Coverage Mapping (current)
- `FR1.35`:
  - `tests/system/ST1.40_KnowledgeHistoryCRUD/test_knowledge_history_crud_readiness.py`
  - `tests/integration/IT2.33_KnowledgeHistoryCRUD/test_knowledge_history_crud_integration.py`
  - `tests/application/AT1.94_WebUIBrowserE2E/test_web_ui_browser_e2e.py`
- `FR1.36`:
  - `tests/system/ST1.45_FileStoreUploadDownload/test_file_store_upload_download.py`
  - `tests/application/AT1.94_WebUIBrowserE2E/test_web_ui_browser_e2e.py`
  - `tests/application/AT1.114_FileStoreManagement/test_file_store_management.py`
- `FR1.37`:
  - `tests/integration/IT2.17_WebUICompleteCoverage/test_web_ui_complete_coverage.py`
  - `tests/application/AT1.94_WebUIBrowserE2E/test_web_ui_browser_e2e.py`
- `FR1.38`:
  - `tests/application/AT1.117_DemoEnvironmentUseCases/test_demo_environment_usecases.py`
  - `docs/TESTS.md`
  - `CONTEXT-SUMMARY.md`
- `FR1.39`:
  - `tests/application/AT1.117_DemoEnvironmentUseCases/test_demo_environment_usecases.py`
  - `tests/system/ST1.40_KnowledgeHistoryCRUD/test_knowledge_history_crud_readiness.py`
  - `tests/integration/IT2.33_KnowledgeHistoryCRUD/test_knowledge_history_crud_integration.py`
- `FR1.40`:
  - `tests/application/AT1.94_WebUIBrowserE2E/test_web_ui_browser_e2e.py`
  - `tests/application/AT1.114_FileStoreManagement/test_file_store_management.py`
  - `tests/application/AT1.117_DemoEnvironmentUseCases/test_demo_environment_usecases.py`

---

## Open Questions

- Preferred LLM providers and deployment models for production
- Vector database selection criteria for different use cases
- External identity provider integration priorities
- Knowledge base ingestion pipeline requirements
- Advanced prompt engineering and safety mechanisms

---

## Appendix A: Version History

### Version 0.2 (2025-01-XX)

**Documentation Enhancements:**
- ✅ Restructured REQUIREMENTS.md with SV/BO/BR/FR/UC/CS/NF prefixes and numbered entries
- ✅ Added alignment links to Requirements (Requirements → Architecture, Tasks, Tests)
- ✅ Restructured ARCHITECTURE.md with section identifiers (OV, SA, CC, DM, SW, CP, DF, IP, SE, SP, RR, MO, CM, DA, AI, TS, MU, DO, RD)
- ✅ Added alignment links to Architecture (Architecture → Requirements, Tasks, Tests)
- ✅ Enhanced PARAMETERS.md with override pattern examples and reliability parameters
- ✅ Added Executive Summary with key capabilities
- ✅ Added Storage Architecture details
- ✅ Added Failure Modes & Recovery section to ARCHITECTURE.md
- ✅ Added Process Flow diagrams (session creation, conversation flow, vector retrieval)
- ✅ Enhanced API_DOCUMENTATION.md structure
- ✅ Added ASCII architecture diagrams

**Requirements Additions:**
- ✅ Added audit trail cryptographic signing requirements (CS1.3, NF1.7)
- ✅ Added circuit breaker, rate limiting, and reliability patterns (FR1.11)
- ✅ Enhanced observability requirements (metrics, tracing, structured logging) (FR1.9)
- ✅ Added IDP authorization modes (SE1.5)

**Architecture Additions:**
- ✅ Added IDP authorization modes (IDP Authorization Mode and Local Authorization Mode)
- ✅ Enhanced component descriptions with file paths and startup commands
- ✅ Added detailed process flows with step-by-step diagrams

---

### Version 0.1 (2025-01-XX)

**Initial Requirements:**
- ✅ Core four-server architecture defined
- ✅ Expert configuration system requirements
- ✅ Session management requirements
- ✅ Vector database integration requirements
- ✅ User and group management requirements
- ✅ Authentication and authorization requirements
- ✅ Audit and compliance requirements

---

**Document Status**: Restructured per RULES.md requirements with SV/BO/BR/FR/UC/CS/NF prefixes, numbering, and alignment links to Architecture, Tasks, and Tests.

## Configuration CRUD Requirements (CFG)

Profile concept for this project: expert configurations with LLM settings, prompt policy, channel bindings, vector-store integration, and access controls.

| ID | Requirement |
|----|-------------|
| CFG-01 | The system SHALL support creating a new expert configuration via the API with all expert settings that would otherwise be available via environment variables or env-file configuration. |
| CFG-02 | The system SHALL support reading expert configurations via the API, including both list and detail retrieval. |
| CFG-03 | The system SHALL support updating an existing expert configuration via the API. |
| CFG-04 | The system SHALL support deleting an expert configuration via the API. |
| CFG-05 | Expert configuration CRUD operations SHALL be available as MCP tools with equivalent functionality. |
| CFG-06 | Expert configuration change events SHALL be broadcast via the A2A interface per **PS-72 §A2A-change-events** (canonical envelope `{type, topic, timestamp, payload}`; reference implementation `cloud_dog_api_kit.a2a.events` ≥0.11.0; see platform-standards `docs/standards/PS-72-agent-to-agent.md`). |
| CFG-07 | Expert configuration CRUD operations SHALL be available in the WebUI with RBAC enforcement. |
| CFG-08 | The system SHALL support creating, reading, updating, and deleting users via the API. |
| CFG-09 | The system SHALL support creating, reading, updating, and deleting groups with role assignments via the API. |
| CFG-10 | The system SHALL support creating, listing, and revoking API keys with per-key capability scoping via the API. |
| CFG-11 | User, group, and API-key management SHALL be available via MCP, A2A, and WebUI with RBAC. |
| CFG-12 | All CRUD operations SHALL be audit logged with user identity, action, timestamp, and outcome. |
| CFG-13 | Only admin users SHALL be able to create, update, and delete expert configurations and manage users or groups; read-only access SHALL be available to authorised non-admin users. |

## Orchestration Enhancement Requirements (W28A-239)

### Service Composition Requirements (SC)

| ID | Requirement | Status |
|---|---|---|
| SC-01 | An expert configuration SHALL be able to declare one or more external services (MCP, A2A, REST tool endpoints) that it can invoke during conversation. | DELIVERED |
| SC-02 | External service declarations SHALL include endpoint URL, service type (`mcp`/`a2a`/`rest`), auth configuration (`api_key`, bearer token, or none), and a list of available tools/capabilities. | DELIVERED |
| SC-03 | The system SHALL support automatic tool discovery from registered MCP services via `tools/list`. | DELIVERED |
| SC-04 | An expert SHALL be able to invoke tools on registered external services during execution, with results incorporated into execution context. | DELIVERED |
| SC-05 | Service invocations SHALL respect the calling user's RBAC permissions. | DELIVERED |
| SC-06 | All external service invocations SHALL be logged in the audit trail with service name, tool called, request timestamp, response status, and token usage. | DELIVERED |
| SC-07 | External service health SHALL be checked before invocation; unhealthy services SHALL be skipped with a graceful fallback message. | DELIVERED |
| SC-08 | Service timeout and circuit-breaker settings SHALL be configurable per-service and through global defaults. | DELIVERED |

### Self-Referencing Agent Requirements (SR)

| ID | Requirement | Status |
|---|---|---|
| SR-01 | An expert configuration SHALL be able to reference other expert configurations within the same instance as sub-experts. | DELIVERED |
| SR-02 | A controlling expert SHALL be able to delegate sub-tasks to sub-experts, receiving their responses as tool results. | DELIVERED |
| SR-03 | Self-referencing loops SHALL be detected and prevented with a configurable maximum depth, default `3`. | DELIVERED |
| SR-04 | Sub-expert invocations SHALL create child sessions linked to the parent session for audit and context tracing. | DELIVERED |
| SR-05 | The controlling expert prompt SHALL be able to reference sub-expert capabilities by name. | DELIVERED |

### Prompt Management Requirements (PM)

| ID | Requirement | Status |
|---|---|---|
| PM-01 | Expert prompts SHALL support template variables for referencing available services and tools, including `{{services}}`, `{{tools}}`, and `{{sub_experts}}`. | DELIVERED |
| PM-02 | A prompt library SHALL allow creating, versioning, and assigning reusable prompts to experts. | DELIVERED |
| PM-03 | Prompts SHALL be manageable via API, MCP, and WebUI. | DELIVERED |
| PM-04 | Prompt testing SHALL be available via WebUI so an operator can run a prompt against test input and review the LLM response. | DELIVERED |

### Execution Mode Requirements (EM)

| ID | Requirement | Status |
|---|---|---|
| EM-01 | The expert-agent SHALL support a transactional mode with a single request and a single structured response, without persistent session state unless configured. | DELIVERED |
| EM-02 | The expert-agent SHALL continue to support chat mode with persistent session and message history. | DELIVERED |
| EM-03 | Transactional mode SHALL be invocable via REST, MCP, and A2A-compatible execution surfaces. | DELIVERED |
| EM-04 | Transactional mode SHALL accept `expert_id`, `input_text`, execution parameters, and optional context. | DELIVERED |
| EM-05 | Transactional mode SHALL return `output_text`, `token_usage`, `services_invoked`, and `execution_time_ms`. | DELIVERED |
| EM-06 | Remote callers SHALL be able to pass context as prior messages or document references. | DELIVERED |

### WebUI Requirements (WU)

| ID | Requirement | Status |
|---|---|---|
| WU-01 | The WebUI SHALL provide a Service Composition page for registering, editing, and removing external services. | DELIVERED |
| WU-02 | The WebUI SHALL allow editing expert configurations to add or remove service bindings and sub-expert references. | DELIVERED |
| WU-03 | The WebUI SHALL provide a test-run interface for composed experts, showing tool calls and sub-expert invocations inline. | DELIVERED |
| WU-04 | The WebUI SHALL show service health status on the service composition page. | DELIVERED |
| WU-05 | All WebUI service and expert composition management SHALL respect RBAC, with service registration restricted to admins and test runs available to authenticated users. | DELIVERED |

## W28A-875 Requirements Merge: WebUI Coverage a-i

This section merges the current expert-agent requirements with the W28A-875
instruction scope for:

- a. Experts/configurations
- b. Channels/chat channels
- c. Chat/sessions
- d. Knowledge
- e. Files
- f. External services
- g. Prompt templates
- h. Logs/audit trail
- i. Cross-cutting WebUI and RBAC constraints

`IMPLEMENTED` means the requirement is materially present in the current
backend and/or WebUI and the traceability evidence matches the live code.
`ACCEPTED-GAP` means the requirement is intentionally left narrower than the
original W28A-875 wording and is recorded in `docs/ACCEPTED-GAPS.md` with a
revisit date. `OUT_OF_SCOPE` means the requirement was explicitly removed with
documented rationale.

| ID | Requirement | Status | Current Evidence / Gap Summary |
|---|---|---|---|
| W875-REQ-01 | The system SHALL provide expert configuration list, detail, create, update, and delete operations in the API, with WebUI CRUD over the same records. | IMPLEMENTED | `/experts` API and `ExpertsPage` provide CRUD, with browser evidence in `w28a877-real-e2e` section `a)`. |
| W875-REQ-02 | The expert configuration WebUI SHALL allow operators to bind and unbind external services and sub-experts, not only inspect related records. | ACCEPTED-GAP | `ExpertsPage` exposes binding visibility and RBAC but still does not mutate bindings from the WebUI. Recorded in `docs/ACCEPTED-GAPS.md` pending a shared relation-editor pattern. |
| W875-REQ-03 | The system SHALL provide channel list, create, update, delete, and expert-linking operations in the API and WebUI. | IMPLEMENTED | `/channels` API plus `ChannelsPage` CRUD exist, with browser evidence in `w28a877-real-e2e` section `b)`. |
| W875-REQ-04 | The channel WebUI SHALL expose channel vector-store, tool, and service binding management where those backend capabilities exist. | ACCEPTED-GAP | Backend routes exist for channel vector-store/tool/service bindings, but `ChannelsPage` still limits itself to channel CRUD. Recorded in `docs/ACCEPTED-GAPS.md`. |
| W875-REQ-05 | The chat workbench SHALL allow an authenticated user to choose an expert, send a message through channel chat, and review the latest response plus live session inventory. | IMPLEMENTED | `ChatPage` creates or reuses a channel, posts to `/channels/{id}/chat`, shows the latest response, and renders a live session snapshot. |
| W875-REQ-06 | The chat workbench SHALL show conversation timeline, tool-call/sub-expert activity, and session lifecycle controls expected for composed expert execution. | ACCEPTED-GAP | `ChatPage` now shows a message timeline and tool-call panel, but destructive/session-management lifecycle controls intentionally live on `SessionsPage` rather than the chat workbench. Recorded in `docs/ACCEPTED-GAPS.md`. |
| W875-REQ-07 | The sessions surface SHALL support session inventory, detail inspection, paging/sorting, and destructive actions with explicit operator confirmation. | IMPLEMENTED | `SessionsPage` uses the shared table surface, exposes detail JSON, and supports delete/bulk delete flows; browser evidence is the dedicated `w28a877-real-e2e` section `d)`. |
| W875-REQ-08 | The knowledge surface SHALL support scoped knowledge CRUD for user, group, and session records from WebUI and API. | IMPLEMENTED | `/knowledge` API and `KnowledgePage` support scoped CRUD with `knowledge_type` and `knowledge_id`. |
| W875-REQ-09 | The files surface SHALL support file inventory, metadata inspection, download, ingest-to-knowledge, and storage metrics in WebUI. | IMPLEMENTED | `FilesPage` lists files and exposes metadata, download, ingest, delete, and metrics, with browser evidence in `w28a877-real-e2e` section `f)`. |
| W875-REQ-10 | The files surface SHALL provide first-class upload and structured ingest target selection in the WebUI rather than relying on implicit or prompt-based operator input. | ACCEPTED-GAP | Structured ingest target selection is now dialog-driven, but browser-native upload remains deferred until the platform file-transfer standard is settled. Recorded in `docs/ACCEPTED-GAPS.md`. |
| W875-REQ-11 | The external services surface SHALL show registered services and health state using the adopted shared WebUI table components. | IMPLEMENTED | `ServicesPage` renders inventory and health status with `AppDataTable`. |
| W875-REQ-12 | The external services WebUI SHALL allow admin users to register, edit, delete, and trigger health checks for services. | IMPLEMENTED | `ServicesPage` now provides admin register/edit/delete/health-check actions, with browser evidence in `w28a877-real-e2e` section `g)`. |
| W875-REQ-13 | The prompt template surface SHALL support template CRUD, preview, validation, and test-case generation from the WebUI. | IMPLEMENTED | `/prompts` API and `PromptsPage` implement those flows. |
| W875-REQ-14 | The monitoring surface SHALL present searchable audit/log data across audit, API, web, MCP, and A2A surfaces with AU-3-relevant fields visible in tabular form. | IMPLEMENTED | `LogTablePanel` supports those sources and renders actor/action/target/outcome/severity/timestamp/trace fields. |
| W875-REQ-15 | All tabular WebUI surfaces in scope SHALL use the platform `DataTable` component, directly or via a thin app wrapper. | IMPLEMENTED | Current app sources contain no raw HTML table markup; shared `EndpointTable`, `SimpleTable`, and `AppDataTable` all delegate to `@cloud-dog/ui` `DataTable`. |
| W875-REQ-16 | All create/edit dialogs in scope SHALL use the platform `EntityDialog` component, directly or via a thin app wrapper. | IMPLEMENTED | View-level CRUD flows use `CrudEntityDialog` over shared `EntityDialog`, and `JobsPage` uses `EntityDialog` directly for bulk actions. |
| W875-REQ-17 | The expert-agent WebUI SHALL expose the routed pages required by this scope at `/chat`, `/channels`, `/sessions`, `/experts`, `/services`, `/knowledge`, `/files`, `/admin/prompts`, `/admin/monitoring`, and `/admin`. | IMPLEMENTED | The app router already declares each required route and smoke coverage exists. |
| W875-REQ-18 | RBAC enforcement SHALL restrict admin-only operations to admin users while preserving read or owner-scoped access for authorised non-admin users. | IMPLEMENTED | Current browser and API evidence covers scoped non-admin visibility plus admin-only mutation paths across experts, channels, knowledge, files, and services. |

## W28A-874 Orchestration Enhancement Requirements

Building on the delivered SC, SR, PM, EM, and WU requirements, this section introduces
scenario-driven orchestration, enhanced prompt integration, and context-managed remote
execution.

### FR-ORCH-01: Expert Composition with Priority-Ordered Tool Binding

| ID | Requirement | Status |
|---|---|---|
| FR-ORCH-01a | An expert configuration SHALL support binding to both sub-experts AND external MCP/A2A/REST services simultaneously, forming a unified tool surface. | NEW |
| FR-ORCH-01b | Each binding SHALL carry a priority integer; the expert's LLM SHALL receive the tool list ordered by priority (lowest value = highest priority). | NEW |
| FR-ORCH-01c | Tool name collisions across bindings SHALL be resolved by priority — the highest-priority binding's tool wins. | NEW |
| FR-ORCH-01d | The unified tool surface SHALL be exposed to the LLM as a single flat list of functions/tools, regardless of origin (local, sub-expert, or external service). | NEW |

### FR-ORCH-02: Self-Referencing Controller Orchestration

| ID | Requirement | Status |
|---|---|---|
| FR-ORCH-02a | An expert flagged `is_controller=True` SHALL be able to orchestrate other experts via its prompt directives, deciding at runtime which sub-experts to delegate to. | NEW |
| FR-ORCH-02b | The controller's system prompt SHALL have access to `{{sub_expert_capabilities}}` — a structured summary of each sub-expert's name, description, and tool surface. | NEW |
| FR-ORCH-02c | Controller experts SHALL support LLM-driven delegation: the LLM emits a `delegate_to_expert` tool call, and the system routes it through `DelegationManager`. | NEW |
| FR-ORCH-02d | Existing loop detection (SR-03) and max depth (SR-05) SHALL apply to controller-initiated delegations identically. | DELIVERED (extends SR-03) |

### FR-ORCH-03: Chat + Transactional Execution Mode Selection

| ID | Requirement | Status |
|---|---|---|
| FR-ORCH-03a | Each expert configuration SHALL declare a default execution mode (`chat` or `transactional`), overridable per invocation. | NEW |
| FR-ORCH-03b | Chat mode SHALL maintain a persistent session with message history, context window management, and automatic summarization (extends EM-02). | DELIVERED (extends EM-02) |
| FR-ORCH-03c | Transactional mode SHALL support pre-execution service calls, delegations, LLM generation, and post-execution service calls in a single pipeline (extends EM-01). | DELIVERED (extends EM-01) |
| FR-ORCH-03d | A new hybrid mode `chat_transactional` SHALL allow multi-turn chat with transactional pipeline stages (pre/post service calls) on each turn. | NEW |

### FR-ORCH-04: Remote Execution with Managed Context

| ID | Requirement | Status |
|---|---|---|
| FR-ORCH-04a | REST `POST /experts/{id}/execute` SHALL accept `session_id` for context continuity across invocations. | DELIVERED (extends EM-04) |
| FR-ORCH-04b | MCP `tools/call execute_expert` SHALL accept the same payload as REST execute. | DELIVERED (extends EM-03) |
| FR-ORCH-04c | Context SHALL support three sources: `prior_messages` (injected history), `documents` (reference text), and `variables` (key-value pairs for prompt interpolation). | NEW |
| FR-ORCH-04d | Context retention SHALL be configurable per expert: `none` (ephemeral), `session` (within session), `rolling` (last N turns, configurable). | NEW |
| FR-ORCH-04e | Cross-session context sharing SHALL be supported via `context_group_id` — sessions in the same group share a common knowledge pool. | NEW |

### FR-ORCH-05: Scenario Workflows

| ID | Requirement | Status |
|---|---|---|
| FR-ORCH-05a | The system SHALL support defining reusable workflows as "scenarios" — named, versioned sequences of expert and service calls. | NEW |
| FR-ORCH-05b | A scenario definition SHALL include: name, description, version, ordered steps, conditional branching (if/else on step output), and error handling (retry, skip, abort). | NEW |
| FR-ORCH-05c | Each scenario step SHALL reference an expert ID or service ID, an input template (with `${variable}` interpolation from prior step outputs), and an output binding name. | NEW |
| FR-ORCH-05d | Scenario execution SHALL create a parent session with child sessions per step, reusing the delegation tree for audit and tracing. | NEW |
| FR-ORCH-05e | Scenarios SHALL be manageable via API (`/scenarios` CRUD) and WebUI (ScenarioDesignerPage). | NEW |
| FR-ORCH-05f | Scenario execution SHALL be invocable via REST `POST /scenarios/{id}/run`, MCP `execute_scenario`, and A2A task submission. | NEW |

### FR-ORCH-06: Enhanced Prompt Integration for Service Calls

| ID | Requirement | Status |
|---|---|---|
| FR-ORCH-06a | Expert prompts SHALL support `{{available_tools}}` — expanded to the full unified tool surface with name, description, and inputSchema per tool. | NEW (extends PM-01) |
| FR-ORCH-06b | Expert prompts SHALL support `{{service:<name>:tools}}` — tools from a specific named service. | NEW |
| FR-ORCH-06c | Expert prompts SHALL support `{{expert:<name>:capabilities}}` — description and tool list from a specific sub-expert. | NEW |
| FR-ORCH-06d | Expert prompts SHALL support `{{context:variables}}` — the current context variables as a formatted block. | NEW |
| FR-ORCH-06e | Expert prompts SHALL support `{{scenario:current_step}}` and `{{scenario:prior_outputs}}` during scenario execution. | NEW |

### FR-ORCH WebUI Requirements

| ID | Requirement | Status |
|---|---|---|
| WU-ORCH-01 | The Experts page SHALL allow configuring an expert as a controller with priority-ordered service and sub-expert bindings. | NEW |
| WU-ORCH-02 | A new Scenarios page SHALL provide scenario CRUD with a step editor supporting drag-and-drop ordering, conditional branching, and input/output binding configuration. | NEW |
| WU-ORCH-03 | A new Scenario Runner page SHALL allow executing a scenario with real-time step progress, per-step output preview, and overall result display. | NEW |
| WU-ORCH-04 | The Chat page SHALL show tool calls and sub-expert delegations inline in the conversation timeline. | NEW (extends W875-REQ-06) |
| WU-ORCH-05 | The Expert detail page SHALL display a composition topology view showing bound services and sub-experts as a visual graph. | NEW |

## W28A-883 PS-78 Cross-Platform File Handling Addendum

### Verified current state

- The API already exposes `/files`, `/files/upload`, `/files/upload_base64`, `/files/{id}`, `DELETE /files/{id}`, and `/files/{id}/download`.
- File persistence uses `cloud_dog_storage.backends.local.LocalStorage` in the multimedia and API file flows.
- The WebUI `FilesPage` supports file inventory, metadata, download, delete, and ingest-to-knowledge, but no upload control is currently wired into the page.

### Required additions to satisfy PS-78

- Add first-class WebUI upload using `FileDropZone` or a standard file input on `FilesPage`.
- Add MCP file upload/download contracts using base64 or URL references instead of relying on API-only file flows.
- Add A2A file transfer for expert workflows that exchange artifacts between agents.
- Add chat-message file attachment and returned-file rendering/download in the conversational UI.
- Add explicit URI source intake policy for `http://`, `https://`, `s3://`, `ftp://`, and `file://`.

### Required PS-78 test plan

- API: multipart upload, base64 upload, list metadata, download binary, delete.
- MCP: base64 upload/download and URI-source upload.
- A2A: agent-to-agent file handoff with base64 or URL payloads.
- WebUI: upload, download, ingest-to-knowledge, delete, RBAC.
- Chat: attach file to a prompt, verify returned file artifact can be viewed and downloaded.

## PS-40 / W28A-619 Logging and Audit Requirements

The service MUST use `cloud_dog_logging` as the only application and audit logging implementation. Raw stdlib logging setup, direct `logging.getLogger()` calls, bespoke audit emitters, and print-based operational logging are not compliant except inside the platform logging package itself.

Every auditable event MUST emit a PS-40/NIST AU-3 audit record with: `event_type`, `action`, `timestamp`, `service`, `component`, `service_instance`, `environment`, `source_host`, `source_process`, `source_application`, `source_address` where available, `destination_address` where available, `outcome`, actor identity including user/service/system plus account/process/device identifiers where available, `target`, `process_id`, `affected_files` where relevant, `correlation_id`, `trace_id`, and `request_id`.

Auditable events MUST include authentication and authorisation decisions, user/group/API-key/RBAC changes, expert/channel/session/service/knowledge/file operations, chat and generated-answer calls, MCP/A2A/API calls, job lifecycle changes, configuration changes, data access and mutation, denials, failures, and privileged operations. Secrets MUST be redacted before persistence. Tests MUST cover schema fields, event coverage, redaction, append-only audit persistence, retention/integrity, and WebUI observability rendering/filtering.

## 5. Cyber Security & Negative Flows

Mandatory schema per PS-REQ-TEST-TRACE v1.0 §3.4. Every project covers anon-denied, wrong-role-denied, missing-param-error per declared surface. The CS rows below are platform-baseline; project-specific extensions append in §5.1.

| ID | Threat / negative scenario | Surface | Role(s) attempted | Expected | Tests |
|---|---|---|---|---|---|
| `CS-001` | Anon attempts data read | `api`, `mcp`, `a2a`, `webui` | `anon` | `401` | (to be bound in Instruction 4 by operator) |
| `CS-002` | read-only attempts write | `api`, `mcp` | `read-only` | `403` | (to be bound in Instruction 4 by operator) |
| `CS-003` | Missing required param | `api` | `admin` | `422` | (to be bound in Instruction 4 by operator) |
| `CS-004` | Wrong-role privileged op | `mcp` | `read-write` | `403` | (to be bound in Instruction 4 by operator) |



<!-- W28C-1710a recovery: full content from archive/2026-06-12/DESCRIPTION.md (archived sha256=affbadd98dca, 142 lines) -->

## Recovered domain content — `archive/2026-06-12/DESCRIPTION.md` (142 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/DESCRIPTION.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# Expert Agent MCP Server - Description

## 1) 50-word Overview
Expert Agent MCP Server is a multi-interface AI orchestration platform that runs API, Web UI, MCP, and A2A services together. It manages experts, channels, sessions, files, knowledge, testing, and analytics with role-based controls. It integrates LLM providers and vector stores for retrieval, evaluation, and operational-grade conversational automation at scale reliably.

## 2) Features & Benefits
| Features | Benefits |
|---|---|
| Four-server architecture | Separation of concerns and resilient operations |
| REST, MCP, A2A interfaces | One backend, many integration paths |
| Expert/channel configuration | Reusable AI behavior per business scenario |
| Session and history management | Persistent context and controlled retention |
| Vector store integration | Retrieval-augmented responses across sources |
| File upload/download/translation | Document workflows for multilingual operations |
| Web UI testing interface | Validate channels before production use |
| Analytics and job tracking | Operational transparency and performance control |
| API-key and RBAC enforcement | Controlled access by user and group |
| Docker single-container mode | Fast local deployment and smoke validation |

## 3) Product Overview
The product solves fragmented AI operations where teams need consistent expert behavior, reliable context management, and auditable access across multiple interfaces. It helps engineering, operations, and product teams that need AI services exposed to users, agents, and systems simultaneously.

It supports expert-specific LLM configurations, channel-level controls, knowledge retrieval, and historical context while enforcing permissions and auditability. The platform helps when organisations require controlled automation, repeatable testing, and production observability instead of ad hoc prompt tooling.

Primary value:
- Standardize AI interactions through channel and expert configuration.
- Unify human UI workflows and machine-to-machine interfaces.
- Provide governed operations for testing, rollout, and troubleshooting.

## 4) Technical Capabilities
The system provides:
- Multi-protocol interface support: REST API, MCP tools/modes, A2A streaming, and Web UI.
- Config-driven LLM and embedding backends (Ollama/OpenAI-compatible/OpenRouter and others).
- Session lifecycle management, history scopes, and queue/job orchestration.
- Vector operations with configurable providers (Chroma, Qdrant, Weaviate, OpenSearch, PGVector).
- File workflows: upload (multipart/base64), download, translation via expert, ingest to vector store.
- Test surfaces across ST/IT/AT suites with real-server execution and explicit environment mapping.

Execution flows include sync/async channel chat, MCP tool calls with session lifecycle, file-to-RAG pipelines, and browser-driven UI operations validated against live APIs.

## 5) Where It Fits
This platform fits as an AI orchestration layer between enterprise applications and LLM/vector infrastructure. It integrates with:
- Internal apps needing authenticated chat/testing/admin operations.
- Agent ecosystems consuming MCP/A2A protocols.
- Data/document workflows requiring ingestion, retrieval, translation, and traceability.
- CI/CD and quality pipelines requiring executable compliance tests and environment-specific validation.

It complements API gateways, identity systems, observability stacks, and managed databases/vector backends.

## 6) Architecture
Core deployment model:
- API server (business/control plane)
- Web UI server (human operations)
- MCP server (tool protocol compatibility)
- A2A server (real-time agent communication)

Infrastructure components:
- SQL system database (MariaDB/PostgreSQL supported)
- Optional Redis/queue backend
- Vector store backend(s) per environment
- File storage volume for multimedia/documents
- Log/audit pipelines and health endpoints

Deployment patterns:
- Local/dev single-node
- Single-container four-server mode
- Multi-host/remote deployments with explicit port and secret management

Security model:
- API keys and role/group-based authorisation
- Admin-scoped operations for sensitive routes
- Audit logging for key state-changing actions
- Secret separation via private env-secrets files

## 7) Technical Design
Business and non-functional requirements are met through:
- Config hierarchy (`os.environ` -> env file -> defaults) for deterministic behavior.
- Strong server lifecycle control via `server_control.sh` for start/stop/status.
- Health contracts that expose application identity and loaded env-file provenance.
- Real-service testing requirements for ST/IT/AT suites (no mock substitution where prohibited).
- RBAC gates and admin checks for privileged actions (users/groups/jobs/file management).
- Structured job/session/resource models supporting async operations and recoverability.

Security design details include API-key verification, admin-only endpoints, and explicit failure behavior for unavailable required services.

## 8) Key Capabilities
Expert and Channel Control:
Organisations define expert behavior once, then apply it consistently through channels with controlled prompts, model choices, and permissions. Scenario: support and engineering teams run different experts with shared governance.

Cross-Interface Delivery:
The same backend serves Web UI operators, REST clients, MCP tools, and A2A agent flows. Scenario: internal UI users and automated agents both query one channel configuration.

Document-Centric Workflows:
Users upload files, translate content, ingest into vector stores, and query retrieved knowledge. Scenario: multilingual documentation support with searchable translated outputs.

Operational Validation:
Testing interfaces and executable suites validate readiness before release. Scenario: run channel tests plus browser E2E checks to catch API/UX regressions early.

Governed Access and Audit:
Role and group controls restrict sensitive operations while preserving traceability. Scenario: admin reviews queue/jobs and logs without exposing unrelated tenant data.

## 9) Example Use Cases
Use Case A: Customer Support Assistant Rollout
- Configure support expert and channel.
- Upload policy files and ingest into vector store.
- Validate responses via testing interface.
- Expose to web operators and MCP-integrated agents.

Use Case B: Engineering Troubleshooting Copilot
- Create specialist expert with engineering prompt template.
- Attach relevant knowledge history and vector collections.
- Use A2A stream for tool/agent coordination.
- Monitor queue status, latency, and error analytics.

Use Case C: Multilingual Knowledge Processing
- Upload English source files.
- Translate via configured expert to Chinese.
- Reupload and ingest translated artifacts.
- Query by token/subject to verify retrieval quality.

## 10) Deployment Patterns
Containerized:
- Single-container four-server runtime for fast local testing.
- Optional browser-enabled image for Selenium/Playwright E2E.

Database:
- MariaDB or PostgreSQL for system records.
- Vector backends selectable by environment/profile.

File System:
- Mounted volumes for logs, storage, database artifacts, and cache.
- Explicit file APIs for upload/download/translation/ingestion flows.

Network:
- Local host-network mode for smoke and development.
- Remote/bridge deployments with explicit published ports and DNS/TLS configuration.

Operations:
- Environment-per-scenario execution (`--env private/...`).
- Health probes and smoke tests for startup validation.
- Test cohorts mapped in `docs/TESTS.md` for repeatable confidence gates.


<!-- W28C-1710b design-delta additions (2026-06-14T18:01:23Z); SHA chain in working/W28C-1710b/KNOWLEDGE-PRESERVATION-DELTA.md -->

## PS-REQ-TEST-TRACE schema completion (W28C-1710b)

Per the binding contract (`docs/standards/PS-REQ-TEST-TRACE.md` §2 + §3), every FR-NNN row in this file declares the following schema (default values; operator amends per row in W28C-1711):

```yaml
surface: ['api', 'mcp', 'a2a', 'webui']  # programme default for expert-agent-mcp-server
priority: must  # default; operator amends per FR
since: 2026-06-14  # carried forward unless older anchor known
last-verified: 2026-06-14
tests: []  # populated by W28C-1711 binding
crud: N/A  # default; operator amends per FR
```

## Baseline CS-NNN rows (PS-REQ-TEST-TRACE §3.4 — added by W28C-1710b)

Every project MUST have CS-NNN rows for `anon-denied`, `wrong-role-denied`, `missing-param-error` per surface. Programme baseline:

| CS-NNN | Scenario | Surface | Expected | Roles |
|---|---|---|---|---|
| `CS-005` | anon-denied | `api` | `401` | `anon` |
| `CS-006` | anon-denied | `mcp` | `401` | `anon` |
| `CS-007` | anon-denied | `a2a` | `401` | `anon` |
| `CS-008` | anon-denied | `webui` | `401` | `anon` |
| `CS-009` | wrong-role-denied | `api` | `403` | `read-only` |
| `CS-010` | wrong-role-denied | `mcp` | `403` | `read-only` |
| `CS-011` | wrong-role-denied | `a2a` | `403` | `read-only` |
| `CS-012` | wrong-role-denied | `webui` | `403` | `read-only` |
| `CS-013` | missing-param-error | `api` | `422` | `*` |
| `CS-014` | missing-param-error | `mcp` | `422` | `*` |
| `CS-015` | missing-param-error | `a2a` | `422` | `*` |
| `CS-016` | missing-param-error | `webui` | `422` | `*` |

_These CS-NNN rows are pending W28C-1711 test binding. Each row binds to one or more `@pytest.mark.negative` tests with explicit expected denial code._



<!-- W28E-1809A: de-mechanised semantic FR/NF catalogue (replaces the W28C-1711-R3 stub form banned by PS-CLOSEOUT-WARRANTY §6 / AGENT-LESSONS §6.92-6.93). FR-NNN/CS-NNN ids are immutable and keep their existing @pytest.mark.req() bindings; only the Description is rewritten to the real capability, crosswalked to the rich §1-§6 legacy requirement and verified against the bound tests. -->

## Functional Requirements (canonical FR-NNN — semantic, W28E-1809A)

Each `FR-NNN` below is the immutable canonical id bound by `@pytest.mark.req("FR-NNN")` in the test suite. `Legacy` crosswalks to the rich requirement in §1-§6; `Description` is the real capability the bound tests exercise — semantic statements, not mechanical derivations.

| ID | Legacy | Surface | Priority | Description |
|---|---|---|---|---|
| `FR-001` | CS-1.1 (Authentication) | `internal` | `should` | Authenticate every caller (API key, cookie session, or JWT) before service logic runs on the API, MCP, A2A and WebUI surfaces; anonymous access to protected operations is denied (401). |
| `FR-002` | CS-1.3 (Audit Events) | `internal` | `should` | Emit structured audit events for security- and business-significant operations (auth, mutation, admin, config, job lifecycle) conforming to PS-AUDIT-LOG. |
| `FR-003` | CS-1.4 (Data Protection) | `internal` | `should` | Protect data in transit and at rest; scope every user/group/session/knowledge/job object by owner; redact secrets and support PII removal from session, history, results and audit. |
| `FR-004` | FR-1.1 (Expert Configurations) | `internal` | `should` | Manage expert configurations — title, description, scope, LLM provider/model/parameters, system prompt, tool and service bindings, enable/disable with access control, plus auto-prompt generation and LLM-backed prompt validation. |
| `FR-005` | FR-1.10 (Audit & Compliance) | `internal` | `should` | Maintain an audit & compliance trail across experts, channels, sessions, knowledge, files, services and prompts, with user/group access scoping and searchable history. |
| `FR-006` | FR-1.11 (Reliability & Controls) | `internal` | `should` | Reliability controls — per-user/group concurrency and session limits, request queueing, graceful degradation, retry/timeout policy and resource management under load. |
| `FR-007` | FR-1.12 (Channel-Based Expert Configurations) | `internal` | `should` | Channel-based expert configuration — bind experts, knowledge, services and RBAC roles to channels, with per-channel LLM/service/prompt overrides and channel type (chat/transactional/workflow). |
| `FR-008` | FR-1.13 (Multimedia Processing) | `internal` | `should` | Multimedia/file processing pipeline — ingest, preview and extract file content that feeds knowledge bases and conversations. |
| `FR-009` | FR-1.14 (Comprehensive Job/Call Logging) | `internal` | `should` | Comprehensive job/call logging — record every expert/tool/channel run with timings, status, correlation id and per-message tool-call logs. |
| `FR-010` | FR-1.15 (Auto-Prompt Generation) | `internal` | `should` | Auto-generate example/starter prompts (ROLE/CONTEXT/tool-calling) from expert title+description and channel/knowledge context. |
| `FR-011` | FR-1.16 (Tool & External Service Management) | `internal` | `should` | Register, discover, health-check and invoke external tools/services via the service registry, and bind them to experts and channels. |
| `FR-012` | FR-1.17 (API Key Management) | `api` | `should` | API key lifecycle — create, rotate and revoke keys with owner/role/group scope and expiry, and surface associated users/groups on key detail. |
| `FR-013` | FR-1.2 (Conversation Management) | `a2a,api,mcp` | `should` | Persistent session/conversation management — retention windows, automatic context summarization, per-user/group history isolation, PII controls and concurrency limits across API, MCP and A2A. |
| `FR-014` | FR-1.20 (Log History Management) | `internal` | `should` | Log/history management — search, filter, paginate and export logs by channel, expert, session and user with RBAC scoping. |
| `FR-015` | FR-1.21 (Web UI Channel Management) | `webui` | `should` | WebUI channel management — CRUD channels and their bindings, view history/messages, and test the channel from the Channels page. |
| `FR-016` | FR-1.22 (Web UI Testing Interface) | `webui` | `should` | WebUI testing/console interface for exercising experts and channels and viewing thinking, responses and timings. |
| `FR-017` | FR-1.23 (Channel Analytics and Statistics) | `internal` | `should` | Channel analytics and statistics — aggregate usage, health and bound-expert metrics per channel. |
| `FR-018` | FR-1.26 (Queue Management with CRUD Operations) | `mcp` | `should` | Job/queue management with CRUD over the cloud_dog_jobs queue — list, detail, cancel, retry, resubmit and dead-letter (PS-AJOBS). |
| `FR-019` | FR-1.27 (Group Admin Role Management) | `mcp` | `should` | Group-admin role management — delegate group/user/membership administration with cascade effects and live revocation. |
| `FR-020` | FR-1.28 (Prompt Test Case Generation) | `mcp` | `should` | Generate prompt test cases from expert/channel/knowledge context to drive prompt validation. |
| `FR-021` | FR-1.29 (LLM Validation Testing) | `mcp` | `should` | LLM validation testing — verify model wiring and response shape per provider/model from the WebUI/API. |
| `FR-022` | FR-1.3 (Vector Database Integration) | `mcp` | `should` | Vector database integration via cloud_dog_vdb (Chroma, Qdrant, OpenSearch, Weaviate, PGVector, Elastic) with collection-based group isolation. |
| `FR-023` | FR-1.30 (Response Quality Evaluation) | `mcp` | `should` | Response quality evaluation/scoring — compute and surface answer-quality metrics and scoring readiness (covered by the AT/ST/IT response-quality suites). |
| `FR-024` | FR-1.31 (Knowledge History CRUD with Permissions) | `internal` | `should` | Knowledge history CRUD with per-user/group permissions and lifecycle (create/read/update/delete with scope checks). |
| `FR-025` | FR-1.32 (Job Queue CRUD Operations (Admin)) | `internal` | `should` | Administrative job-queue CRUD — admin control of jobs and dead-letter beyond the standard owner controls. |
| `FR-026` | FR-1.34 (File Store Management (Admin)) | `internal` | `should` | Admin file-store management via cloud_dog_storage — list, view, ingest and delete files with URI and storage-usage visibility. |
| `FR-027` | FR-1.4 (Knowledge Management) | `internal` | `should` | Knowledge management — knowledge bases with type/parameters/ingest/lifecycle/metadata, import/reuse from sources, and admin operations (prune, search, index). |
| `FR-028` | FR-1.43 (Web UI Full Functional Coverage and Operational Safety) | `webui` | `should` | WebUI full functional coverage and operational safety — read-only write-gate returns 403, anonymous returns 401, and every admin page renders without leaking state. |
| `FR-029` | FR-1.5 (User & Group Management) | `api` | `should` | User and group management via cloud_dog_idam — CRUD users, groups and memberships with RBAC enforcement. |
| `FR-030` | FR-1.6 (Access Control & Authorization) | `internal` | `should` | Access control and authorization — RBAC over reads, writes, admin and job-control operations with wrong-role denial (403) and resource-scoped bindings. |
| `FR-031` | FR-1.7 (API & Integration) | `a2a,api,mcp` | `should` | API/MCP/A2A integration surfaces — versioned REST routes with OpenAPI, discoverable MCP tools, and A2A agent-card/task contracts. |
| `FR-032` | FR-1.8 (Web UI & Administration) | `webui` | `should` | WebUI and administration — the common operator taxonomy (dashboard, admin users/groups/keys/RBAC, developer consoles, settings, about) with consistent branding. |
| `FR-033` | FR-1.9 (Observability & Monitoring) | `internal` | `should` | Observability and monitoring — health/readiness, metrics, and a monitoring page spanning users/experts/sources/channels/sessions with export. |
| `FR-034` | NF-1.1 (Performance) | `internal` | `should` | Performance — bounded latency budgets for API/LLM/VDB operations; long-running work runs asynchronously via jobs. |
| `FR-035` | NF-1.2 (Availability) | `internal` | `should` | Availability — health/readiness checks, graceful degradation, and recovery of stale/stuck jobs. |
| `FR-036` | NF-1.4 (Compliance) | `internal` | `should` | Compliance — NIST-aligned logging/audit and conformance to the platform standards set. |
| `FR-037` | NF-1.5 (Portability) | `internal` | `should` | Portability — pluggable LLM/VDB/DB/storage backends through platform packages, selected by configuration. |
| `FR-038` | NF-1.6 (Testability) | `internal` | `should` | Testability — a multi-tier (QT/UT/ST/IT/AT) test suite with enforced requirement-to-test traceability. |
| `FR-039` | NF-1.8 (Data Retention & Privacy) | `internal` | `should` | Data retention and privacy — configurable retention/TTL, PII removal, and owner-scoped deletion of sessions/history/knowledge. |
| `FR-040` | SV-1.1 (System Overview) | `internal` | `should` | System scope/overview — a multi-expert LLM orchestration MCP service exposing API, MCP, A2A and WebUI surfaces. |
| `FR-041` | SV-1.2 (In-Scope (v1)) | `internal` | `should` | In-scope v1 capabilities — experts, channels, sessions, knowledge, files, services, prompts and jobs. |
| `FR-042` | SV-1.3 (Out-of-Scope (v1)) | `internal` | `should` | Out-of-scope v1 boundary — documented non-goals that the service deliberately does not implement, enforced by scope tests. |

### Per-tier comprehensive-coverage requirements (FR-043..047)

These canonical ids aggregate the multi-tier test suite that exercises the capabilities above; they are real coverage requirements rolling up to FR1.42 (Comprehensive Expert Test Suite), NF1.6 (Testability) and the §8 CQ quality gates — not tier-name stubs.

| ID | Tier | Surface | Priority | Description |
|---|---|---|---|---|
| `FR-043` | unit | `a2a,cli` | `should` | Unit-tier coverage — isolated unit tests for orchestration internals (service composition, delegation, transactional execution), LLM-provider abstraction and retry policy, knowledge versioning, outbound-service credentials, A2A card mount and service-create gating. Test-pyramid base; rolls up to FR1.42 Comprehensive Expert Test Suite, NF1.6 Testability and the CQ quality gates. |
| `FR-044` | application | `webui` | `should` | Application-tier coverage — end-to-end AT scenarios across channel-chat (history scopes, vector-store RAG, error handling), group-admin role management, entropy checking, knowledge-versioning rollback, session history and forensic WebUI E2E. Rolls up to FR1.42 Comprehensive Expert Test Suite and FR1.43 WebUI full functional coverage. |
| `FR-045` | system | `api,webui` | `should` | System-tier coverage — ST readiness for storage backends (PostgreSQL, MariaDB), log search/export, the LLM-validation runner, knowledge-history CRUD, queue CRUD endpoints, file-ingest-to-vector-store and single-container Docker smoke. Rolls up to FR1.42 and NF1.2 Availability. |
| `FR-046` | smoke | `internal` | `should` | Smoke-tier coverage — the expert auth-surface smoke that verifies the core authenticated surfaces boot and respond. Rolls up to FR1.42 and NF1.2 Availability. |
| `FR-047` | integration | `api,mcp,webui` | `should` | Integration-tier coverage — IT across channel REST async/sync, log-history export, prompt test generation, API-key cross-interface, group-admin cross-service, transactional orchestration, WebUI testing interface and analytics aggregation. Rolls up to FR1.42 and FR1.31 Knowledge History CRUD. |

## Non-Functional Standards-Conformance Requirements (NF-NNN — W28E-1809A)

Canonical `NF-NNN` rows binding the quality-tier (`QT_COMPLIANCE`) standards-conformance suite. These replace the legacy `@pytest.mark.probe` markers on those tests with semantic `@pytest.mark.req("NF-NNN")` bindings.

| ID | Surface | Priority | Description |
|---|---|---|---|
| `NF-001` | `internal` | `must` | Platform-package adoption conformance — the service consumes the approved platform packages (cloud_dog_config / logging / api_kit / idam / db / jobs / llm / vdb / cache / storage) and ships zero bespoke replacements (RULES §1.4; PS-COMMON-SVC-REQ CSR-001). Bound by tests/quality/QT_COMPLIANCE/test_qt_package_adoption.py. |
| `NF-002` | `internal` | `must` | Configuration & secret-handling conformance — all config flows through cloud_dog_config, secrets resolve from Vault `${vault…}` expressions, defaults/config carry no secrets, and per-tier env files exist (RULES §2/§11; CSR-010). Bound by tests/quality/QT_COMPLIANCE/test_qt_vault_config_contract.py. |
| `NF-003` | `internal` | `must` | Platform-migration completeness — src/ contains no raw FastAPI app construction, no bespoke auth, no yaml.safe_load for config and no os.environ reads for config (RULES §1.4.1; CSR-001). Bound by tests/quality/QT_COMPLIANCE/test_qt_migration_completeness.py. |
| `NF-004` | `internal` | `must` | RULES.md / platform-standards compliance — zero hardcoded URLs or credentials, no direct external-library imports, no pytest.skip or mocks in IT/AT, and required file headers + function docstrings present (RULES §2.4/§4.2/§5.3). Bound by tests/quality/QT_COMPLIANCE/test_qt_rules_compliance.py. |
| `NF-005` | `internal` | `must` | Requirements↔test↔code traceability conformance — every requirement maps to tests and source, every test maps to a requirement, the delivery matrix is complete and there are no orphan test files (PS-REQ-TEST-TRACE). Bound by tests/quality/QT_COMPLIANCE/test_qt_traceability.py. |

## PS-COMMON-SVC-REQ consumption (pinned by reference — W28E-1822)

Per PS-COMMON-SVC-REQ §4, the common identity/config/request-context/API/MCP/A2A/WebUI/jobs/storage/audit/logging/security/deployment baseline is **pinned by reference**, not restated. expert-agent applicable surfaces: API, MCP, A2A, WebUI, LLM orchestration, jobs, audit. CSR-001..040 map to local rows as follows (full row-by-row matrix in the lane evidence `ps_common_svc_req_consumption.tsv`):

| CSR area | CSR ids | Local mapping |
|---|---|---|
| Reuse platform packages / shared core | CSR-001, CSR-002 | `NF-001`, `NF-003`, FR1.x architecture |
| Ownership / context / auth / RBAC | CSR-003..006 | `FR-001`, `FR-003`, `FR-029`, `FR-030`, `CS-001`..`CS-016` |
| Config / profile / session / secrets | CSR-007..010 | `FR-039`, `NF-002`, `FR-013` |
| Health / OpenAPI / API / MCP / A2A / WebUI | CSR-011..016 | `FR-031`, `FR-032`, `FR-033` |
| Jobs / storage / artifacts / cache / DB | CSR-017..022 | `FR-018`, `FR-025`, `FR-026`, `FR-022` |
| Audit / logging / validation / limits | CSR-023..028 | `FR-002`, `FR-005`, `FR-006` |
| Deployment identity / preprod / docs-trace | CSR-029..031, CSR-040 | Stream-B/C; `NF-005` |
| Negative-flow / error / credential / WebUI taxonomy | CSR-032..039 | `CS-001`..`CS-016`, `FR-028`, `FR-012` |

## Expert Agent WebUI Feedback Trace (EA-01..EA-129 — W28E-1809A)

Every atomic operator WebUI feedback item from GarysWorkingNotes (Expert Agent WebUI Feedback Capture; 129 items) is traced to a requirement and an owning stream. Most are WebUI drive-out targets for Stream-C (Playwright/E2E); backend-wiring items go to Stream-B; cross-cutting (CC) items are also routed to W28E-1825. Surface and requirement use the canonical ids above so the chain `EA item → REQ → UC → test` is closed.

| EA id | Page | Maps to REQ | Surface | Owning stream | Observation |
|---|---|---|---|---|---|
| EA-01 | Cross-product requirements | `FR-018` | `webui` | Stream-B | Expert agent MUST use Jobs to manage multiple concurrent async expert/tool/channel runs, and must surface them on a J… |
| EA-02 | Cross-product requirements | `FR-018` | `webui` | Stream-B/C | Brand: page chrome / nav must show **Expert Agent** (two words, capitalised), not "expertagent" or "Expert agent". |
| EA-03 | Dashboard | `FR-033` | `webui` | Stream-C | Build-info: dashboard shows `v0.1.0` — must update from build metadata, not hard-coded. |
| EA-04 | Dashboard | `FR-033` | `webui` | Stream-C | API status indicator shows **Amber** with no underlying cause exposed — wire to real health and tooltip the reason. |
| EA-05 | Dashboard | `FR-033` | `webui` | Stream-B | Memory tile reads `0` — must show real memory metric. |
| EA-06 | Dashboard | `FR-033` | `webui` | Stream-B | CPU tile reads `0` — must show real CPU metric. |
| EA-07 | Dashboard | `FR-033` | `webui` | Stream-C | Remove dashboard quick-links "Open Chat / Users / Monitoring / API Docs" — duplicates of nav. |
| EA-08 | Dashboard | `FR-005` | `webui` | X-1825(CC) | Audit refresh: add an enable/disable toggle for auto-refresh. **Apply across ALL audit DataTables in ALL projects.** … |
| EA-09 | Dashboard | `FR-014` | `webui` | X-1825(CC) | Log Source drop-down (good here) — replicate this pattern across all 9 projects and consolidate audit + logs into a s… |
| EA-10 | Dashboard | `FR-033` | `webui` | Stream-C | Recent Activity: multi-select rows + download as JSON or CSV. |
| EA-11 | Dashboard | `FR-033` | `webui` | Stream-C | Remove "Dashboard Contract Surface" panel from dashboard. |
| EA-12 | Dashboard | `FR-032` | `webui` | X-1825(CC) | Move "About" out of body content into top nav + login-profile menu. — cross-cutting (recurs on Jobs page per EA-49). |
| EA-13 | Dashboard | `FR-033` | `webui` | Stream-C | Footer `© 2026 Cloud-Dog, Viewdeck Engineering Limited` appears twice — dedup; align to platform UI footer standard. |
| EA-14 | Navigation / Menu | `FR-032` | `webui` | Stream-C | Re-order primary nav: **Experts, Channels, Chat, Sessions, Services, …** |
| EA-15 | Experts | `FR-004` | `webui` | Stream-C | OpenAI-shaped models (e.g. `ibm/granite` on `llm1`) must be addable through the WebUI; no test or example currently e… |
| EA-16 | Experts | `FR-004` | `webui` | Stream-C | Edit / Add Expert: model selection must be a pick-list (not free-text). |
| EA-17 | Experts | `FR-004` | `webui` | Stream-C | Edit / Add Expert: expose key LLM params — Top-K, Temperature, Max Tokens. |
| EA-18 | Experts | `FR-004` | `webui` | Stream-C | System Prompt field is missing from Expert edit — must be present with a default. |
| EA-19 | Experts | `FR-010` | `webui` | X-1825(CC) | **Shared component gap**: `EntityForm` does not support textarea / template-editor fields, so prompt editing falls ba… |
| EA-20 | Experts | `FR-004` | `webui` | Stream-C | Channels, Services, Sub-Experts pickers on Expert form must be **multi-select dropdowns**. |
| EA-21 | Experts | `FR-004` | `webui` | Stream-C | Add a "Test LLM / model" action on Expert form so the user can verify model wiring inline. |
| EA-22 | Experts | `FR-004` | `webui` | Stream-C | "Add Service" must move from in-page box to a pop-up multi-select dialog. |
| EA-23 | Experts | `FR-004` | `webui` | Stream-C | Remove "Expert Contract Service" panel from the page. |
| EA-24 | Experts | `FR-004` | `webui` | Stream-C | Service bindings: zero bindings shown, can't add any — needs the EA-22 multi-select. |
| EA-25 | Experts | `FR-004` | `webui` | Stream-C | "Test Query" must move to a pop-up; improve presentation of `Linked knowledge: 0; total prompt templates available: 3… |
| EA-26 | Experts | `FR-004` | `webui` | Stream-C | "Add Sub-Agent" must move to a pop-up and be reachable from the Add/Edit/View Expert flow. |
| EA-27 | Experts | `FR-004` | `webui` | Stream-C | Providers: surface providers either as a page or as part of Settings; from a provider you must be able to fetch the l… |
| EA-28 | Experts | `FR-004` | `webui` | Stream-C | "View History" for an expert: click-through to the audit/logs page with the expert filter pre-filled. (consistency wi… |
| EA-29 | Channels | `FR-007` | `webui` | Stream-C | Add a "View Channel" action (currently missing). |
| EA-30 | Channels | `FR-007` | `webui` | Stream-C | Add a "View Messages / History" for a channel. |
| EA-31 | Channels | `FR-007` | `webui` | Stream-C | Edit / Add Channel: Expert list is squashed. Channel "type" is locked to chat — must also support transactional / wor… |
| EA-32 | Channels | `FR-007` | `webui` | Stream-C | Remove "Channel Contract Surface" panel (this belongs in the Swagger/OpenAPI docs page). — cross-cutting "Contract Su… |
| EA-33 | Channels | `FR-007` | `webui` | Stream-C | Channel detail must expose history + messages: thinking, responses, timings; ability to test the channel; visibility … |
| EA-34 | Channels | `FR-007` | `webui` | Stream-C | Channel "View History" click-through to audit/logs filtered by channel. (consistency with EA-28). |
| EA-35 | Chat | `FR-013` | `webui` | Stream-C | Remove Sessions / Channels / Experts / Tool-calls boxes at the top of the page. |
| EA-36 | Chat | `FR-013` | `webui` | Stream-C | Conversation Workbench is the main feature — must be **full width / main prominence**. Below it: chat history. New se… |
| EA-37 | Chat | `FR-013` | `webui` | Stream-C | From `/chat` you must be able to jump to the Expert page and the Knowledge page; on selecting an Expert / Knowledge, … |
| EA-38 | Chat | `FR-013` | `webui` | Stream-C | Message timeline layout: user labels on the **right**, assistant (expert name) on the **left**; user label = the logg… |
| EA-39 | Chat | `FR-013` | `webui` | Stream-C | While "Latest Response" is in flight, show a ticking clock / in-progress indicator against the request; surface the j… |
| EA-40 | Chat | `FR-013` | `webui` | Stream-C | "Tool Calls: 0" tile looks wrong — drive from real data. |
| EA-41 | Chat | `FR-013` | `webui` | Stream-C | Tool-call panel currently just copies the request — replace with a per-message icon that opens the tool-call detail o… |
| EA-42 | Chat | `FR-013` | `webui` | Stream-C | Remove "Session snapshot" from `/chat` — this content belongs on `/sessions`. |
| EA-43 | Chat | `FR-013` | `webui` | Stream-C | Remove "Chat contract surface" panel. (consistency with EA-32 cross-cutting). |
| EA-44 | Sessions | `FR-013` | `webui` | Stream-C | "View Timeline" must navigate to `/chat` with the right Expert + Knowledge + Session selected and history loaded. |
| EA-45 | Sessions | `FR-013` | `webui` | Stream-C | Remove "Session / Active / Exports" blocks and "Session contract surface". |
| EA-46 | Sessions | `FR-013` | `webui` | Stream-C | Remove per-row "Detail" — "View Messages" should take you to `/chat`. |
| EA-47 | Sessions | `FR-013` | `webui` | Stream-C | Session "View History" click-through to audit/logs filtered by session. |
| EA-48 | Knowledge | `FR-027` | `webui` | Stream-C | Remove the `Entries 181 / Linked experts / Scopes` summary strip. |
| EA-49 | Knowledge | `FR-027` | `webui` | Stream-C | Clarify Knowledge ID semantics — currently shows `1`; should be a GUID. |
| EA-50 | Knowledge | `FR-027` | `webui` | Stream-C | Bottom-of-screen "linked experts" pick box is not relevant — remove. |
| EA-51 | Knowledge | `FR-027` | `webui` | Stream-C | Edit/Add Knowledge missing: knowledge type (chroma, qdrant, …), knowledge parameters, ingest parameters, lifecycle pa… |
| EA-52 | Knowledge | `FR-027` | `webui` | Stream-C | Ability to select + import / reuse an existing knowledge from one of the sources. |
| EA-53 | Knowledge | `FR-027` | `webui` | Stream-C | Remove "Knowledge contract surface". |
| EA-54 | Knowledge | `FR-027` | `webui` | Stream-C | Knowledge admin page: prune, view all collections, remove items, select + search for entities, kick off index/upload,… |
| EA-55 | Knowledge | `FR-027` | `webui` | Stream-C | Knowledge "View History" click-through to audit/logs filtered by knowledge. |
| EA-56 | Knowledge | `FR-027` | `webui` | Stream-C | Knowledge list: expose type + size columns. |
| EA-57 | Services | `FR-011` | `webui` | Stream-C | Remove `Services 69 / Healthy 15 / Bound experts` summary strip. |
| EA-58 | Services | `FR-011` | `webui` | Stream-C | On page load, async-run a health check against each service; show enabled/disabled toggle per service; green / red si… |
| EA-59 | Services | `FR-011` | `webui` | Stream-C | Per-row "Detail" currently does nothing — wire it. |
| EA-60 | Services | `FR-011` | `webui` | Stream-C | Edit Service: Service Type must be a pick-list. |
| EA-61 | Services | `FR-011` | `webui` | Stream-C | Edit Service: Endpoint URL must be testable once well-formed; once tested, auto-detect endpoint type. |
| EA-62 | Services | `FR-011` | `webui` | Stream-C | Edit Service: improve Auth Config JSON UX — add Bearer / `X-API-Token` / other presets. |
| EA-63 | Services | `FR-011` | `webui` | Stream-C | Improve Metadata JSON UX (cross-links existing CC-18 schema-aware editor). |
| EA-64 | Services | `FR-011` | `webui` | Stream-C | Remove nonsense "Available Experts" block from the bottom of Register Service. |
| EA-65 | Services | `FR-011` | `webui` | Stream-C | Add other settings to Service: tools available, RBAC (who can use it). |
| EA-66 | Services | `FR-011` | `webui` | Stream-C | Health Check / Response should be a pop-up, not in-page. |
| EA-67 | Services | `FR-011` | `webui` | Stream-C | Remove "Service composition contract surface". |
| EA-68 | Services | `FR-011` | `webui` | Stream-C | Service "View History" click-through to logs filtered by service. |
| EA-69 | Files | `FR-026` | `webui` | Stream-C | Replace flat list with a file-tree UI widget. **Re-use the folder/file layout + functionality from file-mcp** (`cloud… |
| EA-70 | Files | `FR-026` | `webui` | Stream-C | Buttons layout is poor — align to platform UI standards. |
| EA-71 | Files | `FR-026` | `webui` | Stream-C | Remove "Files Storage Objects" panel. |
| EA-72 | Files | `FR-026` | `webui` | Stream-C | Storage Bytes tile reads `0` — wire to real storage usage. |
| EA-73 | Files | `FR-026` | `webui` | Stream-C | Show what + where the storage is (URI). |
| EA-74 | Files | `FR-026` | `webui` | Stream-C | Metadata: pop-up + friendly display (not raw JSON); remove metadata sub-panel. |
| EA-75 | Files | `FR-026` | `webui` | Stream-C | Ingest flow: Knowledge picker must be a pick-list; expose ingest options (how, parameters, model). |
| EA-76 | Files | `FR-026` | `webui` | Stream-C | Knowledge ingest must run as an async Job; File row must show "pending import" status; Knowledge screen must show "pe… |
| EA-77 | Files | `FR-026` | `webui` | Stream-C | "Ingest file" pop-up layout (with stray "selected file" at bottom) needs total redesign. |
| EA-78 | Files | `FR-026` | `webui` | Stream-C | Add a File viewer (click to view). |
| EA-79 | Files | `FR-026` | `webui` | Stream-C | Add folder navigation. |
| EA-80 | Files | `FR-026` | `webui` | Stream-C | File times must use Moment format (cross-links existing CC-08). |
| EA-81 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Tightly couple Prompts to Experts: use/add/see prompts related to experts; click a prompt → jump to expert(s) that us… |
| EA-82 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Remove `Templates 42 / Generated cases 0 / Validation score N/A / Prompt valid` strip. |
| EA-83 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Move Prompt Workbench to the bottom of the screen; generation only meaningful with a context (expert and/or knowledge). |
| EA-84 | Admin — Prompts | `FR-010` | `webui` | Stream-C | "Validate Prompt" does nothing; "Generate test cases" has no context input — needs a context form (expert type, outco… |
| EA-85 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Create Prompt: same `EntityForm` multiline gap as EA-19 — fix in `cloud-dog-ai-ui-monorepo`. |
| EA-86 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Edit Prompt: provide easy insertion of available variables (driven by context). |
| EA-87 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Redesign prompt-engineering workflow: given Channel + Expert + Knowledge + description + outcomes, LLM should generat… |
| EA-88 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Clarify "Updated" column semantics. |
| EA-89 | Admin — Prompts | `FR-010` | `webui` | Stream-C | "Generated test cases" possibly needs its own page once context model lands. |
| EA-90 | Admin — Prompts | `FR-010` | `webui` | Stream-C | Remove "Prompt preview" until redesign is in place; remove "Prompt contract surface". |
| EA-91 | Jobs | `FR-018` | `webui` | Stream-B/C | Started and Duration columns have no values. (depends on PS-76 + EA-01). |
| EA-92 | Jobs | `FR-018` | `webui` | Stream-B/C | Action buttons don't match other pages' UI — apply platform standards. |
| EA-93 | Jobs | `FR-018` | `webui` | Stream-B/C | Job Detail: Status / Layout don't match design standards; Submitted By should be user-or-interface; created/started/f… |
| EA-94 | Jobs | `FR-018` | `webui` | Stream-B/C | Add a Resubmit button on Job Detail. |
| EA-95 | Jobs | `FR-009` | `webui` | Stream-B | Expert Agent currently reports zero job failures — implausible; verify failure recording is wired. |
| EA-96 | Jobs | `FR-018` | `webui` | Stream-B/C | Job Id is rendered as a blue box — use platform link/identifier style. |
| EA-97 | Jobs | `FR-018` | `webui` | Stream-B/C | Remove "Job contract surface" panel. |
| EA-98 | Jobs | `FR-018` | `webui` | Stream-B/C | "About" appears at the bottom of `/jobs` (3rd time noted, still not fixed across services). — cross-cutting (consiste… |
| EA-99 | Admin — Users | `FR-029` | `webui` | Stream-C | Create/Edit User screen must allow add/remove of Available Group. (cross-links existing CC-13). |
| EA-100 | Admin — Users | `FR-029` | `webui` | Stream-C | Enable/Disable button not to platform standards — see EA-31 / consistent status pattern. |
| EA-101 | Admin — Users | `FR-029` | `webui` | Stream-C | Remove "User contract surface". |
| EA-102 | Admin — Users | `FR-029` | `webui` | Stream-C | Add an Add-API-Key / Change-API-Key screen on User. (cross-links existing CC-15). |
| EA-103 | Admin — Groups | `FR-019` | `webui` | Stream-C | Remove `Groups / Enabled / Members in Selection` summary strip. |
| EA-104 | Admin — Groups | `FR-019` | `webui` | Stream-C | Edit/Create Group: CRUD on users (select + add + remove). (cross-links existing CC-14). |
| EA-105 | Admin — Groups | `FR-019` | `webui` | Stream-C | From Group, ability to add a new user (taken to user screen). |
| EA-106 | Admin — API Keys | `FR-012` | `webui` | Stream-C | API Key detail MUST show associated users / groups. |
| EA-107 | Admin — API Keys | `FR-012` | `webui` | Stream-C | Create Key: must allow selecting + adding users / groups, and surface them on detail. (cross-links existing CC-15). |
| EA-108 | Admin — API Keys | `FR-012` | `webui` | Stream-C | Roles list in API Keys is very short — confirm whether the full set is exposed. |
| EA-109 | Admin — API Keys | `FR-012` | `webui` | Stream-C | Expiry shows "30 days" header but every row has no expiry — wire correctly. |
| EA-110 | Admin — API Keys | `FR-012` | `webui` | Stream-C | Remove "API key contract surface". |
| EA-111 | Admin — API Keys | `FR-012` | `webui` | X-1825(CC) | Shared `IdamApiKeysPage` `Number(form.owner)` bug breaks string-id API-key create for all 9 services — fix in the sha… |
| EA-112 | Admin — RBAC | `FR-030` | `webui` | Stream-C | Page layout broken — one row should be `User-or-Group + type + Role definition + bind action`. (cross-links existing … |
| EA-113 | Admin — RBAC | `FR-030` | `webui` | Stream-C | "View Permissions" must be a pop-up, not a side panel. |
| EA-114 | Admin — RBAC | `FR-030` | `webui` | Stream-C | **CRITICAL** — bindings to Expert / Channel / Knowledge are entirely missing. RBAC must support these resource bindings. |
| EA-115 | Admin — RBAC | `FR-030` | `webui` | Stream-C | Clarify or remove "Group role overview" tacked on at the end. |
| EA-116 | Admin — RBAC | `FR-030` | `webui` | Stream-C | Rethink the whole RBAC layout against the canonical platform RBAC standard. |
| EA-117 | Admin — Monitoring | `CS-009` | `webui` | Stream-C | Page is non-functional (403) — bring into line with other services' monitoring page. Must allow selecting user / expe… |
| EA-118 | Admin — Monitoring | `FR-033` | `webui` | Stream-C | Remove "Monitoring contract surface". |
| EA-119 | API Docs | `FR-031` | `webui` | Stream-C | Page is broken / full of errors — must be consistent across all 9 projects per the guidance already given. (cross-lin… |
| EA-120 | API Docs | `FR-031` | `webui` | X-1825(CC) | Display all environment-variable settings in the API Docs section. **Apply across all 9 projects.** — cross-cutting C… |
| EA-121 | Testing | `FR-016` | `webui` | Stream-C | Functionality is covered by `/chat` — remove the page. |
| EA-122 | MCP Console | `FR-031` | `mcp` | Stream-C | Apply the same standard as file-mcp / other services: when a tool is selected, show a JSON template auto-filled from … |
| EA-123 | A2A Console | `FR-031` | `a2a` | Stream-C | Apply same feedback as other A2A consoles: list topics, prefill template with agent-card data, allow trial run. Remov… |
| EA-124 | Admin — Settings | `FR-032` | `webui` | Stream-C | Responses must be structured, not raw JSON. (PS-73 standard accepted W28K-1404e; adoption pending). |
| EA-125 | Admin landing | `CS-009` | `webui` | Stream-C | Page is blank/rubbish: `Request Health status: N/A`, `Queue depth: N/A failed with status 403` — fix data wiring and … |
| EA-126 | Admin landing | `FR-032` | `webui` | Stream-C | Add About entry to the LHS menu — make consistent across services per platform standard (cross-links EA-12). |
| EA-127 | Admin landing | `FR-032` | `webui` | Stream-C | Admin must surface Channels + Sub-agents + Services obviously connected (each sub-agent has a prompt and ties to a ch… |
| EA-128 | Profile menu / brand | `FR-029` | `webui` | Stream-C | Profile pop-up: add reset / change password; add select-through to Expert / Channel / Sessions, etc. |
| EA-129 | Profile menu / brand | `FR-029` | `webui` | Stream-C | Service name typography fix: `expert agent` → `Expert Agent` everywhere (consistency with EA-02). |

> Trace provenance: GarysWorkingNotes Expert Agent WebUI Feedback Capture (operator source; read-only). Stream-C lanes close each EA item with an exact Playwright assertion per PS-WEBUI-STYLE-COMPONENTS WSC-017; this Stream-A trace establishes the requirement binding and owning stream only.

