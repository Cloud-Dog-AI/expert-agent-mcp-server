---
template-id: T-DMT
template-version: 1.0
applies-to: docs/DATA-MODEL.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

# document-side (per-project) — stamped at migration, refreshed by check-docs-conformance.sh
project: expert-agent-mcp-server
doc-last-updated: 2026-06-12
doc-git-commit: 23792217e632a149847f4be56af53e9b6b744c14
doc-git-branch: main
doc-source-shas: []
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-12T12:00:00Z
---

# expert-agent-mcp-server — DATA-MODEL

> **Template version:** T-DMT v1.0 — mandatory for every project (idam + jobs schemas alone meet the bar).

## 1. Purpose
Document every persisted data structure this project owns or extends.

## 2. IDAM schema (universal)
Every project participates in the IDAM principals/roles/api-keys model. Document any project-specific extensions (groups, scopes, role bindings).

| Table / collection | Purpose | Owned-by |
|---|---|---|
| `principals` | platform | cloud_dog_idam |
| `roles` | platform | cloud_dog_idam |
| `api_keys` | platform | cloud_dog_idam |
| `<service>_role_bindings` | local extension | this project |

## 3. Jobs schema (universal)
Every project participates in the platform jobs queue. Document any service-specific job types.

| Job type | Trigger | Payload schema | Retention |
|---|---|---|---|

## 4. Service-specific schema
**You MUST include:** every table, collection, file-layout, or message schema this service persists.

| Object | Storage | Schema | Notes |
|---|---|---|---|

## 5. Migrations
List of migrations applied; link to `migrations/` if used.

## 6. Cross-references
- PS-83-canonical-role-catalog.md
- packages/backend/platform-idam (idam owner)
- packages/backend/platform-jobs (jobs owner)

## 7. Project-specific notes
