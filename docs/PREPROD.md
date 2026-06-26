---
template-id: T-PRE
template-version: 1.0
applies-to: docs/PREPROD.md
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

# PREPROD Deployment — Expert Agent MCP Server

This document describes the pre-production operator/deployment overlay for this service. The Terraform container environment is the runtime source of truth, and `private/env-PREPROD` is the operator/test overlay used for local control commands and pytest runs against the deployed preprod service. Defaults and non-preprod settings remain documented in `docs/ENV-REFERENCE.md`, `docs/ARCHITECTURE.md`, and `defaults.yaml`.

## 1. Overview
- Service URL: `https://expertagent0.cloud-dog.net`
- Container hostname: `expertagent0.app.vpc0.cloud-dog.net`
- Health endpoint: `https://expertagent0.cloud-dog.net/health`
- Docker image: `registry.cloud-dog.net:443/cloud-dog/expert-agent-mcp-server:latest`
- Active Terraform container definition: `.w28a936-cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents/expertagent_containers.tf.json`
- Active Terraform image definition: `.w28a936-cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents/docker_images.tf.json`
- Operator overlay file: `./expert-agent-mcp-server/private/env-PREPROD`

### Port allocation
| Surface | Internal port | External URL |
|---|---:|---|
| Web UI | 8080 | `https://expertagent0.cloud-dog.net` |
| MCP | 8081 | `https://expertagent0.cloud-dog.net/mcp` |
| A2A | 8082 | `wss://expertagent0.cloud-dog.net/a2a` |
| API | 8083 | `https://expertagent0.cloud-dog.net/api` |

## 2. Configuration
Section 2 documents the full preprod environment surface that differs from or materially specialises the defaults. Use it together with `defaults.yaml` and `docs/ENV-REFERENCE.md` when tracing a value through the precedence chain `os.environ -> --env file -> config.yaml -> defaults.yaml`.

### Server settings
| Setting(s) | Default / baseline | Preprod source | Preprod change? | Notes |
|---|---|---|---|---|
| `CLOUD_DOG_ENVIRONMENT` | `development` from `defaults.yaml` | `private/env-PREPROD` | Yes | Forces preprod log/audit labelling. |
| `CLOUD_DOG__EXPERT__API_SERVER__HOST/PORT/BASE_URL` | `0.0.0.0:8083`, no external base URL in defaults | Terraform + `private/env-PREPROD` | Yes | API is exposed through Traefik at `/api`. |
| `CLOUD_DOG__EXPERT__WEB_SERVER__HOST/PORT/BASE_URL` | `0.0.0.0:8080`, local static/templates | Terraform + `private/env-PREPROD` | Yes | Web UI is the root external surface. |
| `CLOUD_DOG__EXPERT__MCP_SERVER__HOST/PORT/TRANSPORT/BASE_URL` | `0.0.0.0:8081`, `sse` | Terraform + `private/env-PREPROD` | Yes | Transport remains `sse`; external route is `/mcp`. |
| `CLOUD_DOG__EXPERT__A2A_SERVER__HOST/PORT/BASE_URL` | `0.0.0.0:8082` | `private/env-PREPROD` | Yes | External websocket route is `/a2a`. |

### Data, LLM, and queue settings
| Setting(s) | Default / baseline | Preprod source | Preprod change? | Notes |
|---|---|---|---|---|
| `CLOUD_DOG__EXPERT__DB__URI` | `sqlite:///expert.db` | Terraform + `private/env-PREPROD` | Yes | Container uses `/app/database/expert.db`. |
| `CLOUD_DOG__EXPERT__VECTOR__STORE__TYPE` and `...CHROMA...` | Chroma defaults in `defaults.yaml` | Terraform + `private/env-PREPROD` | Yes | Preprod persists Chroma under `/app/storage/chroma`. |
| `CLOUD_DOG__EXPERT__LLM__PROVIDER/BASE_URL/MODEL/...` | Ollama `qwen3:14b` on `llm2` | Vault-backed Terraform vars + `private/env-PREPROD` | Yes | LLM settings are explicitly pinned for reproducibility. |
| `CLOUD_DOG__EXPERT__EMBEDDINGS__PROVIDER/BASE_URL/MODEL/DIMENSION` | `ollama`, `bge-m3:567m`, 1024 dims | Terraform + `private/env-PREPROD` | Yes | Embeddings stay aligned with the Chroma collection schema. |
| `CLOUD_DOG__EXPERT__REDIS__HOST/PORT/DB/USERNAME/PASSWORD` | Localhost Redis in defaults | Terraform + `private/env-PREPROD` | Yes | Required for queueing and async session work. |

### Auth, TLS, and observability
| Setting(s) | Default / baseline | Preprod source | Preprod change? | Notes |
|---|---|---|---|---|
| `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE` | unset | `private/env-PREPROD` | Yes | Local operator overlay uses host CA bundle; Terraform mounts `/app/certificates/trusted-ca-bundle.pem` in-container. |
| `CLOUD_DOG__EXPERT__API_KEY`, `...API_SERVER__API_KEY` | blank in defaults | Vault via Terraform + `private/env-PREPROD` | Yes | Same key is used for API and test validation. |
| `CLOUD_DOG__EXPERT__WEB_SERVER__USERNAME/PASSWORD` | blank in defaults | Vault via Terraform + `private/env-PREPROD` | Yes | Required for web login. |
| `CLOUD_DOG__EXPERT__SECURITY__SECRET_KEY/JWT_SECRET` | dev placeholders in defaults | Vault via Terraform + `private/env-PREPROD` | Yes | Mandatory in non-dev environments. |
| `CLOUD_DOG__EXPERT__LOG__*` and audit settings | `INFO`, JSON, audit enabled | Terraform + `defaults.yaml` | Partial | Most log defaults are inherited; preprod sets the service environment label. |

## 3. Preprod-Specific Overrides
Only settings that differ materially from defaults or that must be supplied for preprod are listed here. The literal operator/test overlay is `./expert-agent-mcp-server/private/env-PREPROD`.

| Override | Why preprod differs | Source of truth |
|---|---|---|
| External base URLs for API/Web/MCP/A2A | Traefik terminates TLS and exposes canonical public URLs. | `private/env-PREPROD`, Terraform 60-container file |
| SQLite path `/app/database/expert.db` | Container filesystem differs from local development paths. | Terraform 60-container file |
| Chroma path `/app/storage/chroma` | Container volume mount replaces repo-local storage. | Terraform 60-container file |
| Vault-backed LLM and embedding endpoints | Preprod pins live shared `llm2` services, not local defaults. | Vault + Terraform |
| Redis host/password | Queueing uses shared Valkey rather than localhost. | Vault + Terraform |
| API/web credentials and JWT secrets | Non-dev runtime must not use defaults placeholders. | Vault + Terraform |

## 4. Vault Configuration
This service reads preprod secrets from the shared Vault config blob at `cloud_dog_ai/config`.

### Required Vault paths
- `dev.services.expertagent0` for API key, web credentials, JWT, audit secret
- `dev.models.ollama_qwen3_14b_llm2` for chat model endpoint and model name
- `dev.models.ollama_bge_m3_567m_llm2` for embeddings
- `dev.redis.valkey*` for queue password

### Operator setup
```bash
set -a; source ../env-vault; set +a
vault kv get -mount=cloud_dog_ai config
```

### Populate or refresh missing entries
Use a merged JSON payload rather than editing Terraform or the running container.

```bash
vault kv put -mount=cloud_dog_ai config   content=@/tmp/cloud-dog-ai-config.preprod.json
```

Example payload fragment:
```json
{
  "dev": {
    "services": {
      "expertagent0": {
        "api_key": "<API_KEY>",
        "web_username": "<WEB_USERNAME>",
        "web_password": "<WEB_PASSWORD>",
        "secret_key": "<AUDIT_SECRET>",
        "jwt_secret": "<JWT_SECRET>"
      }
    }
  }
}
```

## 5. Deployment Steps
The project rules forbid ad-hoc `docker build`; use the repo entrypoint script.

1. Load Vault-backed build credentials.
```bash
set -a; source ../env-vault; set +a
```
2. Build the image.
```bash
cd ./expert-agent-mcp-server && bash docker-build.sh latest
```
3. Tag and push the image.
```bash
docker push registry.cloud-dog.net:443/cloud-dog/expert-agent-mcp-server:latest
```
4. Plan and apply the Terraform update from the shared preprod workspace.
```bash
cd '/opt/iac/Development/cloud-dog-ai/.w28a936-cloud-dog-repo/terraform/server0.viewdeck.com/27 MLAgents'
terraform plan -target=docker_image.expertagent -target=docker_container.expertagent0 -out=tfplan.out
terraform apply tfplan.out
```
5. Verify the deployed service.
```bash
curl -fsS https://expertagent0.cloud-dog.net/health
```

## 6. Testing Against Preprod
Use the committed tier env file plus `private/env-PREPROD` as the environment-specific overlay.

1. `pytest tests/system --env tests/env-ST --env private/env-PREPROD -q`
2. `pytest tests/integration --env tests/env-IT --env private/env-PREPROD -q`
3. Optional committed overlay: `tests/env-preprod-expertagent0` for targeted smoke validation.

Known limitations:
- Shared preprod LLM latency can exceed local expectations; keep long client timeouts.
- Avoid destructive AT flows against shared session/knowledge data unless explicitly scheduled.

## 7. Troubleshooting
- `curl -fsS https://expertagent0.cloud-dog.net/health` should return `status=healthy`.
- `docker logs expertagent0.app.vpc0.cloud-dog.net` is not the normal access path; use Terraform state plus the remote Docker host when investigating container runtime issues.
- `./server_control.sh --env private/env-PREPROD status` validates local overlay loading before remote tests.
