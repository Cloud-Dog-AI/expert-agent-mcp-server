---
template-id: T-DOK
template-version: 1.0
applies-to: docs/DOCKER.md
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

# Docker Guide

## Build
```bash
set -a; source ../env-vault; set +a
bash docker-build.sh latest
```

## Run
```bash
docker compose -f docker/docker-compose.yml --env-file tests/env-local-docker-server up --build
```

## Push
```bash
docker push <internal-registry>:443/cloud-dog/expert-agent-mcp-server:latest
```

## Compose Files
- `docker/docker-compose.yml`

## Notes
- Keep secrets out of committed compose files and environment examples.
- Use `docs/PREPROD.md` for the Terraform-backed preprod flow.
- Use `tests/env-local-docker-server` or `tests/env-AT-local-docker` as the local Docker env source, depending on the workflow under test.
