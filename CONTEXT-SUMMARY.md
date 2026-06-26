# Context Summary — expert-agent-mcp-server

**Last updated:** 2026-05-07

## Recent Delivery

### W28A-88f Backend Test Fix

- Objective: make backend test layers green across `UT`, `ST`, `IT`, and `AT`, update lessons/reporting, and keep all local lifecycle work on the approved `server_control.sh --env ...` path.
- Final verified status:
  - `UT`: `431 passed, 20 warnings in 149.52s`
  - `ST`: `162 passed, 3 warnings in 286.21s`
  - `IT`: `84 passed, 3 warnings in 172.45s`
  - `AT`: `686 passed, 2 skipped, 7 warnings in 1748.49s`
- Primary evidence:
  - [working/W28A-88f-REPORT.md](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/working/W28A-88f-REPORT.md)
  - [working/test-ut.log](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/working/test-ut.log)
  - [working/test-st.log](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/working/test-st.log)
  - [working/test-it.log](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/working/test-it.log)
  - [working/test-at.log](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/working/test-at.log)

## Key Fixes

- Vault config loading now tolerates `data.data.json` arriving as a JSON string in both pytest bootstrap and runtime config loaders.
- `server_control.sh` fast-paths `help`, invalid commands, and invalid server names before Vault/config resolution, and uses the stable detached launcher path again.
- MCP admin RBAC now resolves the real role from API keys, and MCP transport compatibility is patched for older installed API-kit builds that omit `structuredContent`.
- A2A startup now tolerates environments that lack `cloud_dog_api_kit.a2a.events` exports.
- Callback dispatch uses `httpx.AsyncClient` at the module boundary expected by `ST1.26`.
- `tests/env-IT` now defines embeddings settings explicitly for the embedding integration suite.
- `AT1.123` and `AT1.124` orchestration tests now close in-process `TestClient` instances to avoid leaking app resources into later real-server application suites.
- `AT1.11` OpenSearch CRUD/options tests now isolate collections per run and validate query/delete behavior by document content instead of assuming provider-preserved `document_id` values.
- `AT1.29` now validates API restart success and waits for `/health` before auth/authorization assertions.
- `AT1.2` now uses a proper module-scoped wrapper around the shared recovery-aware API client fixture.

## Operational Rules

- For local service lifecycle during backend test work, use only:
  - `./server_control.sh --env tests/env-ST start-all|stop-all`
  - `./server_control.sh --env tests/env-AT start-all|stop-all`
- Do not hand-start `start_api_server.py`, `start_mcp_server.py`, `start_a2a_server.py`, or `start_web_server.py`.
- Gate 2 is satisfied by the repo control path itself: local services must start on the allocated ports via `server_control.sh`.

## Current State

- Backend test-fix code changes are present in the worktree and documented in [AGENT-LESSONS.md](/opt/iac/Development/cloud-dog-ai/expert-agent-mcp-server/AGENT-LESSONS.md).
- The W28A report now reflects the final all-green test outcome.
- There are still uncommitted working-tree changes associated with the test-fix task.
- Unrelated untracked backup directory remains untouched: `ui/dist.bak.W28A-A22-1777889722/`.
