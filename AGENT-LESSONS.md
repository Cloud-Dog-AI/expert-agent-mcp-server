---
template-id: T-AGL
template-version: 1.0
applies-to: AGENT-LESSONS.md
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

# Agent Lessons Learned — expert-agent-mcp-server

## Central Programme Lesson Authority

The canonical programme lessons are in `/opt/iac/Development/cloud-dog-ai/cloud-dog-ai-platform-standards/AGENT-LESSONS.md`. This repository file is a service-specific overlay only. If this file conflicts with the central programme file, the central file wins.

Before project work, every agent must read the central `RULES.md`, central `AGENT-LESSONS.md`, `AGENT-BOOTSTRAP-DIRECTIVE.md`, the live `AGENT-DISPATCH-TABLE.md`, the exact lane instruction, and this overlay. Do not copy central rules here; add only service-specific deltas and feed reusable lessons back to the central file.


**Purpose:** Lessons from recent agent work on this service. Read before making changes.

---

## Code

### WebUI
- SettingsPage.tsx is the PS-73 reference implementation (267 LOC, 13/13 compliance). All other services' Settings pages should match its pattern.
- JobsPage.tsx is the PS-76 reference implementation (13/13 compliance with search/filter UI). All other services' Jobs pages should match.
- ApiDocsPage.tsx has tab navigation (API/MCP/A2A) + DocumentViewer for service documentation.
- Badge from @cloud-dog/ui is used for health status display on Settings page.

### IDAM
- W28A-716 scanner found 31 violations (highest of all 9 services): 3 bespoke models (User, Group, APIKey in database/models.py) + 28 RBAC enforcement gaps.
- The bespoke SQLAlchemy models in database/models.py extend cloud_dog_idam domain models with service-specific fields.
- RBACEngine wrapper in core/auth/rbac.py provides has_permission() and has_permission_with_context().

## Test Environment

- Tests require `--env tests/env-UT` flag with cloud_dog_config pytest plugin.
- The service is the most feature-complete of the 9 — use as reference for test patterns.

## Infrastructure

- Ports: API 8030, Web 8031, MCP 8032, A2A 8033.
- Preprod: expertagent0.cloud-dog.net.
- Docker build via docker-build.sh.

## Architecture

- Channel-based chat with LLM integration. Job type: channel_chat.
- Knowledge management with vector DB (Qdrant) integration.
- Multi-provider LLM support via cloud_dog_llm.

## Related Projects

- cloud-dog-ai-ui-monorepo: app at apps/expert-agent/. This is the REFERENCE implementation for PS-73 (Settings), PS-74 (Docs), PS-76 (Jobs).
- cloud_dog_idam: Uses APIKeyManager, RBACEngine, AuditEmitter.
- cloud_dog_jobs: Job type channel_chat with full lifecycle.

---

## W28A-866 Session Persistence Fix Lessons

### Code

- Preprod session failures can be caused by the login POST being challenged before the Web route handler runs, not just by bad cookie attributes.
- For Expert Agent WebUI cookie auth, `POST /web/auth/login` and `POST /web/auth/logout` must remain explicitly reachable even when platform auth wraps POST routes in preprod.
- The stable fix pattern in [`src/servers/web/server.py`](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/src/servers/web/server.py) is:
  - keep proxy-aware cookie settings based on browser-visible request headers
  - use `Domain=<fqdn>`, `Path=/`, `HttpOnly`
  - for HTTPS, use `SameSite=none` and `Secure`
  - centralise login/logout response construction in helper methods
  - add a narrow middleware bypass only for public cookie-auth POST routes
- Do not assume a successful `GET /login` means login is healthy. The decisive preprod check is the actual `POST /web/auth/login` response and whether it returns `200` plus `Set-Cookie`.

### Test Environment

- Local Docker validation is necessary but not sufficient. This bug passed locally and only failed behind preprod routing/auth layers.
- The quickest real proof for this service is a Playwright login plus navigation across:
  - `/`
  - `/admin/users`
  - `/admin/settings`
  - `/admin`
- The pass condition is not just route access. It is:
  - no redirect back to `/login`
  - `expert_web_session` present in browser cookies after each navigation
- Reuse the existing admin bootstrap pattern from `tests/application/AT_WEBUI_E2E/test_webui_e2e.py` for local browser validation rather than inventing a new setup flow.
- For preprod browser validation, use Vault-backed `services.expertagent0.web_username` and `services.expertagent0.web_password`, not local test passwords.

### Infrastructure

- `env-vault` must be sourced with export semantics for scripts that expect inherited environment variables:
  - `set -a && source /opt/iac/Development/cloud-dog-ai/env-vault && set +a`
- The Docker build script can fetch private PyPI credentials from Vault, but only if `VAULT_*` variables are actually exported into the shell environment.
- Docker push mistakes can silently keep preprod on the old image. Tag and push the exact registry path:
  - `docker tag expert-agent-mcp-server:latest registry.cloud-dog.net:443/cloud-dog/expert-agent-mcp-server:latest`
  - `docker push registry.cloud-dog.net:443/cloud-dog/expert-agent-mcp-server:latest`
- Always verify registry and deploy image identity explicitly:
  - local image id
  - registry manifest/config digest
  - Terraform state `docker_container.expertagent0.image`
- A targeted Terraform apply can be a no-op even after a new image is pushed. For this workflow, a forced replace was required to guarantee the new image/container was deployed.
- After forced replace, expect a temporary Traefik `404 page not found` window while routing converges. Do not misdiagnose that transient state as the final application behaviour.

### Architecture

- Expert Agent preprod serves the SPA on the root host with runtime config:
  - `AUTH_MODE = "cookie"`
  - `WEB_API_BASE_URL = "/web/api"`
- Because the SPA uses same-origin cookie auth, preprod correctness depends on both:
  - the browser cookie attributes
  - the public accessibility of `/web/auth/login`
- The direct live diagnostic sequence for this architecture is:
  - `GET /login`
  - `GET /runtime-config.js`
  - `POST /web/auth/login`
  - browser navigation with cookie inspection
- Distinguish edge failures from app failures:
  - Traefik/default router failure shows plain `404 page not found`
  - app-level auth failure shows JSON `401` from `uvicorn`

### Related Projects

- `cloud-dog-api-kit==0.4.1` is required here because the service imports `cloud_dog_api_kit.web.proxy.WebApiProxy`.
- Leaving Expert Agent at `cloud-dog-api-kit>=0.2.4` allows Docker to resolve an older runtime that may not include `cloud_dog_api_kit.web`, causing container startup failure even when the local virtualenv works.
- Keep the API kit version aligned across:
  - `pyproject.toml`
  - `requirements.txt`
  - Dockerfile package install lines

### Process / Reporting

- For preprod auth bugs, prove the root cause with the real endpoint before claiming a cookie fix:
  - capture `POST /web/auth/login` status
  - capture `Set-Cookie`
  - then run Playwright
- If deployment verification behaves unexpectedly, check image provenance before changing code again. In W28A-866 the first deployment failure was caused by pushing the wrong tag, not by a bad code fix.
- Reports for this platform must include first-submission evidence completeness:
  - prime directive
  - reading confirmation
  - file:line references
  - exact deploy/build outputs
  - screenshot hashes
  - full RULES warranty

---

## W28A-876 / W28A-877 Expert WebUI and E2E Lessons

### Code

- `section i` log verification only works reliably when CRUD routes emit searchable audit payloads with the same human identifiers the tests query for. In this service that meant explicit audit data for knowledge titles, channel names, service names, and prompt names.
- `PromptsPage.tsx` must keep action controls uniquely addressable. Duplicating `Preview`, `Validate`, or `Generate test cases` buttons across multiple panels creates strict-mode Playwright ambiguity and makes the page brittle for operators too.
- Prompt inventory should be sorted newest-first by descending `id`. That avoids E2E and operator actions landing on stale templates when names are similar.
- Page-level RBAC hiding is required in addition to backend enforcement. The stable pattern is a shared authz helper consumed across Experts, Channels, Services, Prompts, Files, and Knowledge pages.
- Chat verification needs real timeline and tool-call evidence, not just session metadata. For Expert Agent that required rendering `/sessions/{id}/messages` plus job `call_logs`.
- File ingest flows should use adopted dialogs, not `window.prompt`, because prompt-based flows are weak for validation, usability, and PS-77 alignment.

### Test Environment

- The decisive native E2E command for this work was:
  `E2E_BASE_URL=http://127.0.0.1:28080 E2E_REAL=1 E2E_USERNAME=testuser E2E_PASSWORD=TestPassword123! CI=true npx playwright test --workers=1`
- `--workers=1` matters here because the suite mutates shared runtime state across experts, channels, sessions, files, services, prompts, and logs. Parallel workers would make failures noisy and hard to attribute.
- The 9-section suite is only trustworthy if sections `a-h` create real data that section `i` then finds in logs. If log verification cannot find those names/titles, the defect is usually backend audit emission, not the test.
- Native proof and local Docker proof are both required. Native validates the developer runtime path; Docker validates the packaged runtime that will actually be deployed.
- Keep and parse the Playwright JSON report when exact section counts matter. For W28A-877 the authoritative result came from `/tmp/w28a877-playwright-retries0.json`.

### Infrastructure

- Instruction-local native ports for this run were `28080/28081/28082/28083`, not the project defaults `8031/8032/8033/8030`. Agents must not assume the normal ports during AT/E2E work.
- When the instruction snippet and the real script disagree, trust the actual `server_control.sh` help output. In this repo the valid bulk shutdown form is `stop-all`, not `stop all`.
- Manual starts create cleanup risk. In W28A-877 the web server ended up with a stale PID-file case and required `force-stop web` even though API, MCP, and A2A stopped cleanly via `stop-all`.
- Local Docker validation should use instruction-scoped host ports. Mapping this service to `38080-38083` kept Docker proof isolated from the native stack on `28080-28083`.
- After Terraform replace, preprod can transiently return `404 page not found` while ingress converges. The mandated delayed recheck is what determines final status.

### Architecture

- Expert Agent E2E correctness spans experts, channels, sessions, knowledge, files, services, prompts, and audit logs. The system is only truly testable when those domains expose enough metadata to cross-reference each other.
- Services and experts are coupled operationally. Useful UX and useful tests both require explicit visibility of expert-service bindings, service health, and sub-expert relationships from the admin pages.
- Monitoring/audit is not just an observability extra in this service. If actions from the other pages are not visible there, the product is behaviorally incomplete for operators.
- Many apparent frontend failures in this app are actually backend contract gaps. When UI tests fail, check whether the API surface is returning the data needed for rendering and audit verification before rewriting the page.

### Related Projects

- `cloud-dog-ai-ui-monorepo/apps/expert-agent` and `expert-agent-mcp-server` need to evolve together. Several W28A-877 fixes were cross-repo contract fixes, not isolated frontend issues.
- `@cloud-dog/ui` adoption matters operationally, not just cosmetically. Using the platform `Input`, `DataTable`, and dialog patterns reduced ambiguity and aligned the pages with the wider platform contract.
- `cloud-dog-api-kit==0.4.1` remains a hard runtime dependency because this service imports `WebApiProxy`. Docker and dependency files must stay aligned with that published version.

### Process / Reporting

- For this service, “tests passed” is not enough unless Docker build, local Docker test, registry push, Terraform deploy, preprod health, and cleanup are all verified in the same run.
- Cleanup proof should be explicit. The empty result from `ss -tlnp | grep -E ':(2808[0-3]|3808[0-3])\\b' || true` is the durable evidence that both native and Docker test ranges were cleared.
- Reports should record operational nuances instead of smoothing them over. In W28A-877 the truthful report needed both the initial preprod `404` and the stale-PID `force-stop web` cleanup detail.

---

## W28A-843 / W28A-863 / W28A-874 Cross-Platform Lessons

### Code

#### WebApiProxy — use from_config(), never manual construction
- `cloud_dog_api_kit.web.proxy.WebApiProxy` must be instantiated via `WebApiProxy.from_config(cfg)`, not manual constructor kwargs.
- `from_config()` reads standard keys: `web_server.api_base_url`, `api_server.api_key`, `api_server.api_key_header`, `web_server.verify_tls`, `web_server.proxy_timeout`.
- If your service uses non-standard config keys (e.g. `client_api.base_url`), add the standard keys to `defaults.yaml` alongside the existing ones. Do NOT create a wrapper or adapter — align to the platform keys.

#### `/api-docs` SPA route — serve the shell, do not redirect to `/docs`
- `/api-docs` is the SPA client-side route for API documentation.
- `/docs` is typically captured by FastAPI's built-in Swagger UI handler.
- Redirecting `/api-docs` → `/docs` sends the browser to Swagger UI instead of the SPA.
- The correct fix: register `/api-docs` as an explicit SPA entry route that returns `index.html` (or `_spa_shell()`).
- On expert-agent specifically, the `spa_fallback` catch-all would handle `/api-docs` correctly, but the explicit `@self.app.get("/api-docs")` route intercepts first. Keep the explicit route but serve the SPA shell, not a redirect.

#### Runtime config API_BASE_URL
- On chat-client, `API_BASE_URL` in `runtime-config.js` was set to `__origin + "/api"`. This caused the SPA to make requests to `/api/sessions`, `/api/api/v1/users`, etc. — double-prefixing paths that already include `api/`.
- The fix: set `API_BASE_URL` to just `__origin` (no `/api` suffix). The SPA's API client paths already include the correct prefix.
- Different services have different conventions — check what paths the SPA client actually uses before setting `API_BASE_URL`.

#### MCP protocol path scoping in web proxy
- Web proxy routing must distinguish MCP protocol paths (e.g. `/mcp`, `/messages`, `/mcp/sse`) from API-about-MCP paths (e.g. `/mcp/servers`, `/mcp/servers/health`).
- Previously, `path.startswith("mcp/")` routed ALL mcp-prefixed paths to the MCP server. This broke `/mcp/servers` which is an API endpoint.
- The fix: enumerate exact MCP protocol paths in a set, not a prefix match.

#### Admin API key for RBAC
- Web proxies that call the API server for admin operations (user CRUD, config writes) must inject an admin API key.
- The `client_api.api_key` config maps to "viewer" role. Admin operations require `client_api.admin_api_key` or `api_server.api_key` mapped to "admin" role in the auth key mapping.
- Symptom: user creation returns 403 "Admin permission required" even when logged in as admin via the web UI.

### Test Environment

#### Playwright E2E requires real browser login
- `page.request.post("/auth/login")` makes a fetch-style request that does NOT set cookies in the browser context.
- Use actual form-based login: fill username/password fields, click Submit. This sets cookies properly for subsequent page navigations.
- Without proper cookies, all authenticated pages redirect to login, and screenshots look identical (triggering the dedup check).

#### env-IT vault expressions
- env-IT files contain `${vault.dev.models....}` expressions that fail when `source`d by bash ("bad substitution").
- These resolve at runtime via `cloud_dog_config` when the server starts with `--env tests/env-IT`.
- For Python test scripts that need resolved values, run under `server_control.sh` or set the env vars explicitly.

#### cloud_dog_api_kit package tests
- The api-kit package venv at `packages/backend/platform-api-kit/.venv` needs sibling packages installed: `pip install -e ../platform-logging/ -e ../platform-config/ -e ../platform-idam/`
- Tests require `--env tests/env-UT` flag (cloud_dog_config pytest plugin).
- 3 public functions lacked docstrings (`agent_card`, `submit_task`, `ProxyResponse.ok`) — these are caught by the `test_public_docstrings` quality test.

### Infrastructure

#### Traefik PathPrefix(/api) catches /api-docs
- Many services have a Traefik label `PathPrefix(/api)` at priority 200 that routes to the API server.
- `/api-docs` matches `PathPrefix(/api)` and gets routed to the API server instead of the web server.
- Fix: add an explicit Traefik router `Path(/api-docs)` at priority 250 → web server service.
- This was the root cause for expert-agent and db-mcp `/api-docs` returning JSON errors instead of the SPA.

#### PC23 Docker deployment flow
The full deployment sequence for this service:
1. `bash docker-build.sh --registry registry.cloud-dog.net:443/cloud-dog --tag latest`
2. `docker push registry.cloud-dog.net:443/cloud-dog/expert-agent-mcp-server:latest`
3. `cd "/opt/iac/cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents"`
4. `terraform plan -target=docker_image.expertagent -target=docker_container.expertagent0 -out=plan.tfplan`
5. `terraform apply plan.tfplan`
6. Wait for container health: poll `docker -H server0.viewdeck.com inspect --format='{{.State.Health.Status}}'` until "healthy" (expert-agent takes ~60s)
7. Verify: `curl -sf https://expertagent0.cloud-dog.net/health`
8. 60s stability check: 6 probes at 10s intervals

#### Terraform resource names (from AGENT-LESSONS.md)
- Image: `docker_image.expertagent`
- Container: `docker_container.expertagent0`
- Container hostname: `expertagent0.app.vpc0.cloud-dog.net`
- Preprod URL: `https://expertagent0.cloud-dog.net`

#### expert-agent startup time
- expert-agent takes 50-70 seconds to become healthy after container creation. This is normal — it initialises the LLM, vector DB, and runs Alembic migrations.
- Do not mistake "starting" health status for a failed deployment. Wait for at least 90 seconds before diagnosing.

### Architecture

#### Orchestration Enhancement (W28A-874)
- Expert-agent already has: `ServiceCompositionManager` (external service CRUD + tool discovery + invocation), `DelegationManager` (sub-expert parent-child sessions + loop detection), `TransactionalExecutor` (single-shot execution pipeline), `SessionManager`, `KnowledgeHistoryManager`, `PromptTemplate`.

---

## W28A-88f Backend Test Fix Lessons

### Code

- Vault-backed config blobs may arrive as a JSON string under `payload["data"]["data"]["json"]`, not only as a nested object. Both runtime config loading and pytest bootstrap loading need to `json.loads()` that string form before reading service settings.
- `server_control.sh` must short-circuit `help`, unknown commands, and unknown server names before any slow config/Vault resolution. Otherwise `ST1.6` times out on basic CLI contract checks even though the lifecycle logic is fine.
- MCP admin tool RBAC cannot infer role only from `auth_context.role`. For admin MCP calls that pass a real API key, the front-door RBAC layer must resolve the API key to the backing user role before checking `expert:admin:*`.
- The live venv `cloud_dog_api_kit` transport may lag behind the checked-in platform source. In this repo, `/mcp` tool-call responses needed a repo-local compatibility patch to restore `result.structuredContent` on older transport builds that only emit `content[]`.
- `ST1.26` patches `src.core.job.callbacks.httpx.AsyncClient` directly. If callback delivery goes through a shared client helper instead of that symbol, the tests miss the patch point and fail even though the HTTP logic still works.

### Test Environment

- For this repo, local ST lifecycle must use only `./server_control.sh --env tests/env-ST start-all` and `./server_control.sh --env tests/env-ST stop-all`. Hand-starting `start_*.py` breaks the fail-fast gate and invalidates the run.
- `tests/env-IT` must define explicit `embeddings.*` settings. Falling back only to `llm.*` is not enough for `IT2.6`, because that suite hard-fails when `embeddings.model` is unset even if embedding runtime code can derive a model at execution time.
- W28A-874 extends these with: controller experts (`is_controller`), scenario workflows (ordered step sequences), enhanced prompt variables (`{{available_tools}}`, `{{service:X:tools}}`), context retention modes, cross-session sharing via `context_group_id`.
- The largest new build is the Scenario engine (model + executor + API + WebUI). All other features extend existing infrastructure.
- Requirements are in `docs/REQUIREMENTS.md` (FR-ORCH-01 through FR-ORCH-06).
- Architecture is in `docs/ARCHITECTURE.md` (Section 13.7).
- Use cases are in `docs/USE_CASES_ORCHESTRATION.md` (3 scenarios).

#### Visual UI consistency across 9 services
- W28A-863 audit found: 7/9 services have consistent login, dashboard, settings, docs, MCP console pages. expert-agent and sql-agent had routing/session issues.
- expert-agent's session persistence bug was fixed in W28A-866.
- The `PathPrefix(/api)` Traefik issue caused `/api-docs` to fail on expert-agent and db-mcp — fixed by adding explicit Traefik routers.

### Related Projects

#### Platform standards coverage
- PS-30 through PS-77 are very prescriptive for the standard 10 pages (Dashboard, Users, Groups, API Keys, RBAC, Jobs, Settings, Docs, MCP Console, A2A Console).
- 58 service-specific pages across the 9 apps have NO standards coverage.
- Highest-value standardisation candidates: SearchPanel (4 apps), ProfileManager (4 apps), AuditLogPanel (9 apps), Enhanced JsonExplorer (9 apps).
- Full audit in `cloud-dog-ai-platform-standards/working/W28A-863-UI-COMPONENT-AUDIT.md`.

#### UI monorepo shared packages
- `@cloud-dog/ui` exports ~60+ components. Key patterns: `DataTable`, `EntityDialog`, `JsonBlock`, `DocumentViewer`, `ApiDocsPanel`, `McpConsole`, `FileBrowser`, `FolderTree`.
- `@cloud-dog/shell` provides `ShellLayout`, `TopBar`, `LeftNav`, `DashboardLayout`.
- `@cloud-dog/auth` provides `LoginPage`, `AuthProvider`, `SessionTimeoutProvider`.
- No email/message components exist. No code/diff viewer. No advanced JSON tree explorer.
- Third-party deps are minimal: `lucide-react`, `react-markdown`, `remark-gfm`, `clsx`, `tailwindcss`, `zod`.

#### cloud_dog_api_kit alignment
- v0.4.1 is the current required version across all services.
- `WebApiProxy.from_config(config)` is the standard interface — do not use manual constructor.
- The package venv at `packages/backend/platform-api-kit/.venv` must have sibling packages installed for tests to pass (252 tests, 0 failures when env is correct).

---

## W28A-958 Sweep Recovery Lessons

### Code

#### Shared async HTTP clients matter in this service
- Repeated `httpx.AsyncClient()` creation in long-lived service paths is unsafe under sustained browser and E2E load.
- The stable fix pattern was to centralise shared async client reuse in `src/core/http/client.py` and consume it from:
  - `src/core/service/manager.py`
  - `src/core/service/composition.py`
  - `src/core/job/callbacks.py`
  - server startup and shutdown paths
- If Playwright or AT runs show unexplained local stack death, inspect client lifecycle before blaming the browser suite.

#### Browser E2E sections must be state-independent
- `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` originally depended on earlier sections populating `shared.*` runtime IDs and names.
- The robust pattern for this repo is API-side `ensure*` helpers that can create or rediscover prerequisites on demand:
  - `ensurePrimaryExpert()`
  - `ensurePrimaryChannel()`
  - `ensureAdminChatSession()`
  - `ensureNonAdminSession()`
  - `ensureRegisteredService()`
  - `ensurePromptTemplate()`
- If a browser section only passes after another section has run first, treat that as test design debt and fix the dependency.

#### Monitoring assertions must match emitted contracts, not desired contracts
- For this service, audit entries reliably included expert names, channel names, knowledge titles, service names, and prompt names.
- File operations did not emit the uploaded filename into the queried monitoring surfaces during W28A-958, so asserting on that filename was incorrect.
- When monitoring tests fail, inspect the actual route audit payloads first. Do not invent stronger log guarantees than the current server emits.

#### Group and member browser flows need deterministic hooks
- The groups page needed explicit search and selection stability for member CRUD during live refreshes.
- Deterministic selectors and refresh-aware row handling are mandatory here because the page reloads live data aggressively and stale row handles fail often under Playwright.

#### The testing route is now part of the app contract
- `apps/expert-agent/src/views/TestingPage.tsx` plus route wiring in `App.tsx` and `src/lib/api.ts` are required for current browser coverage.
- Do not remove or rename that route without updating both monorepo Playwright coverage and backend forensic browser tests.

### Test Environment

#### Fresh-stack foreground shards are more reliable than one giant browser run
- The full Playwright suite was functionally recoverable, but the most reliable final proof came from foreground one-shot stack runs per slice and per spec using:
  - `working/w28a-958-run-playwright-foreground-stack.sh`
  - `working/w28a-958-run-playwright.py`
- For this service, that approach is preferable when local exec and session pressure is high or when long-lived background stacks are being externally killed.

#### Exact browser totals can be built from shard logs if each shard is foreground and isolated
- Final browser proof for W28A-958 was assembled from:
  - `a11y`
  - `jobs`
  - `smoke`
  - `ui-review2`
  - `w28a642`
  - `w28a877 a-i`
- This is acceptable only if each shard has its own exact pass count and there is no overlap ambiguity.

#### The service is sensitive to concurrent local noise
- A long-running unrelated Playwright tree from another project (`file-mcp`) materially interfered with expert-agent local browser validation.
- If expert-agent API or web processes are being killed without a traceback, check for other local browser or test workloads before changing code.

#### Use repo-local `working/` logs, not `/tmp`
- For this project sweep, all durable evidence needed to live under `expert-agent-mcp-server/working/`.
- Keeping stack, build, deploy, and browser logs there made later forensic assembly much faster and avoided losing proof from temp files.

### Infrastructure

#### Preprod warm-up can look broken before it is healthy
- After targeted Terraform replace, the public host returned Traefik fallback `404 page not found` while the container health was still `starting`.
- Inside the container the API, MCP, and web surfaces came up on different moments (`8083`, then `8081`, then `8080`).
- For this service, do not treat the first public curl after deploy as final truth. Wait for container health to flip to `healthy`, then re-run public curls.

#### Health progression for this service is real and observable
- The useful verification sequence after deploy is:
  - `docker inspect ... .State.Health`
  - internal curls to `127.0.0.1:8083/health`, `127.0.0.1:8080/`, `127.0.0.1:8081/mcp/health`
  - public curls to `/health`, `/api/health`, `/mcp/health`, and `/`
- That sequence distinguishes container warm-up from ingress misrouting.

#### Targeted Terraform applies are the normal recovery tool here
- The relevant deployment target names are still:
  - `docker_image.expertagent`
  - `docker_container.expertagent0`
- For sweep recovery work, a targeted apply was enough to push the fixed image through and verify preprod without waiting on unrelated workspace churn.

#### Registry push evidence must include the digest
- The authoritative deployment artifact for W28A-958 was:
  - `registry.cloud-dog.net:443/cloud-dog/expert-agent-mcp-server:latest@sha256:8834dd542088b3cf4df66512e912bf2914eac57b96db5dc962795389bc0a38b3`
- Capture the digest from the build and push log immediately. It is faster and less error-prone than reconstructing it later.

### Architecture

#### Expert Agent startup is layered, not atomic
- The container entrypoint starts `server_control.sh`, which in turn brings up API, MCP, web, and A2A surfaces on different timings.
- During startup, one surface may be healthy while another is still absent. This is normal for this service and affects both Docker healthchecks and public ingress behavior.

#### This service’s operator value depends on cross-domain visibility
- Experts, channels, sessions, knowledge, files, services, prompts, and monitoring are not independent product slices here.
- The system is only truly operable when those surfaces expose enough shared identifiers to trace actions across them.
- That is why browser coverage and audit or log coverage in this service must be treated as first-class functional requirements, not optional admin extras.

#### Cache behavior is part of the runtime contract
- `tests/integration/IT_CacheIntegration/test_cache_integration.py` is not just a narrow cache test. It verifies prompt-generation caching, knowledge caching, invalidation, expiry, flush, and stats.
- For this service, cache regressions can look like performance regressions or consistency bugs elsewhere. Keep cache coverage green when touching prompts, knowledge, or context rebuild paths.

### Related Projects

#### The monorepo app and backend move together
- `cloud-dog-ai-ui-monorepo/apps/expert-agent` and `expert-agent-mcp-server` cannot be treated as isolated repos for sweep work.
- Several W28A-958 fixes were contract fixes spanning both sides:
  - route existence
  - data-shape expectations
  - RBAC display behavior
  - monitoring evidence

#### The embedding-manager migration is still a separate active snag
- The sweep confirmed that bespoke embedding code is still referenced from `src/core/vector/providers.py` via `EmbeddingManager`.
- Do not falsely mark expert-agent as fully platform-vdb-adopted while those references remain. Treat that as the split-out `W28A-958a` migration task.

### Process / Reporting

#### Be explicit when a sweep is functionally complete but not adoption-complete
- W28A-958 recovered the service functionally, but the bespoke embedding-manager path was still open.
- The correct report pattern is:
  - claim the validated fixes honestly
  - include exact test, build, and deploy evidence
  - call out the remaining adoption snag explicitly instead of smoothing it over

#### When a failing test reveals a false assumption, fix the assumption first
- The last blocking browser failure in `section i` was not an app crash. It was a test assumption that file names would appear in queried logs.
- For this codebase, many late-stage failures are caused by mismatched assumptions between tests and emitted backend contracts, not by fresh product defects.

#### Exec and session pressure is a real operational constraint in Codex runs
- This workspace can accumulate enough unified exec sessions to make long-lived local runs unreliable.
- Reuse active sessions, prefer one-shot foreground runs, and avoid unnecessary background shells when doing long expert-agent sweeps.

---

## W28A-926b OpenRouter LLM Multi-Model Testing Lessons

> See central AGENT-LESSONS.md §6.106 for the cross-service multi-provider LLM testing methodology and config-precedence override rule.

### Code

#### OpenRouter uses the `openai` provider, not a separate provider
- OpenRouter exposes an OpenAI-compatible API at `https://openrouter.ai/api/v1`.
- To switch from Ollama to OpenRouter, set:
  - `CLOUD_DOG__EXPERT__LLM__PROVIDER=openai`
  - `CLOUD_DOG__EXPERT__LLM__BASE_URL=https://openrouter.ai/api/v1`
  - `CLOUD_DOG__EXPERT__LLM__MODEL=<provider/model-name>` (e.g. `qwen/qwen3.5-27b`, `openai/gpt-5.4`)
  - `CLOUD_DOG__EXPERT__LLM__OPENAI_API_KEY=<key from Vault>`
- No code changes are needed — the `cloud_dog_llm` provider abstraction handles this.

#### Config precedence allows per-run model overrides without modifying env files
- Per RULES.md §2, config precedence is: `os.environ` → env-files → config.yaml → defaults.yaml.
- Exporting `CLOUD_DOG__EXPERT__LLM__*` env vars before starting the service overrides the values in `tests/env-AT` without touching the file.
- This is the correct way to test multiple models sequentially — export overrides, restart service, run tests.
- Do NOT modify `tests/env-AT` to switch models. The env file should remain the project default (currently `ollama` / `qwen3:14b`).

#### Think-mode models require `<think>` block stripping
- Models like `qwen3.5` and `DeepSeek` return `<think>...</think>` blocks containing chain-of-thought reasoning before the actual response.
- Content validation must strip these blocks first:
  ```python
  import re
  text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
  ```
- The existing AT tests in this service handle this automatically — no manual stripping was needed during W28A-926b.

### Test Environment

#### AT subset for LLM validation is 6 specific directories (160 tests)
- The designated AT subset for LLM model validation is:
  ```
  tests/application/AT1.1_UserAuth/
  tests/application/AT1.12_MultiTurnConversation/
  tests/application/AT1.16_ExpertConfigManagement/
  tests/application/AT1.11_MCPToolWorkflows/
  tests/application/AT1.101_LLMValidationTesting/
  tests/application/AT1.102_ResponseQualityEvaluation/
  ```
- This yields exactly 160 collected tests.
- AT1.101 (LLM Validation) and AT1.102 (Response Quality) serve as the LLM smoke tests within the subset.
- Do NOT pick different tests or add extra suites for LLM validation runs.

#### Per-model testing requires fresh service restarts
- Each model must be tested with a clean service restart to ensure the new LLM config is loaded.
- Sequence: stop service → export new model env vars → start service → health check → run AT subset.
- The service picks up LLM config at startup, not dynamically at runtime.

#### server_control.sh for expert-agent does not support `all` argument
- Use individual server names: `stop api`, `start api`, `stop web`, etc.
- The bulk shutdown form is `stop-all` (hyphenated), not `stop all` (space-separated).
- For LLM-only testing, starting just the API server (`start api`) is sufficient — the AT subset tests connect via the API.

#### OpenRouter 402/429 means credit exhaustion — stop immediately
- Do NOT retry 402 (Payment Required) or 429 (Rate Limit) from OpenRouter.
- These indicate account-level credit exhaustion, not transient errors.
- Stop testing, report the error, and wait for credit replenishment.
- During W28A-926b, no 402/429 errors were encountered across all 5 models.

### Infrastructure

#### Vault keys for OpenRouter models follow a consistent pattern
- Vault path: `dev.models.<vault_key>` with subkeys `.base_url`, `.model`, `.api_key`.
- The 5 tested OpenRouter model keys are:
  - `openai_qwen3_5_27b_openrouter` → `qwen/qwen3.5-27b`
  - `openai_qwen3_5_35b_a3b_openrouter` → `qwen/qwen3.5-35b-a3b`
  - `openai_gpt_5_4_openrouter` → `openai/gpt-5.4`
  - `openai_google_gemma_4_31b_it_openrouter` → `google/gemma-4-31b-it`
  - `openai_anthropic_claude_sonnet_4_6_openrouter` → `anthropic/claude-sonnet-4.6`
- Some models also have service-specific suffixed keys (e.g. `_chatclient`, `_expert`, `_notification`) for per-service API key isolation.
- Per RULES.md: NEVER invent Vault paths — query live Vault first.

#### Vault HTTP API for programmatic access
- Vault config blob: `GET https://vault0.cloud-dog.net/v1/cloud_dog_ai/data/config` with `X-Vault-Token` header.
- Response structure: `data.data.json.dev.models.<key>` (KV v2 with nested `json` key).
- The `content` key contains the raw YAML; the `json` key contains the parsed JSON structure.
- The `env-vault` file only sets connection parameters (`VAULT_ADDR`, `VAULT_MOUNT_POINT`, `VAULT_CONFIG_PATH`, `VAULT_TOKEN`) — actual Vault resolution of `${vault.*}` expressions happens at runtime via `cloud_dog_config`.

#### env-vault sourcing requires careful shell semantics
- `set -a; source /opt/iac/Development/cloud-dog-ai/env-vault; set +a` exports variables into the current shell.
- Variables are NOT preserved across separate Bash tool invocations. Each new shell session must re-source env-vault.
- For chained commands in a single shell, source env-vault at the top of each command block.

### Architecture

#### Multi-provider LLM is model-agnostic at the test layer
- All 5 OpenRouter models (Qwen 3.5 27B, Qwen 3.5 35B-A3B, GPT-5.4, Gemma 4 31B, Claude Sonnet 4.6) produced identical 160/160 pass rates.
- This confirms the test design is provider- and model-agnostic — tests validate service behaviour, not model-specific output patterns.
- The ~6-minute test duration was consistent across all models (370-376 seconds), dominated by API round-trips rather than model inference time.

#### OpenRouter serves as the cloud LLM tier alongside local Ollama
- Ollama (`llm1.cloud-dog.net`, `llm2.cloud-dog.net`) provides local/self-hosted inference for development and default AT runs.
- OpenRouter (`openrouter.ai/api/v1`) provides cloud-hosted inference for broader model coverage (GPT, Claude, Gemma, Qwen via cloud).
- Both tiers use the same `cloud_dog_llm` abstraction — the service code is identical, only config changes.

### Related Projects

#### Notification-agent W28A-925 established the OpenRouter testing pattern
- The multi-model LLM test procedure (smoke + AT subset per model, sequential) was first proven on `notification-agent-mcp-server` in W28A-925.
- Expert-agent W28A-926b follows the same pattern: same Vault key structure, same provider override technique, same sequential execution.
- Lessons from one service apply directly to the other — both use `cloud_dog_llm` for provider abstraction.

#### Platform-wide LLM testing covers 12 models across 2 providers
- Ollama (7 models): qwen3:14b, qwen3.5:9b, gemma4:e4b, qwen3.5:27b, granite4:tiny-h, granite4:small-h, gemma4:26b
- OpenRouter (5 models): qwen/qwen3.5-27b, qwen/qwen3.5-35b-a3b, openai/gpt-5.4, google/gemma-4-31b-it, anthropic/claude-sonnet-4.6
- Each service tests the same model list but with its own AT subset tailored to service-specific functionality.

---

## W28A-1000 Matrix Triage Lessons

### Code

- Do not mark a WebUI requirement as implemented when the browser test seeds the state through the API and only verifies visibility afterward. In this repo that was the decisive distinction for `W875-REQ-02`.
- Structural platform-standard requirements can be proven from source delegation, not only by runtime screenshots. For expert-agent, `EndpointTable` and `SimpleTable` delegate to `DataTable`, `CrudEntityDialog` delegates to `EntityDialog`, and `JobsPage` uses `EntityDialog` directly.
- `ACCEPTED-GAP` is the right outcome when the backend capability exists but the WebUI intentionally does not expose a safe editor yet. Do not stretch the requirement wording to hide a missing browser surface.
- Chat/session requirements in this app are intentionally split. `ChatPage` owns live timeline and tool-call evidence; `SessionsPage` owns detail and destructive lifecycle controls. Do not over-merge those responsibilities in the matrix.
- `FilesPage` already has dialog-based ingest target selection, but browser-native upload is still absent even though the shared adapter exposes `FileDropZone`. That is a real gap, not a documentation nuance.

### Test Environment

- When the matrix summary and per-row table disagree, trust live code and test evidence over the stale matrix text. W28A-1000 only reconciled cleanly after checking the UI code and the real Playwright sections.
- Browser evidence must distinguish between browser-executed capability and API-assisted setup. If the browser never performs the bind/unbind action, the WebUI requirement is not covered.
- Structural audits can use grep evidence when combined with concrete source anchors. For this service, a zero-match raw-table grep plus wrapper references was enough to justify `W875-REQ-15`.
- Docs-only triage work should still leave evidence artifacts in `working/`. The useful set here was browser-evidence extraction, zero-match structural grep logs, and a doc diff log.

### Infrastructure

- Check for an active expert-agent runtime before starting forensic docs work, but also inspect the git worktree. A quiet process table does not mean the repo is free of overlapping change risk.
- If the worktree is dirty and the task is docs-only, constrain edits to the documentation files and do not touch runtime code. That is the safe way to respect §6.13 when adjacent expert-agent work may still be in flight.
- Keep triage artifacts named and scoped per instruction in `expert-agent-mcp-server/working/`. They become the durable proof when no test or deploy chain is involved.

### Architecture

- Expert-agent admin behaviour is cross-page by design. Experts, channels, chat, sessions, files, services, and monitoring all contribute to the real operator contract, so single-page requirement wording can be misleading if read too literally.
- Channel binding capability currently exists in the API layer without a matching browser editor. The presence of routes such as channel vector-store/tool/service bindings does not imply that `ChannelsPage` supports them operationally.
- The platform-standard wrappers matter architecturally here because the app relies on shared UI primitives for consistency across a very broad admin surface. Matrix claims about tables and dialogs should be anchored to those wrappers.

### Related Projects

- `cloud-dog-ai-ui-monorepo/apps/expert-agent` is part of the evidence base for expert-agent traceability, not just the frontend implementation. Stale matrix rows can only be corrected accurately by reading both repos together.
- Platform standards work and service-local matrix work must stay aligned. `docs/REQUIREMENTS.md`, `docs/TESTS.md`, and `docs/ACCEPTED-GAPS.md` in this repo are the local truth source, but the platform instruction report remains the execution record.
- Shared `@cloud-dog/ui` adoption is what made the `DataTable` and `EntityDialog` structural proof possible. When services bypass those wrappers, later forensic triage becomes much harder.

### Process / Reporting

- On docs-only matrix instructions, say plainly that no runtime code changed and no UT/IT/AT/deploy chain was executed. Do not imply implementation work that did not happen.
- If an instruction asks for an independent coordinator spot-check and none occurred, state that honestly and leave a handoff suggestion instead of fabricating verification.
- `PARTIAL` is not an end state on this platform. Each item must be resolved to `IMPLEMENTED`, `ACCEPTED-GAP`, or `OUT_OF_SCOPE`, and the matrix must end with zero undecided rows.

### Preprod PW testing — expert-agent env vars (2026-05-06)

**Origin:** A133 investigation. Expert-agent PW tests hardcode port 28083 in `defaultDirectApiBase()`. For preprod:
```bash
E2E_BASE_URL=https://expertagent0.cloud-dog.net  E2E_USE_LOCAL_SERVER=0  E2E_REAL=1  CI=true
E2E_DIRECT_API_BASE_URL=https://expertagent0.cloud-dog.net/api
E2E_API_KEY=ExpertAgent5678  E2E_PASSWORD=OrangeRiverTable  E2E_USERNAME=admin
```
API path is `/api` NOT `/api/v1`. `E2E_REAL=1` is REQUIRED (disables local webServer, enables real auth). `E2E_PASSWORD` is the correct env var -- NOT `E2E_WEB_PASSWORD` (nothing reads `E2E_WEB_PASSWORD`). `fixtures.ts:63` and `w28a877-real-e2e.spec.ts:133` both read `E2E_PASSWORD`.

**Confirmed preprod score (run 2b, 2026-05-06):** 32/2/1flaky/5dnr = 80% (up from 72.5% in run 1).
- A133 predicted 92.5-97.5%; actual 80% due to NEW section d failure (session detail dialog pattern mismatch) and section c flakiness (strict mode violation on chat message text).
- Sections a, b, c now RUN and PASS (a+b deterministic, c LLM-dependent but passing with flakiness).
- Section d FAILS: `Session \d+ detail` text not found after clicking Detail button on session row (UI contract mismatch -- the dialog does not render that text pattern).
- Sections e-i DNR: cascade from d failure in serial mode.
- w28a642: still FAILS (user row not visible after create -- UI reactivity bug, confirmed by A133).
- All 29 previously-passing tests still pass; jobs-ps76 now also passes (was F1 in run 1).

**Section D fix applied (2026-05-06):** Changed `w28a877-real-e2e.spec.ts` line 985 regex from `/Session \d+ detail/` to `/Structured metadata for session \d+/`. The UI (SessionsPage.tsx line 156) renders "Structured metadata for session {id}", not "Session {id} detail". This was a test bug, not a UI bug.

**Confirmed preprod score (post-fix, 2026-05-06):** 39/40 passed, 1 failed = 97.5%.
- All 9 w28a877 sections (a-i) now PASS. Section d: 8.1s. Sections e-i unblocked by the fix.
- w28a642: still FAILS (pre-existing UI reactivity bug, unrelated to section-d fix).
- Full log: `/tmp/pw-expert-agent-section-d-fix.log`.

**w28a642 orphan users:** 18+ orphan `w28a642_*` test users on preprod (15 from runs 1-4, plus 3 more from run 2b). Creation works but AdminUsersPage DataTable doesn't refresh (UI reactivity bug). Cleanup needed.

**w28a642 fix applied (2026-05-06):** Root cause was NOT a UI reactivity bug. The DataTable DOES refresh after create, but it paginates at 10 rows/page. On preprod with >10 users, the new user lands beyond page 1. The test was looking for the row on the visible page. Fix: fill the `AppDataTable` search input (aria-label "Search users") with the username to filter the table before asserting row visibility. Extended timeouts to 15000ms for preprod API latency. Also re-assert row visibility after edit+refresh since the search filter persists.

**Confirmed preprod score (post-w28a642-fix, 2026-05-06):** 40/40 target, 38/40 deterministic pass + 1 flaky pass + 1 LLM-dependent failure = effective 39/40.
- w28a642: PASSES (54.7s). Test creates user, searches, edits, deletes, then verifies monitoring logs. No orphans left after run.
- Section c (chat): flaky (strict mode violation on chat message text — pre-existing, LLM-dependent).
- Section h (prompts): was failing on "Generate test cases" 120s timeout. Root cause: test.setTimeout(240000) was too tight for 3 sequential LLM calls (validate + generate-test-cases + preview) each with 120s assertion timeouts (360s worst-case in a 240s test). Fix: bumped test.setTimeout to 480000. Now passes reliably (typically ~40-50s actual).
- 21 orphan `w28a642_*` users cleaned up via API DELETE. Post-cleanup: 10 real users remain.
- Full log: `/tmp/pw-expert-full-suite-fix2.log`.

### w28a642 pagination lesson

> See platform AGENT-LESSONS.md §6.40 for the cross-service AppDataTable pagination test pattern.

- `AppDataTable` (in `apps/expert-agent/src/lib/data-table-adapter.tsx`) defaults to `pageSize=10`. When the user list exceeds one page, newly created users may land beyond the visible page after refresh.
- The correct test pattern: after confirming the status message ("Created user ..."), fill the DataTable search input to filter by username before asserting row visibility. The search input has `aria-label="Search {itemLabel}"` — for UsersPage that is `aria-label="Search users"`.
- The search filter persists across React state updates (it's internal `AppDataTable` state), so subsequent edit/delete actions on the filtered row work without re-searching.
- This was misdiagnosed as a "UI reactivity bug" for 6 previous runs. The DataTable DID refresh; the row was simply on a non-visible page due to pagination.

---

## Traefik stripprefix / base_path alignment fix (2026-05-06)

> See platform AGENT-LESSONS.md §6.37 for the cross-service rule.

### Code

- `defaults.yaml` `api_server.base_path` is now `/v1`, NOT `/api/v1`. Traefik strips `/api` from incoming requests before forwarding to the API server on port 8083. If base_path includes `/api`, then after the strip the route becomes `/v1/users` but the server has routes at `/api/v1/users` -- 404. With base_path `/v1`, the server registers routes at `/v1/users`, matching what Traefik delivers.
- `src/common/base_paths.py` `SURFACE_BASE_PATH_DEFAULTS["api"]` was `/api/v1` -- now `/v1`. This is the fallback used when no config value is present.
- `src/servers/api/server.py` `APIServer.__init__` fallback default was `/api/v1` -- now `/v1`.
- The `/api/v1/heartbeat` path in `tests/application/AT1.17_VectorStoreManagement/test_AT1_17_real.py` is the ChromaDB REST API endpoint -- NOT expert-agent's base_path. Do not change it.
- Same pattern as chat-client A138 fix: Traefik `stripprefix.prefixes=/api` strips the `/api` prefix; the API server base_path must not include `/api`.

### Test Environment

- Pre-fix proof: `curl /api/v1/users` -> 404; `curl /api/api/v1/users` -> 200 (double-prefix workaround confirms the strip mismatch).
- Post-fix proof: `curl /api/v1/users` -> 200; all config_admin endpoints (users, groups, api-keys) return 200.
- SPA client code in the UI monorepo still uses `api/v1/users` (relative path). Through Traefik, this becomes `https://expertagent0.cloud-dog.net/api/v1/users` -> Traefik strips `/api` -> API server receives `/v1/users` -> matches route. No SPA code change needed.

### Architecture

- The Traefik stripprefix pattern is platform-wide: all 9 services have `stripprefix.prefixes=/api` for their API surface. The strip removes the first path segment (`/api`) before forwarding to the API server. Any route prefix on the API server must NOT include `/api` because Traefik already stripped it.
- Health routes (`/health`, `/api/health`) are registered at both paths on the API server, so they work with and without the strip.
- Only config_admin routes (users, groups, api-keys, profiles, jobs) use the configurable base_path. These were the only routes affected by the mismatch.

---

## W28A-88f Backend Test Fix Lessons (2026-05-06)

### Runtime / Config

- Vault config payloads can arrive with `data.data.json` as a JSON string, not only an object. Both pytest bootstrap loading (`tests/conftest.py`) and runtime loading (`src/config/loader.py`) must `json.loads(...)` that string form before walking the config tree.
- `tests/env-IT` must define `embeddings.provider`, `embeddings.base_url`, `embeddings.model`, and `embeddings.dimension` explicitly. Relying on defaults left `IT2.6` with `embeddings.model not configured`.

### Server Control / Lifecycle

- `server_control.sh` CLI fast paths are part of the test contract. `help`, invalid commands, and invalid server names must exit before Vault/config resolution, or `ST1.6` will time out on cases that are supposed to return immediately.
- For this repo, Gate 2 means using only `./server_control.sh --env <env> start-all|stop-all` for local lifecycle during ST/AT work. Do not hand-start `start_*.py` servers.

### MCP / A2A Compatibility

- MCP admin tool authorization must resolve the caller role from the API key before checking `expert:admin:*`. Relying only on `auth_context.role` breaks `IT2.42` for valid admin API keys.
- Older installed `cloud_dog_api_kit` builds can still omit MCP `structuredContent` on `/mcp` tool responses even when the checked-in platform source has already been fixed. A local compatibility shim may be required until the installed package catches up.
- Some environments still lack `cloud_dog_api_kit.a2a.events` exports. The A2A server must tolerate that with local fallbacks for `ConfigChangeEvent`, `EventBroadcaster`, and the events router.

### Test Design

- `ST1.26` patches `src.core.job.callbacks.httpx.AsyncClient`. Callback dispatch code must call `httpx.AsyncClient` from that module boundary, not a deeper shared-client abstraction, or the test patch point misses the live code.
- Application tests that create in-process `fastapi.testclient.TestClient` instances must close them explicitly in `finally` blocks. Leaving them open can leak APIServer resources and destabilize later real-server suites in the same pytest process.
- OpenSearch AT1.11 tests must isolate collections per run. Reusing the shared `expert_agent_test` collection pulls in unrelated documents from prior runs and makes query assertions nondeterministic.
- OpenSearch query results should be validated by returned document content or equivalent semantic payload, not by assuming the backend will echo the caller-supplied `document_id`. Provider record IDs can differ from request IDs.
- Application tests that call `./server_control.sh --env ... restart api` must validate restart success and wait for `/health` before continuing with auth/authorization assertions. The raw restart return alone was not a stable readiness signal for the later `AT1.29 -> AT1.2` corridor.
- AT1.2-style real API tests should use the shared `create_api_client_fixture(...)` recovery-aware client path rather than a bespoke one-off health probe. The shared fixture is what keeps later order-dependent restarts from surfacing as false-negative setup errors.
