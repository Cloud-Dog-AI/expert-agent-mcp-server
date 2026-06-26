---
template-id: T-AUD
template-version: 1.0
applies-to: docs/AUDIT-EVENTS.md
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

# Audit Events Catalogue

Project: expert-agent-mcp-server

| event_type | action | NIST category | Trigger | severity | Example JSON |
|---|---|---|---|---|---|
| auth | token_validate | Authentication | API key or JWT validation on request ingress | INFO | {"event_type":"auth","action":"token_validate","outcome":"success"} |
| user_function | request_execute | Object Access | User/API request execution path | INFO | {"event_type":"user_function","action":"request_execute","outcome":"success"} |
| system_function | dependency_call | System Change | Internal call to DB/MCP/LLM/external service | INFO | {"event_type":"system_function","action":"dependency_call","outcome":"success"} |
| admin_action | config_update | Privileged Use | Runtime configuration or policy change | WARNING | {"event_type":"admin_action","action":"config_update","outcome":"partial"} |
| data_access | read_write | Object Access | Read/write operation against managed data | INFO | {"event_type":"data_access","action":"read_write","outcome":"success"} |
