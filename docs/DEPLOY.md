---
template-id: T-DEP
template-version: 1.0
applies-to: docs/DEPLOY.md
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

# Deployment Guide

## Option 1: Docker (recommended)

### Without Vault
```bash
cat > .env <<EOF
CLOUD_DOG__WEB_SERVER__PORT=8080
CLOUD_DOG__MCP_SERVER__PORT=8081
CLOUD_DOG__A2A_SERVER__PORT=8082
CLOUD_DOG__API_SERVER__PORT=8083
CLOUD_DOG__WEB_SERVER__USERNAME=admin
CLOUD_DOG__WEB_SERVER__PASSWORD=your-secure-password
CLOUD_DOG__API_SERVER__API_KEY=your-api-key
EOF

docker build -t expert-agent:latest .
docker run -d --name expert-agent \
  --env-file .env \
  -p 8080:8080 -p 8081:8081 -p 8082:8082 -p 8083:8083 \
  expert-agent:latest
```

### With Vault
```bash
cat > .env <<EOF
VAULT_ADDR=https://your-vault-server
VAULT_TOKEN=your-vault-token
VAULT_MOUNT_POINT=secret
VAULT_CONFIG_PATH=services/your-service
CLOUD_DOG__WEB_SERVER__PORT=8080
CLOUD_DOG__MCP_SERVER__PORT=8081
CLOUD_DOG__A2A_SERVER__PORT=8082
CLOUD_DOG__API_SERVER__PORT=8083
EOF

docker run -d --name expert-agent \
  --env-file .env \
  -p 8080:8080 -p 8081:8081 -p 8082:8082 -p 8083:8083 \
  expert-agent:latest
```

### With Custom CA Certificates
```bash
docker run -d --name expert-agent \
  --env-file .env \
  -v /path/to/ca-bundle.pem:/app/certs/ca-bundle.pem \
  -e REQUESTS_CA_BUNDLE=/app/certs/ca-bundle.pem \
  -e SSL_CERT_FILE=/app/certs/ca-bundle.pem \
  expert-agent:latest
```

## Option 2: Direct (no Docker)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./server_control.sh --env env.example start all
```

## Example Environment File
- See `docs/ENV-REFERENCE.md` for the full variable catalogue.
- Use only generic examples in shared documentation; inject secrets at runtime.

## Health Checks
```bash
curl -f http://127.0.0.1:8083/health
curl -f http://127.0.0.1:8081/health
```

## Deployment Notes
- Service focus: Expert reasoning, session orchestration, knowledge retrieval, vector-backed context, and administrative control across API, Web, MCP, and A2A surfaces.
- Primary capabilities: session lifecycle, expert selection, knowledge and history retrieval, vector search, admin identity and API key management.
- Review the published environment reference before deploying to a shared environment.
