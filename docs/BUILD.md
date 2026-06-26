---
template-id: T-BLD
template-version: 1.0
applies-to: docs/BUILD.md
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

# BUILD.md — Expert Agent MCP Server

## 1. Prerequisites

- Linux/macOS shell with `bash`
- Python `3.10+`
- Docker + Docker Compose
- Access to Cloud-Dog private PyPI
- Vault bootstrap file: `../env-vault`

## 2. Virtual Environment Setup

```bash
cd ./expert-agent-mcp-server
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

## 3. Install Dependencies

```bash
.venv/bin/python -m pip install -e ".[dev]" --index-url https://your-package-index/simple/
```

If you need platform fallback index chaining:

```bash
.venv/bin/python -m pip install -e ".[dev]" \
  --index-url https://your-package-index/simple/ \
  --extra-index-url https://pypi.org/simple
```

## 4. Vault Environment Bootstrap

```bash
set -a; source ../env-vault; set +a
bash scripts/validate-vault.sh
```

## 5. Build Package

```bash
.venv/bin/python -m pip install build
.venv/bin/python -m build
```

Artifacts are generated under `dist/`.

## 6. Build Docker Image

Project helper:

```bash
bash docker-build.sh
```

Compose build:

```bash
docker compose build
```

## 7. Lint / Type Check / Static Gates

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy src
.venv/bin/python -m pytest tests/quality --env tests/env-QT -q
```

## 8. Test by Tier (Mandatory `--env`)

```bash
# Unit
.venv/bin/python -m pytest tests/unit --env tests/env-UT -q

# System
.venv/bin/python -m pytest tests/system --env tests/env-ST -q

# Integration
set -a; source ../env-vault; set +a
.venv/bin/python -m pytest tests/integration --env tests/env-IT -q

# Application
set -a; source ../env-vault; set +a
.venv/bin/python -m pytest tests/application --env tests/env-AT -q
```

## 9. Local Server Bring-up for ST/IT/AT

```bash
./server_control.sh --env tests/env-ST start all
./server_control.sh --env tests/env-ST status all
./server_control.sh --env tests/env-ST stop all
```

Use the tier-matching env file for each run (`env-ST`, `env-IT`, `env-AT`).

## Publication Build Reference

### Dockerfile Location

- Dockerfile: `Dockerfile`
- Build script: `docker-build.sh`
- Primary compose/runtime file: `docker/docker-compose.yml`

### Registry Push

```bash
cd ./expert-agent-mcp-server
set -a; source ../env-vault; set +a
bash docker-build.sh latest
docker push <internal-registry>:443/cloud-dog/expert-agent-mcp-server:latest
```

### Standard Build Arguments and Prerequisites

- `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` when required by the host environment
- Cloud-Dog CA bundle if private trust material is needed
- Vault-backed credentials for private package indexes and registry access
- BuildKit-enabled Docker where the project build script expects it
