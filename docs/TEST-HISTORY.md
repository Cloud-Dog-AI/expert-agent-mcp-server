---
template-id: T-TSH
template-version: 1.0
applies-to: docs/TEST-HISTORY.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: expert-agent-mcp-server
doc-last-updated: 2026-06-12
doc-git-commit: 23792217e632a149847f4be56af53e9b6b744c14
doc-git-branch: main
doc-source-shas: []
doc-age-policy: indefinite
doc-conformance-stamp: 2026-06-12T12:00:00Z
---

# expert-agent-mcp-server — TEST-HISTORY

> **Template version:** T-TSH v1.0 — appended to by `scripts/update-test-state.py`. Roll-archive to `archive/test-history/<YYYY-MM>.md` when >500 lines.

## Runs (most recent first)

### 2026-06-17T11:09:50.672957+00:00
- Commit: `7797b95fbcd3673388f26132c2b4c7978a7e45ac` (W28C-1714-100pct-fix)
- Totals: 6 / P 6 / F 0 / S 0
- Delta: new-fails 0 | newly-green 166

### 2026-06-13T10:59:13.207362+00:00
- Commit: `e2b793dcc93491d28f5ed85ee51b3f1de53180d2` (main)
- Totals: 166 / P 0 / F 166 / S 0
- Delta: new-fails 166 | newly-green 90

### 2026-06-13T10:18:37.487046+00:00
- Commit: `e2b793dcc93491d28f5ed85ee51b3f1de53180d2` (main)
- Totals: 90 / P 0 / F 90 / S 0
- Delta: new-fails 90 | newly-green 0

### 2026-06-12T12:00:00Z
- Commit: `23792217e632a149847f4be56af53e9b6b744c14` (main)
- Totals: N / P n / F n / S n
- Delta: new-fails 0 | newly-green 0

## W28E-1809C — Stream-C WebUI/E2E/1.0RC01 (2026-06-23)

- UT1.141 WebUI URL canonicalisation: 39/39 PASS (legacy 308, canonical 200, WURL-007 404, WURL-008 retained).
- Monorepo Playwright (apps/expert-agent): smoke + canonical-urls + a11y green; axe wcag2aa 22/22 routes, 0 violations.
- Local-docker image canonical smoke: all legacy aliases 308->canonical, canonical 200 (03-local-docker-canonical-smoke.txt).
- Preprod (deployed sha256:a0ea85a2, version 0.1.1RC1): canonical URL audit green; 4-sentinel browser smoke PASS; sibling estate 9/9 healthy.
- Warranty gate ABC clean (A=111, B=47, C=236 PASS); traceability 0 fail/0 warn; confidentiality scrub clean.
