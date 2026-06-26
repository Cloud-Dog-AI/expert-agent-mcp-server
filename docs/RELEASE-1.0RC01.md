# expert-agent-mcp-server — 1.0RC01 Release Notes

Release: **1.0RC01** · Tag: `1.0RC01-expert-agent-mcp-server` · Lane: W28E-1809C (Stream-C WebUI/E2E/release)
Service version: `0.1.1RC1` · Deployed image digest: `sha256:290d9679f0e619db2ae968daa0372062c3094adca3236cc68b61afab8c0774d6`
Preprod: `https://expertagent0.cloud-dog.net` (server0.viewdeck.com /27 MLAgents · container `expertagent0`)

## Scope

W28E-1809C closes the expert-agent Stream-C WebUI/E2E milestone, consuming accepted
W28E-1809A (REQ/UC/TESTS-DESIGN) and W28E-1809B (functionality/UT/IT/ST/AT/preprod).

## Headline change — WebUI URL canonicalisation (PS-WEBUI-URL-CANONICAL v1.0)

The web tier now serves one canonical route per taxonomy page and 308-redirects every
legacy alias (previously the SPA served HTTP 200 for every path with no redirects):

- Canonical: `/login`, `/audit-log`, `/admin/{users,groups,api-keys,roles,rbac}`,
  `/developer/{api-docs,mcp-console,a2a-console}`, `/system/{jobs,settings,about}`.
- Legacy 308 → canonical: `/idam/*`→`/admin/*`, `/api-docs`→`/developer/api-docs`,
  `/mcp-console`/`/a2a-console`→`/developer/*`, `/jobs`/`/settings`/`/about`→`/system/*`,
  `/audit`/`/logs`→`/audit-log`.
- WURL-008: real Swagger/OpenAPI/ReDoc (`/docs`, `/openapi.json`, `/redoc`) retained.
- WURL-007: unknown WebUI routes return 404 (known-prefix gating); SPA nav links + the
  React router use canonical routes (WURL-009).
- Backend: `src/servers/web/server.py` (`canonical_webui_redirects` middleware).
  SPA: `cloud-dog-ai-ui-monorepo/apps/expert-agent` (canonical routes + nav).

## Other fixes

- **EA-03**: dashboard/health version now sourced from build metadata (`build-info.json`)
  instead of a hardcoded `0.1.0` (platform health router + OpenAPI). Deployed version `0.1.1RC1`.
- **EA-04**: dashboard API status indicator surfaces the underlying cause.
- **EA-13**: footer copyright contrast (a11y).
- **EA-91/92/93/94**: Jobs page Priority + Attempt columns, per-row Detail/Cancel/Retry/Delete
  actions, Copy JSON + Correlation-context in the detail dialog (PS-76).
- **a11y**: chat user-bubble timestamp contrast fixed; axe wcag2aa 0 violations across all 22
  canonical routes.
- **vite proxy** anchored RegExp keys so `/api`,`/mcp`,`/a2a` no longer swallow the
  `/api-docs`,`/mcp-console`,`/a2a-console` SPA routes (AGENT-LESSONS §2.4).

## Verification

- Local-docker image: canonical 308/200 + WURL-007 404 + WURL-008 retained (UT1.141 39/39).
- Preprod: deployed digest == built == registry (`290d9679…`); version `0.1.1RC1`; canonical URL
  audit green; anon `/api/sessions` 401; 4-sentinel browser smoke green; sibling estate 9/9 healthy.
- Warranty gate ABC clean (A=111, B=47, C=236 PASS); traceability 0 fail/0 warn; scrub clean.

## Notes

- All EA observation rows are CLOSED in the final W28E-1809C observation-closure matrix.
- `/apikeys` and `/api-keys` bare aliases are not Traefik-routed to the web tier on preprod
  (canonical `/admin/api-keys` + legacy `/idam/api-keys` work); middleware handles them locally.
