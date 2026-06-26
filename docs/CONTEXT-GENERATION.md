---
template-id: T-CTX
template-version: 1.0
applies-to: docs/CONTEXT-GENERATION.md
registry: service
required: conditional
when-applicable: "service builds LLM prompts from data"
template-last-updated: 2026-06-12
template-owner: platform-standards

project: expert-agent-mcp-server
doc-last-updated: 2026-06-12
doc-git-commit: 23792217e632a149847f4be56af53e9b6b744c14
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-12T12:00:00Z
---

# expert-agent-mcp-server — CONTEXT-GENERATION

> **Template version:** T-CTX v1.0 — how the service builds LLM context from data.

## 1. Sources
Data sources fed into context.

## 2. Pipeline
Stages from raw → tokenised context.

## 3. Token budget
Per-tier limits, truncation strategy.

## 4. Cross-references
- [PROMPTS.md](PROMPTS.md), [ARCHITECTURE.md](ARCHITECTURE.md)
