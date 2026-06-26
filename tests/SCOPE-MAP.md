# Test Scope Map — expert-agent-mcp-server

## Source to test mapping

| Source module | QT | UT | ST | IT | AT |
|--------------|----|----|----|----|-----|
| `src/core/session/manager.py` | — | `UT1.3_SessionManager`, `UT1.38_SessionQueuing` | `tests/system/ST*Session*` | `tests/integration/IT*Session*` | `AT1.2_SessionCreation`, `AT1.9_SessionHistory` |
| `src/core/llm/manager.py` | `tests/quality/QT*` | `UT1.7_LLMProviderAbstraction`, `UT1.8_LLMProvider` | `tests/system/ST*LLM*` | `tests/integration/IT*LLM*` | `AT1.101_LLMValidationTesting`, `AT1.44_AutoPromptGeneration` |
| `src/core/vector/manager.py` | — | `UT1.15_VectorStoreAbstraction`, `UT1.22_VectorLifecycle` | `tests/system/ST*Vector*` | `tests/integration/IT*Vector*` | `AT1.57_ChannelVectorStoreMappings`, `AT1.58_ChannelChatVectorStoreRAG`, `AT1.118_VectorStoreConfiguration` |
| `src/core/auth/user_manager.py` | `tests/quality/QT*` | `UT1.4_UserManager`, `UT1.25_AuthToken`, `UT1.27_RBAC` | `tests/system/ST*Auth*` | `tests/integration/IT*Auth*` | `AT1.1_UserAuth`, `AT1.15_GroupManagement`, `AT1.99_GroupAdminRoleManagement` |
| `src/core/knowledge/manager.py` | — | `UT1.21_IndexingSearch`, `UT1.93_KnowledgeVersioning` | `tests/system/ST*Knowledge*` | `tests/integration/IT*Knowledge*` | `AT1.40_KnowledgeVersioningRollback`, `AT1.114_FileStoreManagement` |
| `src/servers/api/server.py` | `tests/quality/QT*` | `UT1.31_ServerControlScript`, `UT1.32_ConfigLoader` | `tests/system/ST*API*` | `tests/integration/IT*API*` | `AT1.26_HealthCheckValidation`, `AT1.25_ConfigHierarchyEnforcement` |
| `src/core/audit/logger.py` | `tests/quality/QT_LoggingCompliance`, `tests/quality/QT_COMPLIANCE` | `UT_AuditLogFormat`, `UT1.29_AuditIntegrity` | `tests/system/ST_AuditLog` | `tests/integration/IT*Audit*` | `AT1.32_AuditTrailIntegrity` |
| `src/core/security/crypto.py` | `tests/quality/QT*` | `UT1.90_SecurityCrypto`, `UT1.91_AuthLockout` | `tests/system/ST*Security*` | `tests/integration/IT*Security*` | `AT1.31_DataEncryptionAtRest`, `AT1.33_InjectionProtection` |
| `src/**` (platform-package adoption / config / rules / traceability conformance) | `tests/quality/QT_COMPLIANCE` (`NF-001`..`NF-005`) | — | — | — | — |
| `src/core/quality/response_scoring.py` (response quality) | — | — | `tests/system/ST1.39_ResponseQualityScoring` | `tests/integration/IT2.32_ResponseQualityScoring` | `tests/application/AT1.102_ResponseQualityEvaluation` (`FR-023`) |

> **W28E-1809A:** the `QT_COMPLIANCE` tier is now bound to the canonical `NF-001`..`NF-005` standards-conformance rows (no orphan markers remain).

## Scoped run examples

If you changed `src/core/llm/manager.py`, run:

```bash
pytest tests/unit/UT1.7*/ tests/unit/UT1.8*/ tests/system/ST*LLM*/ tests/integration/IT*LLM*/ tests/application/AT1.44*/ tests/application/AT1.101*/ -v
```

If you changed `src/core/vector/manager.py`, run:

```bash
pytest tests/unit/UT1.15*/ tests/unit/UT1.22*/ tests/system/ST*Vector*/ tests/integration/IT*Vector*/ tests/application/AT1.57*/ tests/application/AT1.58*/ tests/application/AT1.118*/ -v
```

If you changed `src/servers/api/server.py`, run:

```bash
pytest tests/unit/UT1.31*/ tests/unit/UT1.32*/ tests/system/ST*API*/ tests/integration/IT*API*/ tests/application/AT1.25*/ tests/application/AT1.26*/ -v
```
