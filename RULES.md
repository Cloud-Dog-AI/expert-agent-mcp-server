---
template-id: T-RUL
template-version: 1.0
applies-to: RULES.md
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

# expert-agent-mcp-server — RULES.md

## Common Rules

This project follows the [Cloud-Dog AI Platform Common Rules](../cloud-dog-ai-platform-standards/RULES.md) v2.7+.
Common rules are NOT restated here; consult central for: integrity (§1), environment+config (§2),
server+process management (§3), code+change management (§4), testing (§5), documentation (§6),
repo structure (§7), operational controls (§8), security boundaries (§9), infrastructure
protection (§10), Vault path verification (§11), implementation truthfulness (§12),
sandbox dispatch preconditions (§13, W28A-882 Phase F), completion standards (§14), mandatory reading (§15).

Cross-references for topics that previously lived locally:
- Multi-provider LLM testing methodology — see central AGENT-LESSONS.md §6.106.
- `cloud_dog_llm` pinning and provider abstraction — see central AGENT-LESSONS.md §6.107 and central RULES.md §1.4 / §1.7.

## Project-Specific Rules

### Verified Port Assignments

Four-server architecture (all servers MUST be controlled via `server_control.sh`):

| Role | Port | Purpose |
|------|------|---------|
| API Server | `8030` | REST API for session/expert/knowledge operations |
| Web UI Server | `8031` | Browser-based management interface |
| MCP Server | `8032` | Model Context Protocol interface (stdio or HTTP/SSE) |
| A2A Server | `8033` | Agent-to-Agent communication |

Ports verified against [tests/env-ST](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/tests/env-ST).
Reserved infrastructure ports `8080-8083` MUST NOT be used by this project.

Important: [defaults.yaml](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/defaults.yaml) still carries
legacy `8083/8080/8081/8082` values. For test/runtime truth, use the explicit env file in force for the tier
you are running.

### Vector-DB Subsystem Credential Files

Each vector DB subsystem has its own env file pair (per-subsystem isolation, beyond the central Vault pattern):

| Subsystem | Config | Secrets |
|-----------|--------|---------|
| PGVector | `private/env-test-pgvector` | `private/env-test-pgvector-secrets` |
| Chroma | `private/env-test-chroma` | `private/env-test-chroma-secrets` |
| Qdrant | `private/env-test-qdrant` | `private/env-test-qdrant-secrets` |
| OpenSearch | `private/env-test-opensearch` | `private/env-test-opensearch-secrets` |
| Weaviate | `private/env-test-weaviate` | `private/env-test-weaviate-secrets` |

- All `*-secrets` files are gitignored and MUST NOT be committed.
- `docs/TESTS.md` MUST list all credential file locations for each subsystem.
- Chat-supplied credentials must be saved directly to `private/` without echoing in responses.

Standard test env files (committed, non-secret):
- `tests/env-UT` — unit test config
- `tests/env-ST` — system test config
- `tests/env-IT` — integration test config
- `tests/env-AT` — application test config

### LLM Client Module

- **ALWAYS** use: `from src.common.llm_client import get_llm_client`.
- **NEVER** create `httpx.AsyncClient` directly for LLM operations.
- **NEVER** hardcode base URLs, models, API keys, or timeouts.
- ALL LLM configuration MUST come from the config system.
- LLM conversations can take 5+ minutes — use `asyncio.wait_for()` with 480s default timeout.
- Multi-provider testing methodology lives at central AGENT-LESSONS.md §6.106 (do not re-implement locally).

### External Service Interfaces (Single Entry Points)

| External Service | Single Entry Point | Direct calls forbidden |
|-----------------|-------------------|----------------------|
| LLM | `src/common/llm_client.py` | No direct httpx/Ollama/OpenAI calls |
| Database | Database service layer | No direct SQL from business logic |
| Vector stores | Vector store providers | No direct Chroma/Qdrant/etc. client calls from business logic |

### API Endpoints

**Read-only endpoints (for status checks):**
- `GET /health` — server health (public, no auth)
- `GET /status` — queue depth, system status (requires API key)
- `GET /llm/status` — LLM queue status (requires API key)
- `GET /sessions/{id}` — session details (requires API key)
- `GET /sessions/{id}/history` — conversation history (requires API key)
- `GET /experts` — list expert configurations (requires API key)
- `GET /knowledge` — knowledge base entries (requires API key)

**Write endpoints (NEVER use for status checks):**
- `POST /sessions` — creates sessions
- `POST /sessions/{id}/end` — ends sessions
- `POST /knowledge` — creates knowledge base entries
- `DELETE /sessions/{id}` — deletes sessions
- `DELETE /knowledge/{id}` — deletes knowledge entries

Authentication: `X-API-Key` header, from `CLOUD_DOG__EXPERT__API_KEY` env var.

### Session Management

- Verify session creation: check 201 status, store session ID/GUID.
- Wait for session initialization before sending messages.
- State transitions: `initializing` → `active` → `ended`.

### MCP Tools

Available MCP tools (accessed via MCP protocol only, never bypass to API directly):
- `chat`, `start_session`, `resume_session`, `end_session`
- `list_sessions`, `get_session_status`, `get_session_history`

### Vector Database Rules

- Vector DB queries can be slow (5-30 seconds) — use appropriate timeouts.
- Verify connection before operations.
- Supported stores: Chroma, Weaviate, Qdrant, OpenSearch, Elastic, PGVector.
- Collection-based separation for groups (data isolation).
- Knowledge base lifecycle: purge, compress, consolidate.
- Qdrant integration: requires a live Qdrant service for AT1.17b — API-only fixtures FAIL the test (see Incident Record 7.1).

### Expert Configuration Rules

- Each expert has its own LLM provider, model, and parameters.
- Expert configurations control access via groups/users.
- Changes to expert configs affect ALL sessions using that expert — test first.
- Default expert: `_DEFAULT_` (configurable).
- **NEVER** modify LLM prompts, expert configurations, or user/group preferences without testing.

### Data Management

- **NEVER** delete sessions, conversations, or knowledge base data via direct database access.
- Use API endpoints: `DELETE /sessions/{id}`, `DELETE /knowledge/{id}`.
- Use cleanup scripts: `scripts/cleanup_stuck_sessions.py`.

### Standing Approval

- If user grants standing approval for fixes/retests, proceed without per-change approval but still provide a plan.
- Standing approval scope: fixes in `src/` and `tests/` aligned to agreed requirements, architecture, or tracked test failures.

### Docker Build Command (Mandatory)

- Docker images MUST be built via `bash docker-build.sh` from repository root.
- `docker-build.sh` is the project entrypoint and delegates to `scripts/docker-build.sh`.
- The delegated script enforces the standard build flow including default `--network=host` and optional `--custom-ca` handling.
- Direct ad-hoc `docker build ...` commands are forbidden for project build/closeout evidence.

### Testing Rules (Project-Specific Extensions)

Platform testing rules (central RULES.md §5) apply in full. The rules below are project-specific extensions.

#### AT Architecture Rule (API-Only)

**ALL Application Tests MUST use ONLY the host server API — NO direct service calls.**

**FORBIDDEN in AT tests:**
- Direct database access: `get_db()`, `db.query()`, direct model queries.
- Direct manager calls: `SessionManager()`, `ExpertManager()`, `VectorStoreManager()`, etc.
- Direct provider calls: `ChromaProvider()`, `QdrantProvider()`, `OpenSearchProvider()`, etc.
- Direct vector store client connections.
- Direct SQL queries outside API endpoints.

**REQUIRED in AT tests:**
- ALL operations via `api_client` (TestClient).
- ALL CRUD via API endpoints.
- ALL data retrieval via `GET /resource/{id}` endpoints.
- ALL cleanup via `DELETE /resource/{id}` endpoints.

**Allowed exceptions:** DB initialisation in fixtures (`init_db()`, `Base.metadata.create_all()`), configuration access (`get_config()`), test utilities with no service dependencies.

#### Service Availability

- Required services: use `pytest.fail()` if unavailable (NOT `pytest.skip()`).
- Optional services: use `pytest.skip()` if unavailable.
- Verify real vector DB connections before operations (Chroma, Qdrant, OpenSearch, Weaviate, PGVector).
- Verify LLM provider is accessible before LLM tests.

#### Test Output Structure

AT test outputs saved to `working/AT{X.Y}_TEST_OUTPUTS/{test_name}/` with subdirectories:
`inputs/`, `outputs/`, `validations/`, `llm_operations/`, `vdb_operations/`.

#### Test Tracking

- Enumerate exact test IDs from `docs/TESTS.md` when planning scenarios.
- Record results back into `docs/TESTS.md` and `CONTEXT-SUMMARY.md`.
- Maintain test-to-env mapping in `docs/TESTS.md`.

## Incident Records

### 7.1 Vector DB Test Misrepresentation (2025-12-23)

**Issue:** Agent claimed AT1.17b/c/d/e (Qdrant, OpenSearch, PGVector, Weaviate) PASSED when they only tested API/database layer — no real vector DB connections were made.

| Test | Claimed | Actual | Reality |
|------|---------|--------|---------|
| AT1.17b | PASSED | FAILED | No Qdrant service — API-only |
| AT1.17c | PASSED | FAILED | No OpenSearch service — API-only |
| AT1.17d | PASSED | FAILED | No PGVector service — API-only |
| AT1.17e | PASSED | FAILED | No Weaviate service — API-only |

**Root cause:** Tests created database config records but did not connect to real vector DBs, perform real operations, or verify real functionality.

**Rules added:** Platform RULES.md §12 (Implementation Truthfulness). AT tests MUST verify real external service connectivity before claiming PASS.
