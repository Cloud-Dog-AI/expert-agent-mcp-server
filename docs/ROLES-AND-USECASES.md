---
template-id: T-RUC
template-version: 1.0
applies-to: docs/ROLES-AND-USECASES.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: expert-agent-mcp-server
doc-last-updated: 2026-06-21
doc-git-commit: 23792217e632a149847f4be56af53e9b6b744c14
doc-git-branch: main
doc-source-shas: []
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-21T00:00:00Z
---

# expert-agent-mcp-server — ROLES-AND-USECASES

> **Template:** T-RUC v1.1 (PS-REQ-TEST-TRACE §3.5). Canonical use-case inventory authored by W28E-1809A. UC-NNN ids are the immutable canonical use cases; each maps to one or more `FR-NNN`/`CS-NNN` across the api/mcp/a2a/webui surfaces. Use-case binding is proven transitively through the bound FR/CS tests (UC markers are intentionally not added to the traceability-enforced FR/CS set).

## 1. Roles
Canonical roles from PS-83-canonical-role-catalog.md plus project extensions.

| Role | From | Notes |
|---|---|---|
| admin | platform | full administrative access across all surfaces |
| group-admin | platform | manages users/memberships/keys/channels within owned groups |
| read-write | platform | create/update channels, sessions, knowledge, files within permission |
| read-only | platform | read channels/logs/history/knowledge; writes denied (403) |
| anon | platform | unauthenticated; all protected operations denied (401) |
| system | local | internal automation actor (job worker, scheduler, logging) |
| developer | local | API/MCP/A2A consumer integrating expert capabilities |

## 2. Personas
| Persona | Description | Roles |
|---|---|---|
| Administrator | Platform operator managing experts, users, groups, jobs and config | admin |
| Group Admin | Owns a group; manages its users, keys, channels and analytics | group-admin |
| Knowledge User | Creates/uses experts, channels, sessions and knowledge | read-write |
| Read-only Analyst | Reads conversations, logs and history; cannot mutate | read-only |
| Developer / Agentic Flow | Integrates via API/MCP/A2A with credentials | developer, system |
| Anonymous | Unauthenticated visitor | anon |

## 3. Use cases
Canonical inventory UC-001..UC-033 (one row per persona+goal). Surfaces: REST(api)/MCP/A2A/WEBUI.

| UC ID | Persona | Goal | Surface | Requirements | Tests |
|---|---|---|---|---|---|
| `UC-001` | user | Start a conversation with an expert and get context-aware responses. | REST, MCP, A2A | `FR-013`, `FR-004` | AT1.12_MultiTurnConversation, IT2.5 |
| `UC-002` | user | Access knowledge-base context during a conversation (RAG). | REST, MCP | `FR-027`, `FR-022` | AT1.58_ChannelChatVectorStoreRAG, AT1.17_VectorStoreManagement |
| `UC-003` | admin | Manage expert configurations (LLM settings, prompts, access control). | REST, WEBUI | `FR-004` | AT1.16_ExpertConfigManagement, IT2.4 |
| `UC-004` | admin | Manage user preferences (language, timezone, access permissions). | REST, WEBUI | `FR-029`, `FR-039` | AT1.15_*, IT2.x |
| `UC-005` | admin | Monitor system health, metrics and performance. | REST, WEBUI | `FR-033` | ST1.42_DockerSingleContainerSmoke, monitoring AT |
| `UC-006` | user | Run an agentic flow against a channel-based expert with per-channel LLM, history limits, vector knowledge, rerank and tool/sub-agent calls. | MCP, A2A, REST | `FR-007`, `FR-013`, `FR-022` | AT1.58/59/60_ChannelChat*, IT2.41_TransactionalOrchestration |
| `UC-007` | user | Send/receive multimedia (image/audio/video) in expert conversations. | REST, MCP | `FR-008` | AT multimedia, IT file ingest |
| `UC-008` | system | Record each session and every LLM/Expert call as a full job/call record (prompts, responses, metadata, metrics). | internal | `FR-009`, `FR-002` | UT job logging, IT2.26_LogHistoryExport |
| `UC-009` | user | Provide an expert description and have the system auto-generate an example prompt and settings. | REST, WEBUI | `FR-010` | AT prompt generation, IT2.30_PromptTestGeneration |
| `UC-010` | user | Add a tool/external A2A or MCP service, verify it responds, apply it to channels and evaluate the prompt. | REST, MCP, WEBUI | `FR-011` | UT1.96_ServiceComposition, AT services |
| `UC-011` | group-admin | Manage group users and define API keys granting read/write to channels, logs and histories. | REST, WEBUI | `FR-012`, `FR-029` | AT1.99_GroupAdminRoleManagement, IT2.24_APIKeyCrossInterface |
| `UC-012` | user | Create Ollama- and OpenAI-compatible experts/channels via an OpenRouter endpoint. | REST, WEBUI | `FR-021`, `FR-004` | AT1.101_LLMValidationTesting |
| `UC-013` | user | Pick an external MCP/A2A service from a known list, apply access rights and add it to permitted channels. | REST, MCP, A2A | `FR-011` | UT1.137_ServiceCreateEnabled, AT services |
| `UC-014` | read-only | See, search and download all log history and job/call outputs the actor is allowed to access. | REST, WEBUI | `FR-014` | ST1.33_LogSearchExport, IT2.26_LogHistoryExport |
| `UC-015` | user | Extend channel configuration and access from the WebUI within permission. | WEBUI | `FR-015`, `FR-007` | IT2.22_WebUITestingInterface, AT channels |
| `UC-016` | user | Run tests on interfaces/experts/calls from the WebUI, adding content to try each expert. | WEBUI | `FR-016` | IT2.22_WebUITestingInterface |
| `UC-017` | group-admin | See usage/success/cost statistics per expert channel. | REST, WEBUI | `FR-017` | IT2.23_AnalyticsAggregation |
| `UC-018` | developer | Access all endpoints with correct authentication via the API. | REST | `FR-031` | IT API coverage, AT1.1_UserAuth |
| `UC-019` | system | Call an expert with correct credentials via MCP or API as an external agentic flow. | MCP, A2A, REST | `FR-031` | AT1.11_MCPToolWorkflows, UT1.36_A2ACardMount |
| `UC-020` | system | Manage all requests/jobs in a queue supporting CRUD from authenticated users/interfaces. | REST, MCP | `FR-018` | ST1.35_QueueCRUDEndpoints, IT queue |
| `UC-021` | admin | Create groups and assign group-admin users so group admins manage their groups independently. | REST, WEBUI | `FR-019` | AT1.99_GroupAdminRoleManagement, IT2.29_GroupAdminCrossService |
| `UC-022` | group-admin | Create a channel/expert with scope, tools and history preferences. | REST, WEBUI | `FR-007`, `FR-011` | AT channels, UT1.98_TransactionalExecution |
| `UC-023` | group-admin | Run a short LLM validation test before deploying a channel. | REST, WEBUI | `FR-021` | AT1.101_LLMValidationTesting, ST1.38_LLMValidationRunner |
| `UC-024` | group-admin | Create and manage API keys with specific access scopes. | REST, WEBUI | `FR-012` | IT2.24_APIKeyCrossInterface, UT1.135_OutboundServiceCredentials |
| `UC-025` | user | Be a member of multiple groups with access to multiple channels. | REST, WEBUI | `FR-029`, `FR-030` | AT1.15_*, RBAC IT |
| `UC-026` | user | Manage knowledge history on user/group/session basis with permissions. | REST, WEBUI | `FR-024` | ST1.40_KnowledgeHistoryCRUD, UT1.93_KnowledgeVersioning |
| `UC-027` | admin | View, remove, resubmit and stop jobs in the queue. | REST, WEBUI | `FR-025` | ST1.35_QueueCRUDEndpoints, jobs AT |
| `UC-028` | system | Evaluate each job response for quality/confidence and provide feedback. | internal, MCP | `FR-023` | AT1.102_ResponseQualityEvaluation, ST1.39/IT2.32 ResponseQualityScoring |
| `UC-029` | developer | Call a channel via REST with an API key in async and sync modes. | REST | `FR-031` | IT2.20_ChannelRESTAsyncSync |
| `UC-030` | admin | Audit, view, upload, download, delete, translate and ingest files (RAG workflows). | REST, WEBUI | `FR-026` | ST1.46_FileIngestVectorStore, AT files |
| `UC-031` | developer | Run extensive tests against known/test experts to confirm capability. | internal | `FR-038`, `FR-043`, `FR-044`, `FR-045`, `FR-046`, `FR-047` | whole test suite (QT/UT/ST/IT/AT) |
| `UC-032` | developer | Perform all administrative and user actions via API. | REST | `FR-031` | IT API coverage |
| `UC-033` | user | Perform all actions via the Web UI without using the API directly. | WEBUI | `FR-032`, `FR-028` | AT1.126_ForensicWebUIE2E |

## 4. Negative use cases (admin/security)
RBAC/denial flows proving anon-denied (401), wrong-role-denied (403) and missing-param (422) per surface. Each maps to a `CS-NNN` row.

| UC ID | Persona | Attempted | Surface | Expected | Requirements | Test |
|---|---|---|---|---|---|---|
| `UC-101` | anon | Read protected data without authentication. | REST | 401 Unauthorized | `CS-001`, `CS-005` | IT negative (api) |
| `UC-102` | anon | Call an MCP tool without authentication. | MCP | 401 Unauthorized | `CS-006` | IT negative (mcp) |
| `UC-103` | anon | Invoke an A2A task without authentication. | A2A | 401 Unauthorized | `CS-007` | IT negative (a2a) |
| `UC-104` | anon | Reach a protected WebUI page without a session. | WEBUI | 401 / login redirect | `CS-008` | WebUI negative (Stream-C) |
| `UC-105` | read-only | Perform a write/mutation via the API. | REST | 403 Forbidden | `CS-002`, `CS-009` | IT negative (api) |
| `UC-106` | read-only | Perform a write via an MCP tool. | MCP | 403 Forbidden | `CS-010` | IT negative (mcp) |
| `UC-107` | read-write | Perform an admin-only privileged operation. | MCP, REST | 403 Forbidden | `CS-004` | IT negative (rbac) |
| `UC-108` | admin | Submit a request missing a required parameter. | REST | 422 Unprocessable | `CS-003`, `CS-013` | IT negative (validation) |
| `UC-109` | read-only | Reach an admin WebUI surface. | WEBUI | 403 / denied panel | `CS-012` | WebUI negative (Stream-C) |
| `UC-110` | read-only | Perform a write via an A2A task. | A2A | 403 Forbidden | `CS-011` | IT negative (a2a) |

## 5. Cross-references
- [REQUIREMENTS.md](REQUIREMENTS.md) — FR/CS/NF catalogue and WebUI feedback trace
- [TESTS.md](TESTS.md) — 10-column coverage map and TEST-DESIGN rows
- PS-82-access-control-session-test-matrix.md · PS-83-canonical-role-catalog.md

## 6. Project-specific notes
Surface set: **api, mcp, a2a, webui**. Stream-C closes each WebUI use case with Playwright assertions per PS-WEBUI-STYLE-COMPONENTS; Stream-B proves API/MCP/A2A/job behaviour. UC-031 rolls up the per-tier coverage requirements FR-043..FR-047.

<!-- W28C-1710a recovery: full content from archive/2026-06-12/DEMO_USECASES.md (archived sha256=d835cd512a02, 91 lines) -->

## Recovered domain content — `archive/2026-06-12/DEMO_USECASES.md` (91 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/DEMO_USECASES.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# Demo Use Cases (AT1.117)

## Scope
`AT1.117_DemoEnvironmentUseCases` seeds a realistic demo environment and validates:
- desks/groups/users/memberships
- named knowledge experts and channels
- current article acquisition from web RSS
- authenticated Web UI uploads
- persistent knowledge ingest
- military/europe desk conversation flows
- English->Arabic and English->Chinese specialist behavior

## Seeded Groups
- Knowledge Users Group
- European Desk
- Americas Desk
- Far East Desk
- Military Group
- UK Politics

## Seeded Users
- Admin email set to: `operations@example.com`
- Gary user: `gary@example.com`
- Specialists:
  - `military.analyst@example.com`
  - `european.specialist@example.com`
  - `americas.specialist@example.com`
  - `far.east.specialist@example.com`
  - `uk.politics.analyst@example.com`
  - `knowledge.librarian@example.com`

## Knowledge Bases (group-scoped)
- Company Knowledge
- European and Middle East
- Americas
- Far East
- Military
- Uk Politics

## Seeded Experts
- Company Knowledge Expert
- European and Middle East Expert
- Americas Expert
- Far East Expert
- Military Expert
- UK Politics Expert
- English to Arabic Expert
- English to Chinese Expert

## Seeded Channels
- Military Channel
- European Channel
- Arabic Translation Channel
- Chinese Translation Channel

## Web-Sourced Article Sets
- UK Military Ajax programme: 5 items
- European Politics News: 6 items

## Military Group Question Set (6)
1. What are the latest reliability concerns discussed for the UK Ajax programme?
2. Summarize current oversight or accountability themes around Ajax procurement.
3. List two operational risks mentioned in recent Ajax reporting.
4. What timelines or milestones are currently discussed for Ajax vehicles?
5. Give a short briefing for a military desk lead on Ajax status this week.
6. What questions should parliament ask next about Ajax programme readiness?

## Military Group Conversation Flows (3)
1. Situation update -> expand highest risk -> mitigation actions.
2. Risk register -> prioritize top risks -> owner/due-date actions.
3. Recent change summary -> force-planning impact -> executive bullet brief.

## European Group Question Set (6)
1. Summarize top current European political developments in uploaded briefings.
2. What cross-border policy themes are driving EU political debate?
3. Brief current leadership/coalition dynamics from recent items.
4. What near-term political risks are repeatedly mentioned?
5. Provide a concise morning memo for a European desk analyst.
6. What follow-up intelligence tasks should the desk execute today?

## European Group Conversation Flows (3)
1. Headline scan -> deep dive key item -> 30-day implications.
2. Watchlist creation -> urgency ranking -> analyst action checklist.
3. Friction-point summary -> highest policy execution risk -> stakeholder note.

## Translation Specialist Demonstrations
- Translate a seeded Ajax document to Arabic and Chinese.
- Download translated artifacts.
- Re-upload translated files via Web UI.
- Ingest translated content into persistent Company Knowledge scope.
- Validate chat channels return Arabic script (Arabic expert) and CJK script (Chinese expert).


<!-- W28C-1710a recovery: full content from archive/2026-06-12/USE_CASES.md (archived sha256=74de98e95ca5, 16 lines) -->

## Recovered domain content — `archive/2026-06-12/USE_CASES.md` (16 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/USE_CASES.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# Expert Agent Use Cases

## UC-CFG-01 New Expert With Custom LLM And Vector Store

1. Create an admin user and API key with expert-management capability.
2. Create a new expert configuration with model, temperature, prompt, and token limits.
3. Create a channel bound to the new expert.
4. Start a session on the channel and verify the expert responds.
5. Update the expert configuration and confirm later responses reflect the change.
6. Bind a vector store or knowledge source to the expert/channel.
7. Query the expert and verify retrieval-backed behaviour.
8. Delete the session, channel, bindings, expert, and temporary admin assets.

Current status:
- API lifecycle is largely delivered.
- Full MCP/A2A/WebUI parity for expert-admin CRUD is still incomplete.


<!-- W28C-1710b design-delta additions (2026-06-14T18:01:23Z) -->

## Cross-surface UC mappings (W28C-1710b)

Per T-RUC v1.1 + PS-REQ-TEST-TRACE §3.5, every UC-NNN maps to one OR MORE FR-NNN across surfaces.

This service's surface set: **api, mcp, a2a, webui**.

Detailed UC-by-UC operator-review pass + per-FR cross-surface mapping deferred to W28C-1711. The cross-surface declarations are enabled here.

```yaml
# Schema for every UC-NNN (default; operator amends per UC):
surfaces: ['api', 'mcp', 'a2a', 'webui']
roles: [admin, read-write, read-only, anon]
FR-mapping: []  # populated by W28C-1711
```
