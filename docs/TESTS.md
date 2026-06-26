---
template-id: T-TST
template-version: 1.1
applies-to: docs/TESTS.md
project: expert-agent-mcp-server
doc-last-updated: 2026-06-21
doc-git-commit: b7435e2385704de114dd5255d5005d11b73fd39a
doc-git-branch: main
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-21T00:00:00Z
req-trace-version: 1.0
total-tests: 1698
coverage-percent: 100
---

# Tests

## Service Scope
Expert reasoning, session orchestration, knowledge retrieval, vector-backed context, and administrative control across API, Web, MCP, and A2A surfaces.

## Test Inventory
| Tier | Present | Notes |
|------|---------|-------|
| `quality` | Yes | Repository contains the `quality` test tier. |
| `unit` | Yes | Repository contains the `unit` test tier. |
| `system` | Yes | Repository contains the `system` test tier. |
| `integration` | Yes | Repository contains the `integration` test tier. |
| `application` | Yes | Repository contains the `application` test tier. |
| `fixtures` | Yes | Repository contains the `fixtures` test tier. |

## Current Evidence Model
- The repository keeps execution evidence in repo-local working reports and rerunnable pytest suites.
- Browser evidence for the Expert Agent SPA lives in `cloud-dog-ai-ui-monorepo/apps/expert-agent/tests`.
- Before release, rerun the relevant `QT`, `UT`, `ST`, `IT`, and `AT` tiers against the intended environment overlays.
- This document records the current catalogue rather than claiming a release verdict.

## Standard Commands
```bash
.venv/bin/python -m pytest tests/quality --env tests/env-QT -q
.venv/bin/python -m pytest tests/unit --env tests/env-UT -q
.venv/bin/python -m pytest tests/system --env tests/env-ST -q
.venv/bin/python -m pytest tests/integration --env tests/env-IT -q
.venv/bin/python -m pytest tests/application --env tests/env-AT -q
cd ../cloud-dog-ai-ui-monorepo/apps/expert-agent && npm run e2e
```

## Notes
- Top-level test directories present: `__pycache__`, `application`, `fixtures`, `functional`, `integration`, `quality`, `system`, `unit`.
- Environment overlays and private credentials are intentionally not published in this document set.

## W28A-875 Requirement-to-Test Mapping

This section maps the merged W28A-875 requirements in `docs/REQUIREMENTS.md`
to current backend and browser evidence. The browser evidence below reflects the
current recovered suites, including `AT1.126_ForensicWebUIE2E` plus the
monorepo Playwright specs under `apps/expert-agent/tests/`.

| Requirement | Backend evidence | Browser / WebUI evidence | Coverage Status |
|---|---|---|---|
| `W875-REQ-01` Expert CRUD in API and WebUI | `tests/application/AT1.16_ExpertConfigManagement/test_AT1_16_real.py`, `tests/application/AT1.16_ExpertConfigManagement/test_expert_comprehensive.py`, `tests/application/AT1.16_ExpertConfigManagement/test_expert_real_comprehensive.py` | `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py::test_e6_expert_config`, `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `a)` | IMPLEMENTED |
| `W875-REQ-02` Expert service/sub-expert binding management in WebUI | `tests/application/AT1.123_OrchestrationWorkbench/test_orchestration_workbench.py`, `tests/application/AT1.124_RealServiceOrchestration/test_directory_processor.py`, `tests/system/ST1.61_OrchestrationAPI/test_orchestration_api.py`, `tests/unit/UT1.96_ServiceComposition/test_service_composition.py` | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `a)` only proves binding visibility after API seeding; `ExpertsPage` does not yet bind or unbind from the browser | ACCEPTED-GAP |
| `W875-REQ-03` Channel CRUD and expert linking | `tests/application/AT1.13_ChannelManagement/test_AT1_13_real.py`, `tests/application/AT1.91_WebUIChannelManagement/test_web_ui_channel_management.py`, `tests/integration/IT2.21_WebUIChannelManagement/test_web_ui_channel_management_integration.py` | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `b)` covers channel CRUD plus expert linking and RBAC; `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py::test_e10_channels` verifies the live route | IMPLEMENTED |
| `W875-REQ-04` Channel vector-store/tool/service binding management in WebUI | `tests/application/AT1.57_ChannelVectorStoreMappings/test_AT1_57_real.py`, `tests/application/AT1.58_ChannelChatVectorStoreRAG/*`, `tests/application/AT1.59_ChannelChatHistoryScopes/test_AT1_59_real.py` | Backend coverage exists, but there is still no browser suite and `ChannelsPage` does not expose the channel vector-store/tool/service binding routes | ACCEPTED-GAP |
| `W875-REQ-05` Chat send/respond/session snapshot | Channel chat backend is exercised by `tests/application/AT1.58_ChannelChatVectorStoreRAG/*` and channel management suites | `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py::test_e8_start_conversation`, `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `c)` | IMPLEMENTED |
| `W875-REQ-06` Chat timeline, tool-call stream, lifecycle controls | No single backend suite covers the entire browser lifecycle surface, but session, orchestration, and chat paths are exercised across AT suites | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `c)` captures prompt/response, timeline, and tool-call evidence; destructive session lifecycle controls intentionally live on the Sessions page (`section d)`) | ACCEPTED-GAP |
| `W875-REQ-07` Sessions inventory/detail/delete | `tests/application/AT1.2_SessionCreation/*`, `tests/application/AT1.9_SessionHistory/*`, `tests/application/AT1.47_SessionLimits/*`, `tests/application/AT1.48_SessionQueueing/*`, `tests/system/ST1.8_SessionPersistence/*` | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `d)` covers list/detail/bulk delete/paging/RBAC; `apps/expert-agent/tests/ui-review2.spec.ts` verifies expert names on `/sessions` | IMPLEMENTED |
| `W875-REQ-08` Scoped knowledge CRUD | `tests/application/AT1.103_KnowledgeHistoryCRUD/test_knowledge_history_crud.py`, `tests/application/AT1.40_KnowledgeVersioningRollback/test_AT1_40_real.py`, `tests/application/AT1.41_KnowledgeRemoval/test_AT1_41_real.py`, `tests/integration/IT2.33_KnowledgeHistoryCRUD/test_knowledge_history_crud_integration.py`, `tests/system/ST1.40_KnowledgeHistoryCRUD/test_knowledge_history_crud_readiness.py` | `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py::test_e7_knowledge_crud`, `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `e)` | IMPLEMENTED |
| `W875-REQ-09` Files inventory/metadata/download/ingest/metrics | `tests/application/AT1.114_FileStoreManagement/test_file_store_management.py`, `tests/application/AT1.116_FileTranslateIngestQuery/test_file_translate_ingest_query.py`, `tests/integration/IT2.37_FileIngestMCPVectorSearch/test_file_ingest_mcp_vector_search.py`, `tests/system/ST1.45_FileStoreUploadDownload/test_file_store_upload_download.py`, `tests/system/ST1.46_FileIngestVectorStore/test_file_ingest_vector_store.py` | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `f)` covers inventory, download, ingest, bulk delete, and RBAC; `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py::test_e13_files` verifies the live route | IMPLEMENTED |
| `W875-REQ-10` Files upload UI and structured ingest selection | Backend upload/ingest paths are covered by file-store suites above | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `f)` covers downstream file lifecycle and structured ingest dialog behaviour, but not a browser-native upload widget flow | ACCEPTED-GAP |
| `W875-REQ-11` Services inventory and health status list | `tests/application/AT1.95_ExternalServiceRegistry/test_external_service_registry_lifecycle.py`, `tests/integration/IT2.25_ExternalServiceRegistry/test_external_service_registry_integration.py`, `tests/system/ST1.32_ExternalServiceRegistry/test_external_service_registry_readiness.py` | `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py::test_e11_services`, `apps/expert-agent/tests/smoke.spec.ts`, `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `g)` | IMPLEMENTED |
| `W875-REQ-12` Services admin CRUD and health actions in WebUI | Backend covered by external-service registry suites above | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` section `g)` covers registration, health check, and binding visibility | IMPLEMENTED |
| `W875-REQ-13` Prompt CRUD, preview, validation, test-case generation | `tests/application/AT1.100_PromptTestCaseGeneration/test_prompt_test_case_generation.py`, `tests/application/AT1.44_AutoPromptGeneration/test_AT1_44_real.py`, `tests/application/AT1.45_PromptLLMValidation/test_AT1_45_real.py`, `tests/application/AT1.46_PromptValidationREST/test_AT1_46_real.py`, `tests/integration/IT2.30_PromptTestGeneration/test_prompt_test_generation_integration.py`, `tests/system/ST1.37_PromptTestCaseGeneration/test_prompt_test_case_generation_readiness.py`, `tests/unit/UT1.100_PromptTemplateManagement/test_prompt_templates.py` | `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py::test_e9_prompts`, `apps/expert-agent/tests/smoke.spec.ts`, `apps/expert-agent/tests/ui-review2.spec.ts` | IMPLEMENTED |
| `W875-REQ-14` Monitoring surface with multi-source AU-3-like log search | `tests/application/AT1.18_AuditLogViewing/test_audit_log_real_comprehensive.py`, `tests/application/AT1.96_LogHistoryManagement/test_log_history_management.py`, `tests/integration/IT2.26_LogHistoryExport/test_log_history_export_integration.py`, `tests/system/ST1.33_LogSearchExport/test_log_search_export_readiness.py` | `tests/w28a642-local-crud.spec.ts` exercises `/admin/monitoring`, source switching, and log search; `tests/smoke.spec.ts` covers route render | IMPLEMENTED |
| `W875-REQ-15` All tabular surfaces use platform `DataTable` | No dedicated backend test required | Live table evidence exists in `apps/expert-agent/tests/smoke.spec.ts` and `apps/expert-agent/tests/jobs-ps76-real.spec.ts`; source grep for app views returns zero raw HTML table markup and shared `EndpointTable`/`SimpleTable` now delegate to `DataTable` | IMPLEMENTED |
| `W875-REQ-16` All create/edit dialogs use platform `EntityDialog` | No dedicated backend test required | `tests/application/AT1.126_ForensicWebUIE2E/test_forensic_webui_e2e.py` exercises create/edit dialogs across users, groups, API keys, experts, knowledge, prompts, and services; source grep shows CRUD dialogs delegate through `CrudEntityDialog` / `EntityDialog` | IMPLEMENTED |
| `W875-REQ-17` Required route set exists in the app router | No dedicated backend test required | `tests/smoke.spec.ts` covers `/chat`, `/channels`, `/experts`, `/services`, `/knowledge`, `/files`, `/admin/prompts`, `/admin/monitoring`, and `/admin` | IMPLEMENTED |
| `W875-REQ-18` RBAC consistency for admin-only and scoped non-admin access | `tests/system/ST1.28_WebUIChannelPermissions/test_web_ui_channel_permissions.py`, `tests/application/AT1.34_LogHistoryAccessControl/test_AT1_34_real.py`, `tests/unit/UT1.99_ExpertApiAuth/test_expert_api_auth.py` | `apps/expert-agent/tests/w28a877-real-e2e.spec.ts` sections `a)`, `b)`, `d)`, `e)`, `f)`, and `g)` cover scoped non-admin access and denial/visibility rules | IMPLEMENTED |

## W28A-875 Coverage Summary

| Status | Count | Notes |
|---|---|---|
| `IMPLEMENTED` | 14 | Direct backend and browser or structural evidence exists, and the matrix row matches the live code/tests. |
| `ACCEPTED-GAP` | 4 | Requirement intentionally remains narrower than the original W28A-875 wording and is recorded in `docs/ACCEPTED-GAPS.md` with revisit dates. |
| `OUT_OF_SCOPE` | 0 | No W28A-875 requirement was removed from scope during this triage. |

## Executable Test Catalogue

The entries below catalogue executable pytest IDs discovered under `tests/` and provide requirement traceability for QT compliance checks. They intentionally complement the W28A-875 requirement-to-test matrix above.

UT1.1 - Executable coverage for `UT1.1`.
  Requirements: CM1.1, NF1.5
UT1.2 - Executable coverage for `UT1.2`.
  Requirements: NF1.8
UT1.3 - Executable coverage for `UT1.3`.
  Requirements: FR1.2
UT1.4 - Executable coverage for `UT1.4`.
  Requirements: FR1.5, CS1.1
UT1.5 - Executable coverage for `UT1.5`.
  Requirements: FR1.5
UT1.6 - Executable coverage for `UT1.6`.
  Requirements: FR1.1
UT1.7 - Executable coverage for `UT1.7`.
  Requirements: FR1.1, FR1.18
UT1.8 - Executable coverage for `UT1.8`.
  Requirements: FR1.1
UT1.9 - Executable coverage for `UT1.9`.
  Requirements: FR1.1
UT1.10 - Executable coverage for `UT1.10`.
  Requirements: FR1.2
UT1.11 - Executable coverage for `UT1.11`.
  Requirements: FR1.1
UT1.12 - Executable coverage for `UT1.12`.
  Requirements: FR1.1
UT1.13 - Executable coverage for `UT1.13`.
  Requirements: FR1.1
UT1.15 - Executable coverage for `UT1.15`.
  Requirements: FR1.3
UT1.16 - Executable coverage for `UT1.16`.
  Requirements: FR1.3
UT1.17 - Executable coverage for `UT1.17`.
  Requirements: FR1.3
UT1.18 - Executable coverage for `UT1.18`.
  Requirements: FR1.3
UT1.19 - Executable coverage for `UT1.19`.
  Requirements: FR1.3
UT1.20 - Executable coverage for `UT1.20`.
  Requirements: FR1.3
UT1.21 - Executable coverage for `UT1.21`.
  Requirements: FR1.3
UT1.22 - Executable coverage for `UT1.22`.
  Requirements: FR1.3
UT1.24 - Executable coverage for `UT1.24`.
  Requirements: FR1.3
UT1.25 - Executable coverage for `UT1.25`.
  Requirements: CS1.1
UT1.26 - Executable coverage for `UT1.26`.
  Requirements: CS1.1
UT1.27 - Executable coverage for `UT1.27`.
  Requirements: FR1.6
UT1.28 - Executable coverage for `UT1.28`.
  Requirements: FR1.2
UT1.29 - Executable coverage for `UT1.29`.
  Requirements: FR1.10
UT1.30 - Executable coverage for `UT1.30`.
  Requirements: FR1.9, CS1.4
UT1.31 - Executable coverage for `UT1.31`.
  Requirements: NF1.6
UT1.32 - Executable coverage for `UT1.32`.
  Requirements: CM1.1, NF1.1, NF1.5
UT1.33 - Executable coverage for `UT1.33`.
  Requirements: NF1.6
UT1.34 - Executable coverage for `UT1.34`.
  Requirements: NF1.6
UT1.36 - Executable coverage for `UT1.36`.
  Requirements: FR1.11
UT1.38 - Executable coverage for `UT1.38`.
  Requirements: FR1.11
UT1.42 - Executable coverage for `UT1.42`.
  Requirements: FR1.7
UT1.43 - Executable coverage for `UT1.43`.
  Requirements: FR1.14
UT1.44 - Executable coverage for `UT1.44`.
  Requirements: FR1.7, FR1.25
UT1.90 - Executable coverage for `UT1.90`.
  Requirements: CS1.3, NF1.5
UT1.91 - Executable coverage for `UT1.91`.
  Requirements: CS1.1
UT1.92 - Executable coverage for `UT1.92`.
  Requirements: NF1.6
UT1.93 - Executable coverage for `UT1.93`.
  Requirements: NF1.6
UT1.95 - Executable coverage for `UT1.95`.
  Requirements: NF1.6
UT1.96 - Executable coverage for `UT1.96`.
  Requirements: FR1.3
UT1.97 - Executable coverage for `UT1.97`.
  Requirements: NF1.6
UT1.98 - Executable coverage for `UT1.98`.
  Requirements: NF1.6
UT1.99 - Executable coverage for `UT1.99`.
  Requirements: FR1.5, FR1.11
UT1.100 - Executable coverage for `UT1.100`.
  Requirements: NF1.6
UT1.101 - Executable coverage for `UT1.101`.
  Requirements: FR1.7, FR1.11
UT1.102 - Executable coverage for `UT1.102`.
  Requirements: NF1.6
UT1.131 - Executable coverage for `UT1.131`.
  Requirements: FR1.43, CS1.1
UT1.132 - Executable coverage for `UT1.132`.
  Requirements: FR1.6, FR1.43
UT1.138 - Executable coverage for `UT1.138` (W28A-729-R5 expert flat WebUI roles: admin/read-write/read-only via installed cloud_dog_idam.RBACEngine, fail-closed normalise, read-only write-gate, 738-decoupled baseline, flat-aware PS-76 job perms).
  Requirements: FR1.6, FR1.43
UT1.103 - Executable coverage for `UT1.103` (prompt store delegation; catalogued by W28A-729-R5 traceability hygiene — test owner W28C-1704).
  Requirements: FR1.6
UT1.130 - Executable coverage for `UT1.130` (code-runner A2A; catalogued by W28A-729-R5 traceability hygiene — test owner W28C-1704).
  Requirements: FR1.7, CS1.1
UT1.133 - Executable coverage for `UT1.133` (expert execute audit; catalogued by W28A-729-R5 traceability hygiene — test owner W28C-1704).
  Requirements: FR1.6, CS1.1
UT1.134 - Executable coverage for `UT1.134` (expert tools access control; catalogued by W28A-729-R5 traceability hygiene — test owner W28C-1704).
  Requirements: FR1.6
UT1.135 - Executable coverage for `UT1.135` (outbound service credentials; catalogued by W28A-729-R5 traceability hygiene — test owner W28C-1704).
  Requirements: CS1.1
UT1.136 - Executable coverage for `UT1.136` (health probes; catalogued by W28A-729-R5 traceability hygiene — test owner W28C-1704).
  Requirements: NF1.6
UT1.137 - Executable coverage for `UT1.137` (service create enabled; catalogued by W28A-729-R5 traceability hygiene — test owner W28C-1704).
  Requirements: FR1.2
ST1.1 - Executable coverage for `ST1.1`.
  Requirements: SV1.1, FR1.7
ST1.2 - Executable coverage for `ST1.2`.
  Requirements: FR1.7, FR1.24, FR1.25
ST1.3 - Executable coverage for `ST1.3`.
  Requirements: FR1.2, FR1.7
ST1.4 - Executable coverage for `ST1.4`.
  Requirements: FR1.8, FR1.21, FR1.22, FR1.43, UC1.33
ST1.5 - Executable coverage for `ST1.5`.
  Requirements: FR1.2, FR1.7, FR1.8
ST1.6 - Executable coverage for `ST1.6`.
  Requirements: NF1.2
ST1.7 - Executable coverage for `ST1.7`.
  Requirements: NF1.8
ST1.8 - Executable coverage for `ST1.8`.
  Requirements: FR1.2
ST1.9 - Executable coverage for `ST1.9`.
  Requirements: FR1.5
ST1.10 - Executable coverage for `ST1.10`.
  Requirements: FR1.2
ST1.11 - Executable coverage for `ST1.11`.
  Requirements: FR1.3
ST1.12 - Executable coverage for `ST1.12`.
  Requirements: FR1.3
ST1.17 - Executable coverage for `ST1.17`.
  Requirements: FR1.9, CS1.4
ST1.18 - Executable coverage for `ST1.18`.
  Requirements: FR1.11
ST1.19 - Executable coverage for `ST1.19`.
  Requirements: FR1.11
ST1.20 - Executable coverage for `ST1.20`.
  Requirements: FR1.11
ST1.21 - Executable coverage for `ST1.21`.
  Requirements: FR1.11
ST1.26 - Executable coverage for `ST1.26`.
  Requirements: FR1.7
ST1.27 - Executable coverage for `ST1.27`.
  Requirements: NF1.6
ST1.28 - Executable coverage for `ST1.28`.
  Requirements: NF1.6
ST1.29 - Executable coverage for `ST1.29`.
  Requirements: NF1.6
ST1.30 - Executable coverage for `ST1.30`.
  Requirements: NF1.6
ST1.31 - Executable coverage for `ST1.31`.
  Requirements: NF1.6
ST1.32 - Executable coverage for `ST1.32`.
  Requirements: NF1.6
ST1.33 - Executable coverage for `ST1.33`.
  Requirements: NF1.6
ST1.34 - Executable coverage for `ST1.34`.
  Requirements: NF1.6
ST1.35 - Executable coverage for `ST1.35`.
  Requirements: NF1.6
ST1.36 - Executable coverage for `ST1.36`.
  Requirements: NF1.6
ST1.37 - Executable coverage for `ST1.37`.
  Requirements: NF1.6
ST1.38 - Executable coverage for `ST1.38`.
  Requirements: NF1.6
ST1.39 - Executable coverage for `ST1.39`.
  Requirements: NF1.6
ST1.40 - Executable coverage for `ST1.40`.
  Requirements: NF1.6
ST1.41 - Executable coverage for `ST1.41`.
  Requirements: NF1.6
ST1.42 - Executable coverage for `ST1.42`.
  Requirements: NF1.6
ST1.43 - Executable coverage for `ST1.43`.
  Requirements: NF1.6
ST1.44 - Executable coverage for `ST1.44`.
  Requirements: NF1.6
ST1.45 - Executable coverage for `ST1.45`.
  Requirements: FR1.13
ST1.46 - Executable coverage for `ST1.46`.
  Requirements: NF1.6
ST1.47 - Executable coverage for `ST1.47`.
  Requirements: NF1.6
ST1.61 - Executable coverage for `ST1.61`.
  Requirements: NF1.6
ST1.98 - Executable coverage for `ST1.98`.
  Requirements: NF1.6
ST1.99 - Executable coverage for `ST1.99`.
  Requirements: NF1.6
IT2.1 - Executable coverage for `IT2.1`.
  Requirements: FR1.3
IT2.3 - Executable coverage for `IT2.3`.
  Requirements: FR1.7, FR1.24
IT2.4 - Executable coverage for `IT2.4`.
  Requirements: FR1.1, FR1.3, FR1.7, NF1.6
IT2.5 - Executable coverage for `IT2.5`.
  Requirements: FR1.2, FR1.7, FR1.8, FR1.24, FR1.25, UC1.32
IT2.6 - Executable coverage for `IT2.6`.
  Requirements: FR1.1, FR1.3, NF1.6
IT2.7 - Executable coverage for `IT2.7`.
  Requirements: FR1.1, FR1.3, FR1.7, NF1.6
IT2.8 - Executable coverage for `IT2.8`.
  Requirements: FR1.26, UC1.20
IT2.17 - Executable coverage for `IT2.17`.
  Requirements: FR1.43
IT2.20 - Executable coverage for `IT2.20`.
  Requirements: UC1.29
IT2.21 - Executable coverage for `IT2.21`.
  Requirements: NF1.6
IT2.22 - Executable coverage for `IT2.22`.
  Requirements: NF1.6
IT2.23 - Executable coverage for `IT2.23`.
  Requirements: NF1.6
IT2.24 - Executable coverage for `IT2.24`.
  Requirements: NF1.6
IT2.25 - Executable coverage for `IT2.25`.
  Requirements: NF1.6
IT2.26 - Executable coverage for `IT2.26`.
  Requirements: NF1.6
IT2.27 - Executable coverage for `IT2.27`.
  Requirements: NF1.6
IT2.28 - Executable coverage for `IT2.28`.
  Requirements: NF1.6
IT2.29 - Executable coverage for `IT2.29`.
  Requirements: NF1.6
IT2.30 - Executable coverage for `IT2.30`.
  Requirements: NF1.6
IT2.31 - Executable coverage for `IT2.31`.
  Requirements: UC1.12, UC1.23
IT2.32 - Executable coverage for `IT2.32`.
  Requirements: NF1.6
IT2.33 - Executable coverage for `IT2.33`.
  Requirements: NF1.6
IT2.34 - Executable coverage for `IT2.34`.
  Requirements: NF1.6
IT2.35 - Executable coverage for `IT2.35`.
  Requirements: NF1.6
IT2.36 - Executable coverage for `IT2.36`.
  Requirements: NF1.6
IT2.37 - Executable coverage for `IT2.37`.
  Requirements: NF1.6
IT2.38 - Executable coverage for `IT2.38`.
  Requirements: FR1.2
IT2.39 - Executable coverage for `IT2.39`.
  Requirements: NF1.6
IT2.40 - Executable coverage for `IT2.40`.
  Requirements: NF1.6
IT2.41 - Executable coverage for `IT2.41`.
  Requirements: NF1.6
IT2.42 - Executable coverage for `IT2.42`.
  Requirements: FR1.7, FR1.11
IT2.43 - Executable coverage for `IT2.43`.
  Requirements: NF1.6
AT1.1 - Executable coverage for `AT1.1`.
  Requirements: FR1.5, UC1.1, UC1.2, CS1.1
AT1.2 - Executable coverage for `AT1.2`.
  Requirements: FR1.2, FR1.7
AT1.3 - Executable coverage for `AT1.3`.
  Requirements: FR1.1, FR1.12
AT1.4 - Executable coverage for `AT1.4`.
  Requirements: FR1.3, FR1.5
AT1.5 - Executable coverage for `AT1.5`.
  Requirements: FR1.5, FR1.27
AT1.6 - Executable coverage for `AT1.6`.
  Requirements: FR1.10
AT1.7 - Executable coverage for `AT1.7`.
  Requirements: FR1.2, CS1.4, NF1.8
AT1.8 - Executable coverage for `AT1.8`.
  Requirements: FR1.1, FR1.2, FR1.7
AT1.9 - Executable coverage for `AT1.9`.
  Requirements: FR1.2, FR1.3
AT1.10 - Executable coverage for `AT1.10`.
  Requirements: FR1.2, FR1.3
AT1.11 - Executable coverage for `AT1.11`.
  Requirements: FR1.2, FR1.3, FR1.7, FR1.24, FR1.26, FR1.27, FR1.28, FR1.29, FR1.30, UC1.2
AT1.12 - Executable coverage for `AT1.12`.
  Requirements: FR1.2, FR1.3, FR1.7, FR1.10, FR1.11
AT1.13 - Executable coverage for `AT1.13`.
  Requirements: FR1.2, FR1.10, FR1.11, FR1.12, UC1.6
AT1.14 - Executable coverage for `AT1.14`.
  Requirements: FR1.5
AT1.15 - Executable coverage for `AT1.15`.
  Requirements: FR1.1, FR1.12, NF1.1
AT1.16 - Executable coverage for `AT1.16`.
  Requirements: FR1.1, FR1.4, FR1.12, NF1.1
AT1.17 - Executable coverage for `AT1.17`.
  Requirements: FR1.3, NF1.1
AT1.18 - Executable coverage for `AT1.18`.
  Requirements: FR1.10, NF1.1
AT1.19 - Executable coverage for `AT1.19`.
  Requirements: FR1.9, NF1.2
AT1.20 - Executable coverage for `AT1.20`.
  Requirements: FR1.9, NF1.2
AT1.21 - Executable coverage for `AT1.21`.
  Requirements: FR1.9, NF1.2
AT1.22 - Executable coverage for `AT1.22`.
  Requirements: FR1.9, FR1.26, UC1.20, NF1.2
AT1.23 - Executable coverage for `AT1.23`.
  Requirements: FR1.9, NF1.2
AT1.24 - Executable coverage for `AT1.24`.
  Requirements: FR1.9, NF1.2
AT1.25 - Executable coverage for `AT1.25`.
  Requirements: CM1.1, FR1.9, NF1.5
AT1.26 - Executable coverage for `AT1.26`.
  Requirements: FR1.9, NF1.2
AT1.27 - Executable coverage for `AT1.27`.
  Requirements: FR1.9, NF1.2
AT1.28 - Executable coverage for `AT1.28`.
  Requirements: FR1.11, CS1.1
AT1.29 - Executable coverage for `AT1.29`.
  Requirements: FR1.6, FR1.11, CS1.1
AT1.30 - Executable coverage for `AT1.30`.
  Requirements: FR1.7, CS1.1
AT1.31 - Executable coverage for `AT1.31`.
  Requirements: CS1.3, NF1.5
AT1.32 - Executable coverage for `AT1.32`.
  Requirements: CS1.3, NF1.1
AT1.33 - Executable coverage for `AT1.33`.
  Requirements: CS1.1, CS1.4
AT1.34 - Executable coverage for `AT1.34`.
  Requirements: CS1.1, CS1.2
AT1.35 - Executable coverage for `AT1.35`.
  Requirements: FR1.5, CS1.1
AT1.40 - Executable coverage for `AT1.40`.
  Requirements: NF1.6
AT1.41 - Executable coverage for `AT1.41`.
  Requirements: NF1.6
AT1.42 - Executable coverage for `AT1.42`.
  Requirements: FR1.41
AT1.43 - Executable coverage for `AT1.43`.
  Requirements: NF1.6
AT1.44 - Executable coverage for `AT1.44`.
  Requirements: FR1.15, UC1.9
AT1.45 - Executable coverage for `AT1.45`.
  Requirements: NF1.6
AT1.46 - Executable coverage for `AT1.46`.
  Requirements: NF1.6
AT1.47 - Executable coverage for `AT1.47`.
  Requirements: NF1.6
AT1.48 - Executable coverage for `AT1.48`.
  Requirements: NF1.6
AT1.49 - Executable coverage for `AT1.49`.
  Requirements: NF1.6
AT1.55 - Executable coverage for `AT1.55`.
  Requirements: FR1.12, UC1.6
AT1.56 - Executable coverage for `AT1.56`.
  Requirements: FR1.12, UC1.6
AT1.57 - Executable coverage for `AT1.57`.
  Requirements: FR1.12, UC1.6, UC1.22
AT1.58 - Executable coverage for `AT1.58`.
  Requirements: NF1.6
AT1.59 - Executable coverage for `AT1.59`.
  Requirements: NF1.6
AT1.60 - Executable coverage for `AT1.60`.
  Requirements: NF1.6
AT1.91 - Executable coverage for `AT1.91`.
  Requirements: FR1.21, UC1.15
AT1.92 - Executable coverage for `AT1.92`.
  Requirements: FR1.22, UC1.16
AT1.93 - Executable coverage for `AT1.93`.
  Requirements: FR1.23, UC1.17
AT1.94 - Executable coverage for `AT1.94`.
  Requirements: FR1.8, FR1.21, FR1.35, FR1.36, FR1.43
AT1.95 - Executable coverage for `AT1.95`.
  Requirements: FR1.16, FR1.19, UC1.13
AT1.96 - Executable coverage for `AT1.96`.
  Requirements: FR1.20, UC1.14
AT1.97 - Executable coverage for `AT1.97`.
  Requirements: UC1.19
AT1.98 - Executable coverage for `AT1.98`.
  Requirements: NF1.6
AT1.99 - Executable coverage for `AT1.99`.
  Requirements: UC1.21
AT1.100 - Executable coverage for `AT1.100`.
  Requirements: NF1.6
AT1.101 - Executable coverage for `AT1.101`.
  Requirements: FR1.42, UC1.31
AT1.102 - Executable coverage for `AT1.102`.
  Requirements: UC1.28
AT1.103 - Executable coverage for `AT1.103`.
  Requirements: FR1.31, UC1.26
AT1.104 - Executable coverage for `AT1.104`.
  Requirements: FR1.32, UC1.8, UC1.27
AT1.114 - Executable coverage for `AT1.114`.
  Requirements: FR1.34, UC1.30
AT1.115 - Executable coverage for `AT1.115`.
  Requirements: FR1.17, UC1.11, UC1.18
AT1.116 - Executable coverage for `AT1.116`.
  Requirements: UC1.7
AT1.117 - Executable coverage for `AT1.117`.
  Requirements: NF1.6
AT1.118 - Executable coverage for `AT1.118`.
  Requirements: FR1.3
AT1.119 - Executable coverage for `AT1.119`.
  Requirements: FR1.2, FR1.3, UC1.2
AT1.120 - Executable coverage for `AT1.120`.
  Requirements: FR1.2, FR1.7
AT1.121 - Executable coverage for `AT1.121`.
  Requirements: FR1.2, FR1.10, FR1.11
AT1.122 - Executable coverage for `AT1.122`.
  Requirements: NF1.4
AT1.123 - Executable coverage for `AT1.123`.
  Requirements: UC1.10
AT1.124 - Executable coverage for `AT1.124`.
  Requirements: NF1.6
AT1.125 - Executable coverage for `AT1.125`.
  Requirements: NF1.6
AT1.126 - Executable coverage for `AT1.126`.
  Requirements: FR1.42, UC1.31
QT1.98 - Executable coverage for `QT1.98`.
  Requirements: NF1.6
QT1.99 - Executable coverage for `QT1.99`.
  Requirements: NF1.6
UT1.139 - Executable coverage for `UT1.139` (session sharing group access, summary consolidation, session state history; W28E-1809B Stream-B).
  Requirements: FR1.27, FR1.2, FR1.7
UT1.140 - Executable coverage for `UT1.140` (file upload admin-only gate, quality feedback authentication; W28E-1809B Stream-B).
  Requirements: FR1.13, FR1.30
IT2.43 - Executable coverage for `IT2.43` (IDAM negative + group-share live-revoke cascade through API/MCP; W28E-1809B Stream-B).
  Requirements: FR1.27, CS1.1

## 2. Coverage map

Mandatory 10-column schema per PS-REQ-TEST-TRACE v1.0 §4.2. The per-test catalogue below will be populated by operator-driven Instruction 4 work that binds @pytest.mark.req() decorators to specific REQ-IDs. Until then, all tests carry @pytest.mark.probe (KEEP-AS-PROBE disposition per PS-REQ-TEST-TRACE §7).

| Test ID | Tier | Use case | Requirement | Surface | Scenario | Variants | Env files | Known issue | Last run commit |
|---|---|---|---|---|---|---|---|---|---|


<!-- W28C-1710b design-delta additions (2026-06-14T18:01:23Z) -->

## W28C-1710b design-delta — planned tests catalogue (T-TST v1.1 10-col schema)

Per T-TST v1.1, the planned tests catalogue carries 10 columns: `test-id | tier | use-case | requirement | surface | scenario | variants | env-files | known-issue | last-run-commit`. Test binding (replacement of probe markers with `@pytest.mark.req("FR-NNN")`) is W28C-1711 work.

Consolidation rules (per W28C-1711):

1. One primary test per FR-NNN; variants via `pytest.parametrize`.
2. Common scenarios (login, RBAC matrix, anon-denied) in `tests/helpers/`.
3. Cross-surface FR uses parametrized test file; not duplicate files.
4. Every `surface: webui` FR has a Playwright test (cookie-login + RBAC matrix + screenshot + DOM-assert + console-error-gate + CW-pattern).
5. Every `surface: api|mcp|a2a` FR has a protocol-level test.
6. Every `CS-NNN` binds to `@pytest.mark.negative` test with expected denial code.
7. CRUD-applicable entities have C/R/U/D coverage.
8. Orphan retirement requires knowledge-extract worksheet.

## W28E-1809A probe-rebind record

All 33 residual orphan markers left by the W28C-1711-R3 cleanup are replaced with semantic `@pytest.mark.req(...)` bindings (zero orphan markers remain in `tests/`):

| Test file(s) | Count | Rebound to | Rationale |
|---|---|---|---|
| `tests/quality/QT_COMPLIANCE/test_qt_package_adoption.py` | 8 | `NF-001` | platform-package adoption conformance |
| `tests/quality/QT_COMPLIANCE/test_qt_vault_config_contract.py` | 6 | `NF-002` | config & secret-handling conformance |
| `tests/quality/QT_COMPLIANCE/test_qt_migration_completeness.py` | 4 | `NF-003` | platform-migration completeness |
| `tests/quality/QT_COMPLIANCE/test_qt_rules_compliance.py` | 7 | `NF-004` | RULES.md / platform-standards compliance |
| `tests/quality/QT_COMPLIANCE/test_qt_traceability.py` | 5 | `NF-005` | requirement↔test↔code traceability conformance |
| `tests/application/AT1.102_ResponseQualityEvaluation/…`, `tests/system/ST1.39_…`, `tests/integration/IT2.32_…` | 3 | `FR-023` | response-quality evaluation/scoring |

No probe became a TEST-DESIGN-TODO: every residual marker mapped to a real requirement (NF-001..005 standards-conformance rows added to REQUIREMENTS.md §Non-Functional Standards-Conformance, FR-023 Response Quality Evaluation).
## Expert Agent WebUI TEST-DESIGN rows (EA-01..EA-129 — W28E-1809A, Stream-C drive-out)

One AT TEST-DESIGN row per Variant-V2 WebUI feedback item, giving Stream-C explicit Playwright drive-out targets (PS-WEBUI-STYLE-COMPONENTS WSC-017). These are design rows (not yet executable); Stream-C implements and runs them.

| test-id | tier | use-case | requirement | surface | scenario | variants | env-files | known-issue | last-run-commit |
|---|---|---|---|---|---|---|---|---|---|
| `T-AT-EA-01` | AT | `UC-033` | `FR-018` | `webui` | Expert agent MUST use Jobs to manage multiple concurrent async expert/tool/channel runs, a… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-02` | AT | `UC-033` | `FR-018` | `webui` | Brand: page chrome / nav must show **Expert Agent** (two words, capitalised), not "experta… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-03` | AT | `UC-005` | `FR-033` | `webui` | Build-info: dashboard shows `v0.1.0` — must update from build metadata, not hard-coded. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-04` | AT | `UC-005` | `FR-033` | `webui` | API status indicator shows **Amber** with no underlying cause exposed — wire to real healt… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-05` | AT | `UC-005` | `FR-033` | `webui` | Memory tile reads `0` — must show real memory metric. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-06` | AT | `UC-005` | `FR-033` | `webui` | CPU tile reads `0` — must show real CPU metric. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-07` | AT | `UC-005` | `FR-033` | `webui` | Remove dashboard quick-links "Open Chat / Users / Monitoring / API Docs" — duplicates of n… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-08` | AT | `UC-005` | `FR-005` | `webui` | Audit refresh: add an enable/disable toggle for auto-refresh. **Apply across ALL audit Dat… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-09` | AT | `UC-005` | `FR-014` | `webui` | Log Source drop-down (good here) — replicate this pattern across all 9 projects and consol… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-10` | AT | `UC-005` | `FR-033` | `webui` | Recent Activity: multi-select rows + download as JSON or CSV. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-11` | AT | `UC-005` | `FR-033` | `webui` | Remove "Dashboard Contract Surface" panel from dashboard. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-12` | AT | `UC-005` | `FR-032` | `webui` | Move "About" out of body content into top nav + login-profile menu. — cross-cutting (recur… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-13` | AT | `UC-005` | `FR-033` | `webui` | Footer `© 2026 Cloud-Dog, Viewdeck Engineering Limited` appears twice — dedup; align to pl… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-14` | AT | `UC-033` | `FR-032` | `webui` | Re-order primary nav: **Experts, Channels, Chat, Sessions, Services, …** | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-15` | AT | `UC-003` | `FR-004` | `webui` | OpenAI-shaped models (e.g. `ibm/granite` on `llm1`) must be addable through the WebUI; no … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-16` | AT | `UC-003` | `FR-004` | `webui` | Edit / Add Expert: model selection must be a pick-list (not free-text). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-17` | AT | `UC-003` | `FR-004` | `webui` | Edit / Add Expert: expose key LLM params — Top-K, Temperature, Max Tokens. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-18` | AT | `UC-003` | `FR-004` | `webui` | System Prompt field is missing from Expert edit — must be present with a default. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-19` | AT | `UC-003` | `FR-010` | `webui` | **Shared component gap**: `EntityForm` does not support textarea / template-editor fields,… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-20` | AT | `UC-003` | `FR-004` | `webui` | Channels, Services, Sub-Experts pickers on Expert form must be **multi-select dropdowns**. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-21` | AT | `UC-003` | `FR-004` | `webui` | Add a "Test LLM / model" action on Expert form so the user can verify model wiring inline. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-22` | AT | `UC-003` | `FR-004` | `webui` | "Add Service" must move from in-page box to a pop-up multi-select dialog. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-23` | AT | `UC-003` | `FR-004` | `webui` | Remove "Expert Contract Service" panel from the page. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-24` | AT | `UC-003` | `FR-004` | `webui` | Service bindings: zero bindings shown, can't add any — needs the EA-22 multi-select. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-25` | AT | `UC-003` | `FR-004` | `webui` | "Test Query" must move to a pop-up; improve presentation of `Linked knowledge: 0; total pr… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-26` | AT | `UC-003` | `FR-004` | `webui` | "Add Sub-Agent" must move to a pop-up and be reachable from the Add/Edit/View Expert flow. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-27` | AT | `UC-003` | `FR-004` | `webui` | Providers: surface providers either as a page or as part of Settings; from a provider you … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-28` | AT | `UC-003` | `FR-004` | `webui` | "View History" for an expert: click-through to the audit/logs page with the expert filter … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-29` | AT | `UC-015` | `FR-007` | `webui` | Add a "View Channel" action (currently missing). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-30` | AT | `UC-015` | `FR-007` | `webui` | Add a "View Messages / History" for a channel. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-31` | AT | `UC-015` | `FR-007` | `webui` | Edit / Add Channel: Expert list is squashed. Channel "type" is locked to chat — must also … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-32` | AT | `UC-015` | `FR-007` | `webui` | Remove "Channel Contract Surface" panel (this belongs in the Swagger/OpenAPI docs page). —… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-33` | AT | `UC-015` | `FR-007` | `webui` | Channel detail must expose history + messages: thinking, responses, timings; ability to te… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-34` | AT | `UC-015` | `FR-007` | `webui` | Channel "View History" click-through to audit/logs filtered by channel. (consistency with … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-35` | AT | `UC-001` | `FR-013` | `webui` | Remove Sessions / Channels / Experts / Tool-calls boxes at the top of the page. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-36` | AT | `UC-001` | `FR-013` | `webui` | Conversation Workbench is the main feature — must be **full width / main prominence**. Bel… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-37` | AT | `UC-001` | `FR-013` | `webui` | From `/chat` you must be able to jump to the Expert page and the Knowledge page; on select… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-38` | AT | `UC-001` | `FR-013` | `webui` | Message timeline layout: user labels on the **right**, assistant (expert name) on the **le… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-39` | AT | `UC-001` | `FR-013` | `webui` | While "Latest Response" is in flight, show a ticking clock / in-progress indicator against… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-40` | AT | `UC-001` | `FR-013` | `webui` | "Tool Calls: 0" tile looks wrong — drive from real data. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-41` | AT | `UC-001` | `FR-013` | `webui` | Tool-call panel currently just copies the request — replace with a per-message icon that o… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-42` | AT | `UC-001` | `FR-013` | `webui` | Remove "Session snapshot" from `/chat` — this content belongs on `/sessions`. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-43` | AT | `UC-001` | `FR-013` | `webui` | Remove "Chat contract surface" panel. (consistency with EA-32 cross-cutting). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-44` | AT | `UC-001` | `FR-013` | `webui` | "View Timeline" must navigate to `/chat` with the right Expert + Knowledge + Session selec… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-45` | AT | `UC-001` | `FR-013` | `webui` | Remove "Session / Active / Exports" blocks and "Session contract surface". | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-46` | AT | `UC-001` | `FR-013` | `webui` | Remove per-row "Detail" — "View Messages" should take you to `/chat`. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-47` | AT | `UC-001` | `FR-013` | `webui` | Session "View History" click-through to audit/logs filtered by session. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-48` | AT | `UC-026` | `FR-027` | `webui` | Remove the `Entries 181 / Linked experts / Scopes` summary strip. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-49` | AT | `UC-026` | `FR-027` | `webui` | Clarify Knowledge ID semantics — currently shows `1`; should be a GUID. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-50` | AT | `UC-026` | `FR-027` | `webui` | Bottom-of-screen "linked experts" pick box is not relevant — remove. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-51` | AT | `UC-026` | `FR-027` | `webui` | Edit/Add Knowledge missing: knowledge type (chroma, qdrant, …), knowledge parameters, inge… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-52` | AT | `UC-026` | `FR-027` | `webui` | Ability to select + import / reuse an existing knowledge from one of the sources. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-53` | AT | `UC-026` | `FR-027` | `webui` | Remove "Knowledge contract surface". | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-54` | AT | `UC-026` | `FR-027` | `webui` | Knowledge admin page: prune, view all collections, remove items, select + search for entit… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-55` | AT | `UC-026` | `FR-027` | `webui` | Knowledge "View History" click-through to audit/logs filtered by knowledge. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-56` | AT | `UC-026` | `FR-027` | `webui` | Knowledge list: expose type + size columns. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-57` | AT | `UC-010` | `FR-011` | `webui` | Remove `Services 69 / Healthy 15 / Bound experts` summary strip. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-58` | AT | `UC-010` | `FR-011` | `webui` | On page load, async-run a health check against each service; show enabled/disabled toggle … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-59` | AT | `UC-010` | `FR-011` | `webui` | Per-row "Detail" currently does nothing — wire it. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-60` | AT | `UC-010` | `FR-011` | `webui` | Edit Service: Service Type must be a pick-list. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-61` | AT | `UC-010` | `FR-011` | `webui` | Edit Service: Endpoint URL must be testable once well-formed; once tested, auto-detect end… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-62` | AT | `UC-010` | `FR-011` | `webui` | Edit Service: improve Auth Config JSON UX — add Bearer / `X-API-Token` / other presets. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-63` | AT | `UC-010` | `FR-011` | `webui` | Improve Metadata JSON UX (cross-links existing CC-18 schema-aware editor). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-64` | AT | `UC-010` | `FR-011` | `webui` | Remove nonsense "Available Experts" block from the bottom of Register Service. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-65` | AT | `UC-010` | `FR-011` | `webui` | Add other settings to Service: tools available, RBAC (who can use it). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-66` | AT | `UC-010` | `FR-011` | `webui` | Health Check / Response should be a pop-up, not in-page. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-67` | AT | `UC-010` | `FR-011` | `webui` | Remove "Service composition contract surface". | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-68` | AT | `UC-010` | `FR-011` | `webui` | Service "View History" click-through to logs filtered by service. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-69` | AT | `UC-030` | `FR-026` | `webui` | Replace flat list with a file-tree UI widget. **Re-use the folder/file layout + functional… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-70` | AT | `UC-030` | `FR-026` | `webui` | Buttons layout is poor — align to platform UI standards. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-71` | AT | `UC-030` | `FR-026` | `webui` | Remove "Files Storage Objects" panel. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-72` | AT | `UC-030` | `FR-026` | `webui` | Storage Bytes tile reads `0` — wire to real storage usage. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-73` | AT | `UC-030` | `FR-026` | `webui` | Show what + where the storage is (URI). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-74` | AT | `UC-030` | `FR-026` | `webui` | Metadata: pop-up + friendly display (not raw JSON); remove metadata sub-panel. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-75` | AT | `UC-030` | `FR-026` | `webui` | Ingest flow: Knowledge picker must be a pick-list; expose ingest options (how, parameters,… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-76` | AT | `UC-030` | `FR-026` | `webui` | Knowledge ingest must run as an async Job; File row must show "pending import" status; Kno… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-77` | AT | `UC-030` | `FR-026` | `webui` | "Ingest file" pop-up layout (with stray "selected file" at bottom) needs total redesign. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-78` | AT | `UC-030` | `FR-026` | `webui` | Add a File viewer (click to view). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-79` | AT | `UC-030` | `FR-026` | `webui` | Add folder navigation. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-80` | AT | `UC-030` | `FR-026` | `webui` | File times must use Moment format (cross-links existing CC-08). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-81` | AT | `UC-009` | `FR-010` | `webui` | Tightly couple Prompts to Experts: use/add/see prompts related to experts; click a prompt … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-82` | AT | `UC-009` | `FR-010` | `webui` | Remove `Templates 42 / Generated cases 0 / Validation score N/A / Prompt valid` strip. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-83` | AT | `UC-009` | `FR-010` | `webui` | Move Prompt Workbench to the bottom of the screen; generation only meaningful with a conte… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-84` | AT | `UC-009` | `FR-010` | `webui` | "Validate Prompt" does nothing; "Generate test cases" has no context input — needs a conte… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-85` | AT | `UC-009` | `FR-010` | `webui` | Create Prompt: same `EntityForm` multiline gap as EA-19 — fix in `cloud-dog-ai-ui-monorepo… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-86` | AT | `UC-009` | `FR-010` | `webui` | Edit Prompt: provide easy insertion of available variables (driven by context). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-87` | AT | `UC-009` | `FR-010` | `webui` | Redesign prompt-engineering workflow: given Channel + Expert + Knowledge + description + o… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-88` | AT | `UC-009` | `FR-010` | `webui` | Clarify "Updated" column semantics. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-89` | AT | `UC-009` | `FR-010` | `webui` | "Generated test cases" possibly needs its own page once context model lands. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-90` | AT | `UC-009` | `FR-010` | `webui` | Remove "Prompt preview" until redesign is in place; remove "Prompt contract surface". | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-91` | AT | `UC-027` | `FR-018` | `webui` | Started and Duration columns have no values. (depends on PS-76 + EA-01). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-92` | AT | `UC-027` | `FR-018` | `webui` | Action buttons don't match other pages' UI — apply platform standards. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-93` | AT | `UC-027` | `FR-018` | `webui` | Job Detail: Status / Layout don't match design standards; Submitted By should be user-or-i… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-94` | AT | `UC-027` | `FR-018` | `webui` | Add a Resubmit button on Job Detail. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-95` | AT | `UC-027` | `FR-009` | `webui` | Expert Agent currently reports zero job failures — implausible; verify failure recording i… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-96` | AT | `UC-027` | `FR-018` | `webui` | Job Id is rendered as a blue box — use platform link/identifier style. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-97` | AT | `UC-027` | `FR-018` | `webui` | Remove "Job contract surface" panel. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-98` | AT | `UC-027` | `FR-018` | `webui` | "About" appears at the bottom of `/jobs` (3rd time noted, still not fixed across services)… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-99` | AT | `UC-004` | `FR-029` | `webui` | Create/Edit User screen must allow add/remove of Available Group. (cross-links existing CC… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-100` | AT | `UC-004` | `FR-029` | `webui` | Enable/Disable button not to platform standards — see EA-31 / consistent status pattern. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-101` | AT | `UC-004` | `FR-029` | `webui` | Remove "User contract surface". | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-102` | AT | `UC-004` | `FR-029` | `webui` | Add an Add-API-Key / Change-API-Key screen on User. (cross-links existing CC-15). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-103` | AT | `UC-021` | `FR-019` | `webui` | Remove `Groups / Enabled / Members in Selection` summary strip. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-104` | AT | `UC-021` | `FR-019` | `webui` | Edit/Create Group: CRUD on users (select + add + remove). (cross-links existing CC-14). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-105` | AT | `UC-021` | `FR-019` | `webui` | From Group, ability to add a new user (taken to user screen). | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-106` | AT | `UC-024` | `FR-012` | `webui` | API Key detail MUST show associated users / groups. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-107` | AT | `UC-024` | `FR-012` | `webui` | Create Key: must allow selecting + adding users / groups, and surface them on detail. (cro… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-108` | AT | `UC-024` | `FR-012` | `webui` | Roles list in API Keys is very short — confirm whether the full set is exposed. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-109` | AT | `UC-024` | `FR-012` | `webui` | Expiry shows "30 days" header but every row has no expiry — wire correctly. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-110` | AT | `UC-024` | `FR-012` | `webui` | Remove "API key contract surface". | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-111` | AT | `UC-024` | `FR-012` | `webui` | Shared `IdamApiKeysPage` `Number(form.owner)` bug breaks string-id API-key create for all … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-112` | AT | `UC-025` | `FR-030` | `webui` | Page layout broken — one row should be `User-or-Group + type + Role definition + bind acti… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-113` | AT | `UC-025` | `FR-030` | `webui` | "View Permissions" must be a pop-up, not a side panel. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-114` | AT | `UC-025` | `FR-030` | `webui` | **CRITICAL** — bindings to Expert / Channel / Knowledge are entirely missing. RBAC must su… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-115` | AT | `UC-025` | `FR-030` | `webui` | Clarify or remove "Group role overview" tacked on at the end. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-116` | AT | `UC-025` | `FR-030` | `webui` | Rethink the whole RBAC layout against the canonical platform RBAC standard. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-117` | AT | `UC-005` | `CS-009` | `webui` | Page is non-functional (403) — bring into line with other services' monitoring page. Must … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-118` | AT | `UC-005` | `FR-033` | `webui` | Remove "Monitoring contract surface". | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-119` | AT | `UC-018` | `FR-031` | `webui` | Page is broken / full of errors — must be consistent across all 9 projects per the guidanc… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-120` | AT | `UC-018` | `FR-031` | `webui` | Display all environment-variable settings in the API Docs section. **Apply across all 9 pr… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-121` | AT | `UC-016` | `FR-016` | `webui` | Functionality is covered by `/chat` — remove the page. | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-122` | AT | `UC-019` | `FR-031` | `mcp` | Apply the same standard as file-mcp / other services: when a tool is selected, show a JSON… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-123` | AT | `UC-019` | `FR-031` | `a2a` | Apply same feedback as other A2A consoles: list topics, prefill template with agent-card d… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-124` | AT | `UC-033` | `FR-032` | `webui` | Responses must be structured, not raw JSON. (PS-73 standard accepted W28K-1404e; adoption … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-125` | AT | `UC-033` | `CS-009` | `webui` | Page is blank/rubbish: `Request Health status: N/A`, `Queue depth: N/A failed with status … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-126` | AT | `UC-033` | `FR-032` | `webui` | Add About entry to the LHS menu — make consistent across services per platform standard (c… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-127` | AT | `UC-033` | `FR-032` | `webui` | Admin must surface Channels + Sub-agents + Services obviously connected (each sub-agent ha… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-128` | AT | `UC-004` | `FR-029` | `webui` | Profile pop-up: add reset / change password; add select-through to Expert / Channel / Sess… | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |
| `T-AT-EA-129` | AT | `UC-004` | `FR-029` | `webui` | Service name typography fix: `expert agent` → `Expert Agent` everywhere (consistency with … | admin/read-write/read-only/anon | `tests/env-AT` | Stream-C TEST-DESIGN (drive-out) | — |

<!-- W28E-1809C Stream-C: + tests/unit/UT1.141_WebUICanonicalUrls (WebUI URL canonicalisation, 39 tests). Monorepo apps/expert-agent Playwright: a11y.spec (22 canonical routes), w28e-1809c-canonical-urls.spec. -->
