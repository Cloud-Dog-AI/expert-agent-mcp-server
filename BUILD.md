---
template-id: T-BLR
template-version: 1.0
applies-to: BUILD.md
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

# Build Instructions

## Project
`expert-agent-mcp-server` - multi-server expert orchestration service.

## Prerequisites
- Python 3.12+
- Docker
- pip

## Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

If the Cloud-Dog platform packages live on a public index other than the default,
install with a single package index (never an `--extra-index-url`):
```bash
PYPI_URL=https://pypi.org/simple/
pip install -e ".[dev]" --index-url "$PYPI_URL"
```

## Local Configuration
Create a local env file with the ports and runtime settings you want to override:
```bash
cat > .env.local <<'ENV'
CLOUD_DOG__EXPERT__API_SERVER__PORT=8083
CLOUD_DOG__EXPERT__WEB_SERVER__PORT=8080
CLOUD_DOG__EXPERT__MCP_SERVER__PORT=8081
CLOUD_DOG__EXPERT__A2A_SERVER__PORT=8082
CLOUD_DOG__EXPERT__DB__URI=sqlite:///./data/expert.db
ENV
```

## Run Locally
```bash
./server_control.sh --env ./.env.local start-all
./server_control.sh --env ./.env.local status-all
./server_control.sh --env ./.env.local stop-all
```

## Run Tests
If your tests require environment-backed configuration, place it in `.env.test` and point pytest at it:
```bash
python -m pytest tests/quality --env ./.env.test -v
python -m pytest tests/unit --env ./.env.test -v
python -m pytest tests/system --env ./.env.test -v
python -m pytest tests/integration --env ./.env.test -v
python -m pytest tests/application --env ./.env.test -v
```

## Build
### Python Package
```bash
python -m pip install build
python -m build
```

### Docker Container
Public (external / GitHub-boundary) build:
```bash
PUBLICATION_TAG_SUFFIX=github-test ./docker-build.sh --variant public latest
```

Build with explicit image, network, and public package index settings:
```bash
PIP_INDEX_URL=https://pypi.org/simple/ \
DOCKER_BUILD_NETWORK=host \
PUBLICATION_TAG_SUFFIX=github-test ./docker-build.sh --variant public --name expert-agent-mcp-server --tag latest --registry registry.example.com/team
```

For a self-contained external build, see [EXTERNAL-BUILD.md](EXTERNAL-BUILD.md).

If your environment uses a custom CA bundle:
```bash
./docker-build.sh --custom-ca ./certs/ca.pem --network host
```

## Docker Push
```bash
docker tag expert-agent-mcp-server:latest registry.example.com/team/expert-agent-mcp-server:latest
docker push registry.example.com/team/expert-agent-mcp-server:latest
```

## Configuration
Configuration follows this precedence:
```text
OS environment -> env file passed to server_control.sh -> defaults.yaml
```

## Local Secrets
Put local-only values in the env file passed to `server_control.sh` or mounted into Docker. Do not commit real credentials.
