---
template-id: T-CHG
template-version: 1.0
project: expert-agent-mcp-server
doc-last-updated: 2026-06-14T17:35:58Z
doc-conformance-stamp: 2026-06-14T17:35:58Z
---

# expert-agent-mcp-server — Changelog

_Created by W28C-1710a recovery to receive carry-forward content from `archive/2026-06-12/`._



<!-- W28C-1710a recovery: full content from archive/2026-06-12/ACCEPTED-GAPS.md (archived sha256=97bd622572f6, 14 lines) -->

## Recovered domain content — `archive/2026-06-12/ACCEPTED-GAPS.md` (14 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/ACCEPTED-GAPS.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# Accepted Gaps

This document records requirements that remain intentionally narrower than the
original requirement wording. Each accepted gap includes the current state,
rationale, and a concrete revisit date.

## W28A-1000 Accepted Gaps

| Requirement | Current state | Rationale | Revisit date |
|---|---|---|---|
| `W875-REQ-02` Expert service/sub-expert binding management in WebUI | `ExpertsPage` shows bound services and sub-experts in the inventory and edit dialog, but binding create/delete still happens via API-only flows. | The current WebUI proves visibility and RBAC, but it does not yet provide a safe relation-editor workflow for cross-entity binding mutation. Accept the gap rather than over-claim UI capability. | 2026-07-31 |
| `W875-REQ-04` Channel vector-store/tool/service binding management in WebUI | Backend routes exist for channel vector-store/tool/service bindings, but `ChannelsPage` still provides channel CRUD only. | The UI has no binding editor for channel composition yet. Accept the gap explicitly instead of treating backend-only capability as browser coverage. | 2026-07-31 |
| `W875-REQ-06` Chat timeline, tool-call stream, lifecycle controls | `ChatPage` now shows timeline and tool-call evidence. Session detail/delete/bulk lifecycle controls live on `SessionsPage`, not the chat workbench. | The platform currently splits live conversation operations and destructive session management across two pages. Accept the narrower chat-surface scope until there is a product need to merge those controls. | 2026-07-31 |
| `W875-REQ-10` Files upload UI and structured ingest selection | Structured ingest target selection is dialog-driven in `FilesPage`, but browser-native upload is still absent. | The service already has upload endpoints, but the platform still lacks a settled file-transfer standard/package (PS-94 gap). Accept the missing upload widget rather than extend bespoke upload UX during this triage. | 2026-07-31 |


<!-- W28C-1710a recovery: full content from archive/2026-06-12/MIGRATION_PLAN.md (archived sha256=0402be80672d, 535 lines) -->

## Recovered domain content — `archive/2026-06-12/MIGRATION_PLAN.md` (535 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/MIGRATION_PLAN.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# Expert Agent MCP Server - Migration Plan
**Version:** 1.0 • 2025-01-XX
**Purpose:** Align project structure and documentation with RULES.md requirements

---

## Executive Summary

This document outlines the migration plan to align the Expert Agent MCP Server project structure and documentation with the requirements specified in `RULES.md`. The migration will ensure:

1. **Folder Structure Compliance** - All required folders exist and are properly organized
2. **Documentation Completeness** - All required documents exist and follow naming conventions
3. **Test Organization** - Tests are organized by type with numbered folders matching TESTS.md
4. **File Naming Consistency** - Documents follow consistent naming (e.g., TASKS.md not Tasks.md)
5. **Cross-Reference Alignment** - Requirements, Tasks, Architecture, and Tests are properly cross-referenced

### ⚠️ Critical Rule: Temporary Working Files

**Per RULES.md Section "working":**
- **ALL temporary working files MUST be stored in `working/` folder**
- This includes: working documents, reports, test results created during delivery
- Can be deleted at any time (transient information only)
- Excluded from git repo
- Agent maintains this folder
- Useful information should be extracted to REQUIREMENTS, TASKS, TESTS, ARCHITECTURE documents
- No PII/secure credentials should be stored here

---

## Current State Analysis

### ✅ Existing Folders (Compliant)
- `src/` - Source code ✓
- `docs/` - Documentation ✓
- `tests/` - Test structure (needs reorganization) ✓
- `database/` - Database migrations ✓
- `scripts/` - Application scripts ✓
- `logs/` - Log files ✓
- `private/` - Private configuration ✓
- `config/` - Configuration files ✓

### ❌ Missing Folders (Required by Rules)
- `archive/` - For unused files to be deleted later [excluded from git repo]
- `working/` - **Temporary working files location**: Any working documents, reports, test results created during delivery. Can be deleted at any time, must only contain transient information. Agent maintains this folder. Useful information should be extracted to REQUIREMENTS, TASKS, TESTS, ARCHITECTURE documents. No PII/secure credentials. [excluded from git repo]
- `storage/` - Local running/server development/project storage, used during development and local testing [excluded from git repo]
- `tmp/` - Project run/delivery tmp area if needed
- `cache/` - Application delivery/runtime cache (version controlled, but transient/temporary in nature)
- `query_responses/` - Application delivery/runtime query responses (version controlled, but transient/temporary in nature)
- `prompts/` - Application delivery/runtime prompts (version controlled, but transient/temporary in nature)

### ✅ Existing Documents (Compliant)
- `README.md` - Top-level README ✓
- `RULES.md` - Cursor/Agent rules ✓
- `docs/REQUIREMENTS.md` - Requirements document ✓
- `docs/ARCHITECTURE.md` - Architecture document ✓
- `docs/PARAMETERS.md` - Parameters document ✓
- `docs/AGENT_RULES.md` - Agent-specific rules ✓
- `docs/FOLDER_STRUCTURE.md` - Folder structure doc ✓
- `docs/SUMMARY.md` - Project summary ✓

### ❌ Missing Documents (Required by Rules)
- `LICENSE` - License file (Apache 2.0)
- `CONTEXT-SUMMARY.md` - AI agent contextual summary (root level)
- `openapi.json` - OpenAPI 3.x specification for API server
- `docs/TASKS.md` - Tasks document (currently `Tasks.md` - needs rename)
- `docs/TESTS.md` - Tests document (currently `Tests.md` - needs rename)
- `docs/API_SERVER.md` - API Server specification
- `docs/MCP_SERVER.md` - MCP Server specification
- `docs/A2A_SERVER.md` - A2A Server specification
- `docs/WEB_UI.md` - Web UI Server specification
- `docs/API_DOCUMENTATION.md` - Complete API endpoint documentation
- `docs/DOCKER.md` - Docker build, deployment, configuration guide

### ⚠️ Documents Needing Review/Consolidation
- `COMPRESSED_CONTEXT.md` - Should be `CONTEXT-SUMMARY.md` or moved to archive
- `docs/SUMMARY.md` - May need to be consolidated or moved to archive if redundant
- `docs/FOLDER_STRUCTURE.md` - May need to be consolidated into ARCHITECTURE.md

### ❌ Missing README Files (Required by Rules)
- `database/README.md` - Database folder overview
- `docs/README.md` - Documentation folder overview
- `archive/README.md` - Archive folder overview (when created)
- `working/README.md` - Working folder overview (when created)
- `private/README.md` - Already exists ✓
- `tests/README.md` - Test folder overview
- `src/README.md` - Source code folder overview
- `logs/README.md` - Logs folder overview
- `scripts/README.md` - Scripts folder overview
- `storage/README.md` - Storage folder overview (when created)
- `tmp/README.md` - Tmp folder overview (when created)
- `cache/README.md` - Cache folder overview (when created)
- `query_responses/README.md` - Query responses folder overview (when created)
- `prompts/README.md` - Prompts folder overview (when created)

### ⚠️ Test Structure Issues
- Tests are organized by type (unit, integration, functional) but **NOT** in numbered folders
- Tests do **NOT** match the naming convention: `{TYPE}{NUMBER}_{DescriptiveName}`
- Tests are **NOT** aligned with entries in `docs/Tests.md` (needs to be `TESTS.md`)
- Missing `system/` test folder (ST tests)
- Test numbering scheme needs to be established

---

## Migration Plan

### Phase 1: Folder Structure Creation (Priority: HIGH)

#### 1.1 Create Missing Folders
```bash
# Create required folders (excluded from git)
mkdir -p archive          # Unused files, to be deleted later
mkdir -p working          # TEMPORARY WORKING FILES - transient documents, reports, test results
mkdir -p storage           # Local running/server development/project storage
mkdir -p tmp               # Project run/delivery tmp area if needed

# Create application runtime folders (version controlled, but transient)
mkdir -p cache             # Application delivery/runtime cache
mkdir -p query_responses    # Application delivery/runtime query responses
mkdir -p prompts           # Application delivery/runtime prompts

# Create missing test structure
mkdir -p tests/system      # Missing system test folder (ST tests)
```

#### 1.2 Create .gitignore Entries
Ensure `.gitignore` excludes (per RULES.md):
- `archive/` - Excluded from git repo
- `working/` - **Excluded from git repo** (temporary working files location)
- `storage/` - Excluded from git repo
- `private/` - Already excluded (contains PII, credentials, API keys)
- `logs/` - Should be excluded
- `tmp/` - Excluded from git repo

**Note:** `cache/`, `query_responses/`, and `prompts/` are version controlled per rules (application delivery/runtime folders), but they are transient/temporary in nature.

#### 1.3 Create README Files for All Folders
Create README.md files for each folder explaining:
- Purpose of the folder
- What should be stored there
- Links to related documentation
- Examples of typical contents
- Git exclusion status (if applicable)

**Priority Order:**
1. `working/README.md` - **CRITICAL**: Must clearly state this is for temporary working files, can be deleted at any time, excluded from git
2. `archive/README.md` - For unused files to be deleted later
3. `storage/README.md` - Local running/server development/project storage
4. `tmp/README.md` - Project run/delivery tmp area
5. `cache/README.md` - Application runtime cache (version controlled, transient)
6. `query_responses/README.md` - Application runtime query responses (version controlled, transient)
7. `prompts/README.md` - Application runtime prompts (version controlled, transient)
8. `database/README.md` - Database folder overview
9. `docs/README.md` - Documentation folder overview
10. `tests/README.md` - Test folder overview (note: test results/logs/workings go in test subfolders)
11. `src/README.md` - Source code folder overview
12. `logs/README.md` - Logs folder overview
13. `scripts/README.md` - Scripts folder overview

---

### Phase 2: Document Renaming and Creation (Priority: HIGH)

#### 2.1 Rename Existing Documents
```bash
# Rename to match rules (uppercase)
mv docs/Tasks.md docs/TASKS.md
mv docs/Tests.md docs/TESTS.md
```

#### 2.2 Create Missing Root-Level Documents
1. **LICENSE** - Create Apache 2.0 license file
2. **CONTEXT-SUMMARY.md** - Create or rename from `COMPRESSED_CONTEXT.md`
   - Decision needed: Rename existing or create new?
   - Should be updated at each git commit

#### 2.3 Create Missing Server Documentation
Create comprehensive documentation for each server following the template in RULES.md:

1. **docs/API_SERVER.md**
   - Document Header: Version, metadata
   - Overview: Purpose, port (8083), protocol
   - Quick Start: Running, configuration, health check
   - Key Features: Capabilities and operations
   - Architecture: Components, data flow, integration
   - Protocol/Interface Details: Request/response formats, endpoints
   - Key Flows: Workflows and processing flows
   - Usage Examples: Client examples and integration
   - Configuration: Settings and configuration reference
   - Startup & Deployment: Startup process and deployment options
   - Error Handling: Error formats, common errors, recovery
   - Performance: Benchmarks, optimization, caching
   - Monitoring & Troubleshooting: Debug, logging, metrics, common issues
   - Security Considerations: Auth, authorization, data protection
   - Scaling: Horizontal/vertical scaling, connection pooling
   - Advanced Features: Advanced patterns and customization
   - Best Practices: Usage, security, development practices
   - Future Enhancements: Roadmap and planned features
   - Resources: Source code, config files, documentation links
   - Related Documentation: Cross-references
   - Support: Repository, issues, license
   - Server-Specific: OpenAPI spec, rate limits, database schema

2. **docs/MCP_SERVER.md**
   - Similar structure with MCP-specific content
   - Transport modes (stdio, HTTP/SSE)
   - Tool registry and protocol compliance
   - MCP tools: chat, start_session, resume_session, end_session, list_sessions, get_session_status, get_session_history

3. **docs/A2A_SERVER.md**
   - Similar structure with A2A-specific content
   - WebSocket topics, natural language commands, event streaming

4. **docs/WEB_UI.md**
   - Similar structure with Web UI-specific content
   - UI components, keyboard shortcuts, mobile access

5. **docs/API_DOCUMENTATION.md**
   - Complete API endpoint documentation
   - Document Header - Version, OpenAPI links
   - Table of Contents - Navigation
   - Overview - Purpose and capabilities
   - OpenAPI Specification - Spec access and tooling
   - Authentication - Auth methods and security
   - Base URLs - Development and production URLs
   - Core Endpoints - Root, health, status
   - Primary Operations - Main API operations
   - Resource Management - CRUD operations
   - Context/Configuration Management - System configuration
   - User & Group Management - User operations
   - Callbacks & Webhooks - Webhook endpoints
   - Administration - Logs, metrics, activity
   - Request/Response Examples - Working examples
   - Error Handling - Error codes and formats
   - Rate Limiting - Limits and configuration
   - OpenAPI Tooling Integration - Swagger, Postman, code generation
   - Additional Resources - Related docs and support
   - Updates and Changelog - Version history
   - Planned Features - Roadmap and deprecations

6. **docs/DOCKER.md**
   - Consolidated Docker documentation
   - Build, deployment, settings, configuration dependencies
   - Container management
   - Docker Compose configuration
   - Environment setup

#### 2.4 Create OpenAPI Specification
- **openapi.json** - OpenAPI 3.x specification
  - Should reflect all API endpoints
  - Include examples and descriptions
  - Maintained at each release/commit/deploy

---

### Phase 3: Test Structure Reorganization (Priority: MEDIUM)

#### 3.1 Review and Categorize Existing Tests
1. Review all existing test files in `tests/unit/`, `tests/integration/`, `tests/functional/`
2. Categorize each test as:
   - **UT** (Unit Tests): Individual functions, methods, classes
   - **ST** (System Tests): System functionality (database, LLM health, service availability)
   - **IT** (Integration Tests): Integration between components
   - **AT** (Application/Business Tests): End-to-end business scenarios

#### 3.2 Update TESTS.md with Numbered Test Entries
1. Review `docs/TESTS.md` (after rename)
2. Ensure each test has:
   - Unique test number (UT1.1, UT1.2, ST1.1, IT1.1, AT1.1, etc.)
   - Test type, scope, what is being tested
   - Inputs/outputs, preconditions
   - Test run history (last 5 max)
   - Related Requirements, Architecture, Tasks
   - Related tests

#### 3.3 Reorganize Test Files into Numbered Folders
For each test in TESTS.md:
1. Create folder: `tests/{type}/{NUMBER}_{DescriptiveName}/`
2. Move test file(s) into folder
3. Rename test file to match naming convention: `test_{descriptive_name}.py`
4. Optionally create `README.md` in test folder for test-specific documentation

**Example Structure:**
```
tests/
  unit/
    UT1.1_ConfigTests/
      test_config_manager.py
      README.md
    UT1.2_DatabaseTests/
      test_database_manager.py
  system/
    ST1.1_HealthChecks/
      test_health_endpoints.py
  integration/
    IT1.1_SessionManagement/
      test_session_flow.py
  functional/
    AT1.1_ExpertConversation/
      test_expert_chat.py
```

#### 3.4 Create Test Subfolders for Results/Logs
Per RULES.md, tests folder should have subfolders to hold:
- Test results
- Test logs
- Test data/workings

**Note:** Per rules, test results/workings created during delivery should go in `working/` folder (temporary), but structured test results/logs that are part of the test organization should remain in test subfolders.

---

### Phase 4: Document Consolidation and Review (Priority: MEDIUM)

#### 4.1 Review Redundant Documents
1. **COMPRESSED_CONTEXT.md**
   - Decision: Rename to `CONTEXT-SUMMARY.md` or move to archive?
   - Recommendation: Rename to `CONTEXT-SUMMARY.md` if it serves the purpose

2. **docs/SUMMARY.md**
   - Review if redundant with README.md or other docs
   - If redundant, consolidate into appropriate document or move to archive

3. **docs/FOLDER_STRUCTURE.md**
   - Review if this information belongs in ARCHITECTURE.md
   - If redundant, consolidate into ARCHITECTURE.md or move to archive

#### 4.2 Ensure Cross-References
1. **Requirements-Tasks-Tests Mapping**
   - Review all requirements in `docs/REQUIREMENTS.md`
   - Ensure each requirement maps to:
     - At least one Task in `docs/TASKS.md`
     - At least one Test in `docs/TESTS.md`
   - Add backlog entries in TASKS.md for requirements without tasks

2. **Architecture Alignment**
   - Ensure ARCHITECTURE.md references:
     - Related Requirements
     - Related Tasks
     - Related Tests
   - Use identifiers (OV1.1, SA1.2, CC2.1, etc.)

3. **Task Alignment**
   - Ensure TASKS.md references:
     - Related Requirements
     - Related Architecture sections
     - Related Tests
   - Track completion with dates and git tags

---

### Phase 5: Code Header Updates (Priority: LOW)

#### 5.1 Review Source Code Headers
1. Review all source code files in `src/`
2. Ensure each file has header docstring with:
   - License: Apache 2.0
   - Ownership: Cloud Dog
   - Description: What the code does
   - Related Requirements: SV1.1, BR1.1, FR1.1, UC1.1
   - Related Tasks: T1, T5, T12
   - Related Architecture: OV1.1, SA1.2, CC2.1
   - Related Tests: UT1.1, IT2.3, AT5.1
   - Recent Changes (max 10): Commit hash and description

#### 5.2 Update Function/Method Documentation
Ensure all functions, procedures, methods, classes have:
- Description of what the component does
- Where/what it is used for/by
- Key processes it supports
- Inputs, outputs, dependencies, limitations
- List of tests (unit, system, integration) that test it

---

## Implementation Checklist

### Phase 1: Folder Structure
- [x] Create `archive/` folder (excluded from git) ✅
- [x] Create `working/` folder (excluded from git) - **TEMPORARY WORKING FILES LOCATION** ✅
- [x] Create `storage/` folder (excluded from git) ✅
- [x] Create `tmp/` folder (excluded from git) ✅
- [x] Create `cache/` folder (version controlled, transient) ✅
- [x] Create `query_responses/` folder (version controlled, transient) ✅
- [x] Create `prompts/` folder (version controlled, transient) ✅
- [x] Create `tests/system/` folder (for ST system tests) ✅
- [x] Update `.gitignore` to exclude: `archive/`, `working/`, `storage/`, `tmp/`, `logs/`, `private/` ✅
- [x] Create README.md for `working/` - **CRITICAL**: Must state temporary files location, can be deleted, excluded from git ✅
- [x] Create README.md for `archive/` ✅
- [x] Create README.md for `storage/` ✅
- [x] Create README.md for `tmp/` ✅
- [x] Create README.md for `cache/` ✅
- [x] Create README.md for `query_responses/` ✅
- [x] Create README.md for `prompts/` ✅
- [x] Create README.md for `database/` ✅
- [x] Create README.md for `docs/` ✅
- [x] Create README.md for `tests/` (note test results/logs/workings subfolders) ✅
- [x] Create README.md for `src/` ✅
- [x] Create README.md for `logs/` ✅
- [x] Create README.md for `scripts/` ✅

### Phase 2: Documents
- [x] Rename `docs/Tasks.md` to `docs/TASKS.md` ✅
- [x] Rename `docs/Tests.md` to `docs/TESTS.md` ✅
- [x] Create `LICENSE` file (Apache 2.0) ✅
- [x] Create/rename `CONTEXT-SUMMARY.md` ✅
- [x] Create `docs/API_SERVER.md` ✅
- [x] Create `docs/MCP_SERVER.md` ✅
- [x] Create `docs/A2A_SERVER.md` ✅
- [x] Create `docs/WEB_UI.md` ✅
- [x] Create `docs/API_DOCUMENTATION.md` ✅
- [x] Create `docs/DOCKER.md` ✅
- [x] Create `openapi.json` ✅

### Phase 3: Test Reorganization
- [ ] Review and categorize all existing tests
- [ ] Update `docs/TESTS.md` with numbered test entries
- [ ] Create numbered test folders (UT1.1_*, ST1.1_*, IT1.1_*, AT1.1_*)
- [ ] Move test files into numbered folders
- [ ] Rename test files to match convention
- [ ] Create test result/log subfolders
- [ ] Create README.md files for test folders (optional)

### Phase 4: Document Consolidation
- [x] Review `COMPRESSED_CONTEXT.md` - moved to archive ✅
- [x] Review `docs/SUMMARY.md` - updated references, kept (useful summary) ✅
- [x] Review `docs/FOLDER_STRUCTURE.md` - moved to archive (redundant with ARCHITECTURE.md) ✅
- [x] Review `docs/AGENT_RULES.md` - moved to archive (redundant with RULES.md) ✅
- [ ] Verify Requirements-Tasks-Tests mapping (needs review)
- [ ] Verify Architecture cross-references (needs review)
- [ ] Verify Tasks cross-references (needs review)

### Phase 5: Code Headers
- [ ] Review all source code files for header compliance
- [ ] Update missing/incomplete headers
- [ ] Update function/method documentation

---

## Migration Order and Dependencies

### Recommended Execution Order:
1. **Phase 1** (Folders) - No dependencies, can start immediately
2. **Phase 2.1-2.2** (Renames and root docs) - No dependencies
3. **Phase 2.3** (Server docs) - Can be done in parallel
4. **Phase 3** (Test reorganization) - Depends on Phase 2.1 (TESTS.md rename)
5. **Phase 4** (Consolidation) - Can be done in parallel with Phase 2
6. **Phase 5** (Code headers) - Can be done anytime, lowest priority

---

## Risk Assessment

### Low Risk
- Creating new folders
- Creating README files
- Renaming documents
- Creating new documentation

### Medium Risk
- Test reorganization (may break test runners temporarily)
- Document consolidation (may lose information if not careful)

### High Risk
- None identified - migration is primarily additive

---

## Success Criteria

Migration is complete when:
1. ✅ All required folders exist with README files
2. ✅ All required documents exist and follow naming conventions
3. ✅ Tests are organized in numbered folders matching TESTS.md
4. ✅ Requirements, Tasks, Architecture, and Tests are cross-referenced
5. ✅ All source code has proper headers
6. ✅ `.gitignore` properly excludes transient folders
7. ✅ Documentation is production-ready (no interim/working docs in docs/)

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize phases** based on project needs
3. **Assign tasks** to team members
4. **Begin Phase 1** (folder creation) - can start immediately
5. **Track progress** using the checklist above

---

## Notes

- This migration should be done incrementally to avoid disrupting ongoing work
- Test reorganization should be done carefully to avoid breaking CI/CD pipelines
- Document consolidation should preserve all important information
- All changes should be committed incrementally with clear commit messages

## Important Rules Compliance Notes

### Temporary Working Files
**Per RULES.md, ALL temporary working files must be stored in `working/` folder:**
- Any working documents, reports, test results created during delivery
- Can be deleted at any time (transient information only)
- Excluded from git repo
- Agent maintains this folder
- Useful information should be extracted to REQUIREMENTS, TASKS, TESTS, ARCHITECTURE documents
- No PII/secure credentials should be stored here

### Folder Purposes (Per RULES.md)
- **`working/`** - Primary location for temporary working files (excluded from git)
- **`tmp/`** - Project run/delivery tmp area if needed (excluded from git)
- **`storage/`** - Local running/server development/project storage (excluded from git)
- **`archive/`** - Unused files to be deleted later (excluded from git)
- **`cache/`, `query_responses/`, `prompts/`** - Application runtime folders (version controlled, but transient)

### Test Results Location
- Structured test results/logs/workings: Subfolders within `tests/` structure
- Temporary test results/workings during delivery: `working/` folder

---

**Document Status:** Migration Completed (Phases 1-2), Phase 4 Partial
**Last Updated:** 2025-01-XX
**Migration Status:** 
- ✅ Phase 1: COMPLETE - All folders created, READMEs created, .gitignore updated
- ✅ Phase 2: COMPLETE - All documents renamed/created, server docs complete
- ⚠️ Phase 3: PENDING - Test reorganization (no existing tests to reorganize yet)
- ✅ Phase 4: PARTIAL - Document consolidation complete (redundant docs archived)
- ⚠️ Phase 5: PENDING - Code header updates (low priority)

**Remaining Work:**
- Phase 3: Test reorganization (when tests are created)
- Phase 4: Cross-reference verification (Requirements-Tasks-Tests mapping)
- Phase 5: Code header compliance review


<!-- W28C-1710a recovery: full content from archive/2026-06-12/TASKS.md (archived sha256=cb001046e234, 16 lines) -->

## Recovered domain content — `archive/2026-06-12/TASKS.md` (16 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/TASKS.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# Tasks

## Current Delivery Tracks
| Workstream | Status | Notes |
|------------|--------|-------|
| Runtime surfaces | Complete | Source files detected: `src/servers/a2a/server.py`, `src/servers/api/routes/__init__.py`, `src/servers/api/routes/api_docs.py`, `src/servers/api/routes/api_keys.py`, `src/servers/api/routes/audit.py`, `src/servers/api/routes/auth.py`, `src/servers/api/routes/channels.py`, `src/servers/api/routes/experts.py`. |
| API documentation | Complete | `docs/API_DOCUMENTATION.md` reviewed against source inventory. |
| MCP documentation | Complete | `docs/MCP_DOCUMENTATION.md` reviewed against source inventory. |
| Configuration reference | Complete | `docs/PARAMETERS.md` and `docs/ENV-REFERENCE.md` regenerated from `defaults.yaml`. |
| Deployment guidance | Complete | `docs/DEPLOY.md` and `docs/DOCKER.md` refreshed with shareable examples. |
| Test catalogue | Complete | `docs/TESTS.md` refreshed from the current repository inventory. |

## Next Review Cycle
1. Re-run the release-relevant test tiers in the intended deployment environment.
2. Update API and MCP inventories whenever routes or tool contracts change.
3. Keep any non-standard topical docs aligned with the canonical set listed in this repository.
