---
template-id: T-ENV
template-version: 1.0
applies-to: docs/ENV-REFERENCE.md
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

# Environment Reference

This reference is generated from `defaults.yaml` and the standard Cloud-Dog environment override pattern.

## `a2a_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__A2A_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for a2a server. |
| `CLOUD_DOG__A2A_SERVER__PORT` | `8082` | Optional | `8082` | Port for a2a server connections. |
| `CLOUD_DOG__A2A_SERVER__DEBUG` | `false` | Optional | `false` | Configuration value for a2a server debug. |
| `CLOUD_DOG__A2A_SERVER__LOG_FILE` | `/var/log/expert/a2a.log` | Optional | `/var/log/expert/a2a.log` | Configuration value for a2a server log file. |
| `CLOUD_DOG__A2A_SERVER__ENABLED` | `true` | Optional | `true` | Toggle for a2a server. |

## `api_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__API_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for api server. |
| `CLOUD_DOG__API_SERVER__PORT` | `8083` | Optional | `8083` | Port for api server connections. |
| `CLOUD_DOG__API_SERVER__DEBUG` | `false` | Optional | `false` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__API_SERVER__LOG_FILE` | `/var/log/expert/api.log` | Optional | `/var/log/expert/api.log` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__API_SERVER__ENABLED` | `true` | Optional | `true` | Credential or authentication setting for the related subsystem. |

## `app`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__APP__NAME` | `Expert Agent MCP Server` | Optional | `Expert Agent MCP Server` | Configuration value for app name. |
| `CLOUD_DOG__APP__VERSION` | `0.1.0` | Optional | `0.1.0` | Configuration value for app version. |
| `CLOUD_DOG__APP__ENVIRONMENT` | `development` | Optional | `development` | Configuration value for app environment. |
| `CLOUD_DOG__APP__URL` | `<set per environment>` | Deployment dependent | `https://service.example.com` | Endpoint or connection URL for app. |

## `auth`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__AUTH__PROVIDER` | `local` | Optional | `local` | Configuration value for auth provider. |
| `CLOUD_DOG__AUTH__JWT_SECRET` | `<secret>` | Deployment dependent | `your-secret-value` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__AUTH__SESSION_TIMEOUT_MINUTES` | `60` | Optional | `60` | Configuration value for auth session timeout minutes. |
| `CLOUD_DOG__AUTH__PASSWORD_MIN_LENGTH` | `8` | Deployment dependent | `your-secure-password` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__AUTH__PASSWORD_REQUIRE_COMPLEXITY` | `true` | Deployment dependent | `your-secure-password` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__AUTH__LOCKOUT_ENABLED` | `false` | Optional | `false` | Toggle for auth lockout. |
| `CLOUD_DOG__AUTH__LOCKOUT_MAX_ATTEMPTS` | `5` | Optional | `5` | Configuration value for auth lockout max attempts. |
| `CLOUD_DOG__AUTH__LOCKOUT_WINDOW_SECONDS` | `300` | Optional | `300` | Timeout or duration control for auth lockout window. |
| `CLOUD_DOG__AUTH__LOCKOUT_SECONDS` | `300` | Optional | `300` | Timeout or duration control for auth lockout. |

## `auth_providers`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__AUTH_PROVIDERS__LOCAL__ENABLED` | `true` | Optional | `true` | Toggle for auth providers local. |
| `CLOUD_DOG__AUTH_PROVIDERS__GOOGLE__ENABLED` | `false` | Optional | `false` | Toggle for auth providers google. |
| `CLOUD_DOG__AUTH_PROVIDERS__GOOGLE__CLIENT_ID` | `-` | Optional | `<set as needed>` | Configuration value for auth providers google client id. |
| `CLOUD_DOG__AUTH_PROVIDERS__GOOGLE__CLIENT_SECRET` | `-` | Deployment dependent | `your-secret-value` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__AUTH_PROVIDERS__LINKEDIN__ENABLED` | `false` | Optional | `false` | Toggle for auth providers linkedin. |
| `CLOUD_DOG__AUTH_PROVIDERS__LINKEDIN__CLIENT_ID` | `-` | Optional | `<set as needed>` | Configuration value for auth providers linkedin client id. |
| `CLOUD_DOG__AUTH_PROVIDERS__LINKEDIN__CLIENT_SECRET` | `-` | Deployment dependent | `your-secret-value` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__ENABLED` | `false` | Optional | `false` | Toggle for auth providers keycloak. |
| `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__SERVER_URL` | `-` | Deployment dependent | `<set as needed>` | Endpoint or connection URL for auth providers keycloak server. |
| `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__REALM` | `-` | Optional | `<set as needed>` | Configuration value for auth providers keycloak realm. |
| `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__CLIENT_ID` | `-` | Optional | `<set as needed>` | Configuration value for auth providers keycloak client id. |
| `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__CLIENT_SECRET` | `-` | Deployment dependent | `your-secret-value` | Credential or authentication setting for the related subsystem. |

## `cache`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__CACHE__ENABLED` | `true` | Optional | `true` | Toggle for cache. |
| `CLOUD_DOG__CACHE__BACKEND` | `memory` | Optional | `memory` | Configuration value for cache backend. |
| `CLOUD_DOG__CACHE__TTL_SECONDS` | `3600` | Optional | `3600` | Timeout or duration control for cache ttl. |
| `CLOUD_DOG__CACHE__MAX_ENTRIES` | `1000` | Optional | `1000` | Configuration value for cache max entries. |

## `circuit`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__CIRCUIT__HARD_ERROR_THRESHOLD` | `5` | Optional | `5` | Configuration value for circuit hard error threshold. |
| `CLOUD_DOG__CIRCUIT__SOFT_ERROR_THRESHOLD` | `3` | Optional | `3` | Configuration value for circuit soft error threshold. |
| `CLOUD_DOG__CIRCUIT__RESET_TIMEOUT_SECONDS` | `60` | Optional | `60` | Timeout or duration control for circuit reset timeout. |

## `db`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__DB__URI` | `sqlite:///expert.db` | Deployment dependent | `https://service.example.com` | Endpoint or connection URL for db. |
| `CLOUD_DOG__DB__POOL_SIZE` | `10` | Optional | `10` | Configuration value for db pool size. |
| `CLOUD_DOG__DB__MAX_OVERFLOW` | `20` | Optional | `20` | Configuration value for db max overflow. |
| `CLOUD_DOG__DB__ECHO` | `false` | Optional | `false` | Configuration value for db echo. |

## `default_expert`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__DEFAULT_EXPERT` | `_DEFAULT_` | Optional | `_DEFAULT_` | Configuration value for default expert. |

## `embeddings`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__EMBEDDINGS__PROVIDER` | `ollama` | Optional | `ollama` | Configuration value for embeddings provider. |
| `CLOUD_DOG__EMBEDDINGS__BASE_URL` | `<set per environment>` | Deployment dependent | `<set per environment>` | Endpoint or connection URL for embeddings base. |
| `CLOUD_DOG__EMBEDDINGS__MODEL` | `bge-m3:567m` | Optional | `bge-m3:567m` | Configuration value for embeddings model. |
| `CLOUD_DOG__EMBEDDINGS__DIMENSION` | `1024` | Optional | `1024` | Configuration value for embeddings dimension. |
| `CLOUD_DOG__EMBEDDINGS__BATCH_SIZE` | `10` | Optional | `10` | Configuration value for embeddings batch size. |
| `CLOUD_DOG__EMBEDDINGS__TIMEOUT` | `300` | Optional | `300` | Timeout or duration control for embeddings. |

## `experts`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__EXPERTS___DEFAULT___NAME` | `General Assistant` | Optional | `General Assistant` | Configuration value for experts DEFAULT name. |
| `CLOUD_DOG__EXPERTS___DEFAULT___TITLE` | `General Purpose Expert` | Optional | `General Purpose Expert` | Configuration value for experts DEFAULT title. |
| `CLOUD_DOG__EXPERTS___DEFAULT___DESCRIPTION` | `A general purpose expert assistant for various tasks` | Optional | `A general purpose expert assistant for various tasks` | Configuration value for experts DEFAULT description. |
| `CLOUD_DOG__EXPERTS___DEFAULT___LLM_PROVIDER` | `ollama` | Optional | `ollama` | Configuration value for experts DEFAULT llm provider. |
| `CLOUD_DOG__EXPERTS___DEFAULT___LLM_MODEL` | `qwen3:14b` | Optional | `qwen3:14b` | Configuration value for experts DEFAULT llm model. |
| `CLOUD_DOG__EXPERTS___DEFAULT___LLM_TEMPERATURE` | `0.7` | Optional | `0.7` | Configuration value for experts DEFAULT llm temperature. |
| `CLOUD_DOG__EXPERTS___DEFAULT___LLM_MAX_TOKENS` | `1024` | Deployment dependent | `your-secret-value` | Configuration value for experts DEFAULT llm max tokens. |
| `CLOUD_DOG__EXPERTS___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for experts DEFAULT. |
| `CLOUD_DOG__EXPERTS___DEFAULT___HISTORY_ENABLED` | `true` | Optional | `true` | Toggle for experts DEFAULT history. |
| `CLOUD_DOG__EXPERTS___DEFAULT___VECTOR_STORE_ENABLED` | `true` | Optional | `true` | Toggle for experts DEFAULT vector store. |
| `CLOUD_DOG__EXPERTS___DEFAULT___TOOLS_ENABLED` | `false` | Optional | `false` | Toggle for experts DEFAULT tools. |
| `CLOUD_DOG__EXPERTS___DEFAULT___ACCESS_CONTROL__PUBLIC` | `false` | Optional | `false` | Configuration value for experts DEFAULT access control public. |
| `CLOUD_DOG__EXPERTS___DEFAULT___ACCESS_CONTROL__ALLOWED_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for experts DEFAULT access control allowed groups. |
| `CLOUD_DOG__EXPERTS___DEFAULT___ACCESS_CONTROL__ALLOWED_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for experts DEFAULT access control allowed users. |

## `llm`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__LLM__PROVIDER` | `ollama` | Optional | `ollama` | Configuration value for llm provider. |
| `CLOUD_DOG__LLM__BASE_URL` | `<set per environment>` | Deployment dependent | `<set per environment>` | Endpoint or connection URL for llm base. |
| `CLOUD_DOG__LLM__MODEL` | `qwen3:14b` | Optional | `qwen3:14b` | Configuration value for llm model. |
| `CLOUD_DOG__LLM__TEMPERATURE` | `0.7` | Optional | `0.7` | Configuration value for llm temperature. |
| `CLOUD_DOG__LLM__TOP_K` | `40` | Optional | `40` | Configuration value for llm top k. |
| `CLOUD_DOG__LLM__TOP_P` | `0.9` | Optional | `0.9` | Configuration value for llm top p. |
| `CLOUD_DOG__LLM__MAX_TOKENS` | `1024` | Deployment dependent | `your-secret-value` | Configuration value for llm max tokens. |
| `CLOUD_DOG__LLM__TIMEOUT` | `300` | Optional | `300` | Timeout or duration control for llm. |
| `CLOUD_DOG__LLM__DEFAULT_SYSTEM_PROMPT` | `You are a helpful expert assistant. Provide accurate, concise...` | Optional | `You are a helpful expert assistant. Provide accurate, concise...` | Configuration value for llm default system prompt. |
| `CLOUD_DOG__LLM__PROMPTS__EN` | `You are a helpful expert assistant. Provide accurate, concise...` | Optional | `You are a helpful expert assistant. Provide accurate, concise...` | Configuration value for llm prompts en. |
| `CLOUD_DOG__LLM__PROMPTS__FR` | `Vous êtes un assistant expert utile. Fournissez des réponses ...` | Optional | `Vous êtes un assistant expert utile. Fournissez des réponses ...` | Configuration value for llm prompts fr. |
| `CLOUD_DOG__LLM__PROMPTS__PL` | `Jesteś pomocnym asystentem eksperckim. Zapewniaj dokładne, zw...` | Optional | `Jesteś pomocnym asystentem eksperckim. Zapewniaj dokładne, zw...` | Configuration value for llm prompts pl. |

## `log`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__LOG__LEVEL` | `INFO` | Optional | `INFO` | Configuration value for log level. |
| `CLOUD_DOG__LOG__FORMAT` | `json` | Optional | `json` | Configuration value for log format. |
| `CLOUD_DOG__LOG__DUMP_CONFIG` | `false` | Optional | `false` | Configuration value for log dump config. |
| `CLOUD_DOG__LOG__PII_REDACTION` | `true` | Optional | `true` | Configuration value for log pii redaction. |
| `CLOUD_DOG__LOG__SERVICE_INSTANCE` | `${HOSTNAME:expert-agent-local}` | Optional | `${HOSTNAME:expert-agent-local}` | Configuration value for log service instance. |
| `CLOUD_DOG__LOG__AUDIT_LOG` | `logs/audit.log.jsonl` | Optional | `logs/audit.log.jsonl` | Configuration value for log audit log. |
| `CLOUD_DOG__LOG__ENVIRONMENT` | `${CLOUD_DOG_ENVIRONMENT:dev}` | Optional | `${CLOUD_DOG_ENVIRONMENT:dev}` | Configuration value for log environment. |
| `CLOUD_DOG__LOG__RETENTION__HOT_DAYS` | `14` | Optional | `14` | Configuration value for log retention hot days. |
| `CLOUD_DOG__LOG__RETENTION__COLD_DAYS` | `60` | Optional | `60` | Configuration value for log retention cold days. |
| `CLOUD_DOG__LOG__RETENTION__ARCHIVE_FORMAT` | `gz` | Optional | `gz` | Configuration value for log retention archive format. |
| `CLOUD_DOG__LOG__INTEGRITY__ENABLED` | `true` | Optional | `true` | Toggle for log integrity. |
| `CLOUD_DOG__LOG__INTEGRITY__INTERVAL_SECONDS` | `300` | Optional | `300` | Timeout or duration control for log integrity interval. |
| `CLOUD_DOG__LOG__INTEGRITY__LOG_FILE` | `logs/audit-integrity.log` | Optional | `logs/audit-integrity.log` | Configuration value for log integrity log file. |
| `CLOUD_DOG__LOG__INTEGRITY__HASH_ALGORITHM` | `sha256` | Optional | `sha256` | Configuration value for log integrity hash algorithm. |
| `CLOUD_DOG__LOG__ROTATION__MODE` | `size` | Optional | `size` | Configuration value for log rotation mode. |
| `CLOUD_DOG__LOG__ROTATION__MAX_BYTES` | `10485760` | Optional | `10485760` | Configuration value for log rotation max bytes. |
| `CLOUD_DOG__LOG__ROTATION__BACKUP_COUNT` | `10` | Optional | `10` | Configuration value for log rotation backup count. |
| `CLOUD_DOG__LOG__ROTATION__WHEN` | `midnight` | Optional | `midnight` | Configuration value for log rotation when. |
| `CLOUD_DOG__LOG__ROTATION__INTERVAL` | `1` | Optional | `1` | Configuration value for log rotation interval. |
| `CLOUD_DOG__LOG__ROTATION__COMPRESS` | `true` | Optional | `true` | Configuration value for log rotation compress. |

## `mcp_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__MCP_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for mcp server. |
| `CLOUD_DOG__MCP_SERVER__PORT` | `8081` | Optional | `8081` | Port for mcp server connections. |
| `CLOUD_DOG__MCP_SERVER__DEBUG` | `false` | Optional | `false` | Configuration value for mcp server debug. |
| `CLOUD_DOG__MCP_SERVER__LOG_FILE` | `/var/log/expert/mcp.log` | Optional | `/var/log/expert/mcp.log` | Configuration value for mcp server log file. |
| `CLOUD_DOG__MCP_SERVER__ENABLED` | `true` | Optional | `true` | Toggle for mcp server. |
| `CLOUD_DOG__MCP_SERVER__TRANSPORT` | `sse` | Optional | `sse` | Configuration value for mcp server transport. |

## `metrics`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__METRICS__ENABLED` | `true` | Optional | `true` | Toggle for metrics. |
| `CLOUD_DOG__METRICS__PROMETHEUS_ENDPOINT` | `/metrics` | Optional | `/metrics` | Configuration value for metrics prometheus endpoint. |
| `CLOUD_DOG__METRICS__COLLECTION_INTERVAL_SECONDS` | `30` | Optional | `30` | Timeout or duration control for metrics collection interval. |

## `multimedia`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__MULTIMEDIA__STORAGE_PATH` | `storage/multimedia` | Optional | `storage/multimedia` | Configuration value for multimedia storage path. |
| `CLOUD_DOG__MULTIMEDIA__MAX_FILE_SIZE_MB` | `10` | Optional | `10` | Configuration value for multimedia max file size mb. |
| `CLOUD_DOG__MULTIMEDIA__SUPPORTED_FORMATS` | `["jpg", "png", "mp3", "mp4", "txt", "md"]` | Optional | `<set as needed>` | Configuration value for multimedia supported formats. |

## `privacy`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__PRIVACY__PII_REMOVAL_ENABLED` | `true` | Optional | `true` | Toggle for privacy pii removal. |
| `CLOUD_DOG__PRIVACY__PII_PATTERNS` | `[{"pattern": "\\b\\d{3}-\\d{2}-\\d{4}\\b", "replacement": "[REDACTED_SSN]", "description": "Social Security Number"}, {"...` | Optional | `<set as needed>` | Configuration value for privacy pii patterns. |
| `CLOUD_DOG__PRIVACY__DATA_ENCRYPTION_AT_REST` | `true` | Optional | `true` | Configuration value for privacy data encryption at rest. |
| `CLOUD_DOG__PRIVACY__USER_DATA_RETENTION_DAYS` | `365` | Optional | `365` | Configuration value for privacy user data retention days. |

## `prompts`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__PROMPTS__MIN_DESCRIPTION_CHARS` | `30` | Optional | `30` | Configuration value for prompts min description chars. |
| `CLOUD_DOG__PROMPTS__ENTROPY_MIN_UNIQUE_WORDS` | `8` | Optional | `8` | Configuration value for prompts entropy min unique words. |
| `CLOUD_DOG__PROMPTS__TEMPLATE_VARIABLES` | `["services", "tools", "sub_experts", "user", "session"]` | Optional | `<set as needed>` | Configuration value for prompts template variables. |

## `queue`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__QUEUE__MAX_RETRIES` | `3` | Optional | `3` | Configuration value for queue max retries. |
| `CLOUD_DOG__QUEUE__RETRY_DELAY_SECONDS` | `5` | Optional | `5` | Timeout or duration control for queue retry delay. |
| `CLOUD_DOG__QUEUE__TIMEOUT_SECONDS` | `30` | Optional | `30` | Timeout or duration control for queue timeout. |

## `rate_limit`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__RATE_LIMIT__REQUESTS_PER_MINUTE` | `60` | Optional | `60` | Configuration value for rate limit requests per minute. |
| `CLOUD_DOG__RATE_LIMIT__BURST_LIMIT` | `10` | Optional | `10` | Configuration value for rate limit burst limit. |

## `redis`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__REDIS__HOST` | `localhost` | Optional | `0.0.0.0` | Host binding or upstream host for redis. |
| `CLOUD_DOG__REDIS__PORT` | `6379` | Optional | `6379` | Port for redis connections. |
| `CLOUD_DOG__REDIS__DB` | `0` | Optional | `0` | Configuration value for redis db. |
| `CLOUD_DOG__REDIS__USERNAME` | `-` | Optional | `service-admin` | Configuration value for redis username. |
| `CLOUD_DOG__REDIS__PASSWORD` | `-` | Deployment dependent | `your-secure-password` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__REDIS__TOKEN` | `-` | Deployment dependent | `your-secret-value` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__REDIS__SSL` | `false` | Optional | `false` | Configuration value for redis ssl. |
| `CLOUD_DOG__REDIS__SOCKET_CONNECT_TIMEOUT_SECONDS` | `10` | Optional | `10` | Timeout or duration control for redis socket connect timeout. |
| `CLOUD_DOG__REDIS__TIMEOUT` | `5` | Optional | `5` | Timeout or duration control for redis. |

## `security`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__SECURITY__AUDIT_SECRET_KEY` | `<secret>` | Deployment dependent | `your-secret-value` | Credential or authentication setting for the related subsystem. |

## `server_id`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__SERVER_ID` | `${HOSTNAME:expert-agent-local}` | Optional | `${HOSTNAME:expert-agent-local}` | Configuration value for server id. |

## `service_composition`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__SERVICE_COMPOSITION__TOOL_DISCOVERY_CACHE_TTL` | `300` | Optional | `300` | Configuration value for service composition tool discovery cache ttl. |
| `CLOUD_DOG__SERVICE_COMPOSITION__INVOCATION_TIMEOUT` | `30` | Optional | `30` | Timeout or duration control for service composition invocation. |
| `CLOUD_DOG__SERVICE_COMPOSITION__CIRCUIT_BREAKER_THRESHOLD` | `5` | Optional | `5` | Configuration value for service composition circuit breaker threshold. |
| `CLOUD_DOG__SERVICE_COMPOSITION__CIRCUIT_BREAKER_RESET` | `60` | Optional | `60` | Configuration value for service composition circuit breaker reset. |
| `CLOUD_DOG__SERVICE_COMPOSITION__MAX_DELEGATION_DEPTH` | `3` | Optional | `3` | Configuration value for service composition max delegation depth. |
| `CLOUD_DOG__SERVICE_COMPOSITION__TRANSACTIONAL_SESSION_PERSIST` | `false` | Optional | `false` | Configuration value for service composition transactional session persist. |

## `session`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__SESSION__DEFAULT_TTL_HOURS` | `24` | Optional | `24` | Configuration value for session default ttl hours. |
| `CLOUD_DOG__SESSION__HISTORY_RETENTION_DAYS` | `30` | Optional | `30` | Configuration value for session history retention days. |
| `CLOUD_DOG__SESSION__CONTEXT_WINDOW_SIZE` | `32768` | Optional | `32768` | Configuration value for session context window size. |
| `CLOUD_DOG__SESSION__MAX_HISTORY_MESSAGES` | `100` | Optional | `100` | Configuration value for session max history messages. |
| `CLOUD_DOG__SESSION__MAX_SESSIONS_PER_USER` | `10` | Optional | `10` | Configuration value for session max sessions per user. |
| `CLOUD_DOG__SESSION__MAX_SESSIONS_PER_GROUP` | `50` | Optional | `50` | Configuration value for session max sessions per group. |
| `CLOUD_DOG__SESSION__QUEUE_ENABLED` | `true` | Optional | `true` | Toggle for session queue. |

## `test`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__TEST__HTTP_TIMEOUT_SECONDS` | `60` | Optional | `60` | Timeout or duration control for test http timeout. |

## `tracing`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__TRACING__ENABLED` | `false` | Optional | `false` | Toggle for tracing. |
| `CLOUD_DOG__TRACING__PROVIDER` | `jaeger` | Optional | `jaeger` | Configuration value for tracing provider. |
| `CLOUD_DOG__TRACING__ENDPOINT` | `http://localhost:14268/api/traces` | Optional | `http://localhost:14268/api/traces` | Configuration value for tracing endpoint. |

## `vault`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__VAULT__SERVER` | `-` | Optional | `<set as needed>` | Configuration value for vault server. |
| `CLOUD_DOG__VAULT__KEY` | `-` | Optional | `your-api-key` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__VAULT__MOUNT_POINT` | `-` | Optional | `<set as needed>` | Configuration value for vault mount point. |
| `CLOUD_DOG__VAULT__CONFIG_PATH` | `-` | Optional | `<set as needed>` | Configuration value for vault config path. |
| `CLOUD_DOG__VAULT__TIMEOUT_SECONDS` | `5` | Optional | `5` | Timeout or duration control for vault timeout. |

## `vector_stores`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__DISTANCE_METRIC` | `cosine` | Optional | `cosine` | Configuration value for vector stores common indexing distance metric. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__INDEX_TYPE` | `ann` | Optional | `ann` | Configuration value for vector stores common indexing index type. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__ANN_ALGORITHM` | `hnsw` | Optional | `hnsw` | Configuration value for vector stores common indexing ann algorithm. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__COMPRESSION_ENABLED` | `false` | Optional | `false` | Toggle for vector stores common indexing compression. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__QUANTIZATION_TYPE` | `-` | Optional | `<set as needed>` | Configuration value for vector stores common indexing quantization type. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__SHARDS` | `1` | Optional | `1` | Configuration value for vector stores common indexing shards. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__REPLICAS` | `0` | Optional | `0` | Configuration value for vector stores common indexing replicas. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__PERSISTENCE` | `true` | Optional | `true` | Configuration value for vector stores common indexing persistence. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__LIMIT` | `5` | Optional | `5` | Configuration value for vector stores common search limit. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__TOP_K` | `-` | Optional | `<set as needed>` | Configuration value for vector stores common search top k. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__PRE_FILTER` | `false` | Optional | `false` | Configuration value for vector stores common search pre filter. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__OFFSET` | `0` | Optional | `0` | Configuration value for vector stores common search offset. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__SCORE_THRESHOLD` | `-` | Optional | `<set as needed>` | Configuration value for vector stores common search score threshold. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__MIN_SCORE` | `-` | Optional | `<set as needed>` | Configuration value for vector stores common search min score. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__MAX_DISTANCE` | `-` | Optional | `<set as needed>` | Configuration value for vector stores common search max distance. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_VECTORS` | `false` | Optional | `false` | Configuration value for vector stores common search include vectors. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_METADATA` | `true` | Optional | `true` | Configuration value for vector stores common search include metadata. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_DISTANCES` | `true` | Optional | `true` | Configuration value for vector stores common search include distances. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_SCORES` | `true` | Optional | `true` | Configuration value for vector stores common search include scores. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__HYBRID_ENABLED` | `false` | Optional | `false` | Toggle for vector stores common search hybrid. |
| `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__HYBRID_ALPHA` | `0.5` | Optional | `0.5` | Configuration value for vector stores common search hybrid alpha. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___HOST` | `localhost` | Optional | `0.0.0.0` | Host binding or upstream host for vector stores chroma DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___PORT` | `8000` | Optional | `8000` | Port for vector stores chroma DEFAULT connections. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___COLLECTION_NAME` | `expert_default` | Optional | `expert_default` | Configuration value for vector stores chroma DEFAULT collection name. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for vector stores chroma DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___INDEXING__DISTANCE_METRIC` | `cosine` | Optional | `cosine` | Configuration value for vector stores chroma DEFAULT indexing distance metric. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___INDEXING__INDEX_TYPE` | `ann` | Optional | `ann` | Configuration value for vector stores chroma DEFAULT indexing index type. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___INDEXING__ANN_ALGORITHM` | `hnsw` | Optional | `hnsw` | Configuration value for vector stores chroma DEFAULT indexing ann algorithm. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_SPACE` | `cosine` | Optional | `cosine` | Configuration value for vector stores chroma DEFAULT options hnsw space. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_CONSTRUCTION_EF` | `200` | Optional | `200` | Configuration value for vector stores chroma DEFAULT options hnsw construction ef. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_M` | `16` | Optional | `16` | Configuration value for vector stores chroma DEFAULT options hnsw M. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_SEARCH_EF` | `50` | Optional | `50` | Configuration value for vector stores chroma DEFAULT options hnsw search ef. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_NUM_THREADS` | `4` | Optional | `4` | Configuration value for vector stores chroma DEFAULT options hnsw num threads. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_RESIZE_FACTOR` | `1.2` | Optional | `1.2` | Configuration value for vector stores chroma DEFAULT options hnsw resize factor. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_BATCH_SIZE` | `100` | Optional | `100` | Configuration value for vector stores chroma DEFAULT options hnsw batch size. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_SYNC_THRESHOLD` | `10000` | Optional | `10000` | Configuration value for vector stores chroma DEFAULT options hnsw sync threshold. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___SEARCH__LIMIT` | `5` | Optional | `5` | Configuration value for vector stores chroma DEFAULT search limit. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___SEARCH__INCLUDE` | `["metadatas", "documents", "distances"]` | Optional | `<set as needed>` | Configuration value for vector stores chroma DEFAULT search include. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores chroma DEFAULT access control read groups. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores chroma DEFAULT access control write groups. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__READ_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores chroma DEFAULT access control read users. |
| `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores chroma DEFAULT access control write users. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___HOST` | `localhost` | Optional | `0.0.0.0` | Host binding or upstream host for vector stores qdrant DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___PORT` | `6333` | Optional | `6333` | Port for vector stores qdrant DEFAULT connections. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___API_KEY` | `-` | Deployment dependent | `your-api-key` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___COLLECTION_NAME` | `expert_agent_default` | Optional | `expert_agent_default` | Configuration value for vector stores qdrant DEFAULT collection name. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for vector stores qdrant DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___INDEXING__DISTANCE_METRIC` | `cosine` | Optional | `cosine` | Configuration value for vector stores qdrant DEFAULT indexing distance metric. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___INDEXING__INDEX_TYPE` | `ann` | Optional | `ann` | Configuration value for vector stores qdrant DEFAULT indexing index type. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___INDEXING__ANN_ALGORITHM` | `hnsw` | Optional | `hnsw` | Configuration value for vector stores qdrant DEFAULT indexing ann algorithm. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_M` | `16` | Optional | `16` | Configuration value for vector stores qdrant DEFAULT options hnsw m. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_EF_CONSTRUCT` | `200` | Optional | `200` | Configuration value for vector stores qdrant DEFAULT options hnsw ef construct. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_FULL_SCAN_THRESHOLD` | `10000` | Optional | `10000` | Configuration value for vector stores qdrant DEFAULT options hnsw full scan threshold. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_MAX_INDEXING_THREADS` | `0` | Optional | `0` | Configuration value for vector stores qdrant DEFAULT options hnsw max indexing threads. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_ON_DISK` | `false` | Optional | `false` | Configuration value for vector stores qdrant DEFAULT options hnsw on disk. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__SHARD_NUMBER` | `1` | Optional | `1` | Configuration value for vector stores qdrant DEFAULT options shard number. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__SHARDING_METHOD` | `auto` | Optional | `auto` | Configuration value for vector stores qdrant DEFAULT options sharding method. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__REPLICATION_FACTOR` | `1` | Optional | `1` | Configuration value for vector stores qdrant DEFAULT options replication factor. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__WRITE_CONSISTENCY_FACTOR` | `1` | Optional | `1` | Configuration value for vector stores qdrant DEFAULT options write consistency factor. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__READ_FAN_OUT_FACTOR` | `1` | Optional | `1` | Configuration value for vector stores qdrant DEFAULT options read fan out factor. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__ON_DISK_PAYLOAD` | `false` | Optional | `false` | Configuration value for vector stores qdrant DEFAULT options on disk payload. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__QUANTIZATION_ENABLED` | `false` | Optional | `false` | Toggle for vector stores qdrant DEFAULT options quantization. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__QUANTIZATION_TYPE` | `scalar` | Optional | `scalar` | Configuration value for vector stores qdrant DEFAULT options quantization type. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__QUANTIZATION_ALWAYS_RAM` | `true` | Optional | `true` | Configuration value for vector stores qdrant DEFAULT options quantization always ram. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___SEARCH__LIMIT` | `5` | Optional | `5` | Configuration value for vector stores qdrant DEFAULT search limit. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___SEARCH__WITH_PAYLOAD` | `true` | Optional | `true` | Configuration value for vector stores qdrant DEFAULT search with payload. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___SEARCH__WITH_VECTOR` | `false` | Optional | `false` | Configuration value for vector stores qdrant DEFAULT search with vector. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores qdrant DEFAULT access control read groups. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores qdrant DEFAULT access control write groups. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__READ_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores qdrant DEFAULT access control read users. |
| `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores qdrant DEFAULT access control write users. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___HOST` | `localhost` | Optional | `0.0.0.0` | Host binding or upstream host for vector stores opensearch DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___PORT` | `1201` | Optional | `1201` | Port for vector stores opensearch DEFAULT connections. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___USERNAME` | `-` | Optional | `service-admin` | Configuration value for vector stores opensearch DEFAULT username. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___PASSWORD` | `-` | Deployment dependent | `your-secure-password` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___COLLECTION_NAME` | `expert_agent_default` | Optional | `expert_agent_default` | Configuration value for vector stores opensearch DEFAULT collection name. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for vector stores opensearch DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___INDEXING__DISTANCE_METRIC` | `cosine` | Optional | `cosine` | Configuration value for vector stores opensearch DEFAULT indexing distance metric. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___INDEXING__INDEX_TYPE` | `ann` | Optional | `ann` | Configuration value for vector stores opensearch DEFAULT indexing index type. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___INDEXING__ANN_ALGORITHM` | `hnsw` | Optional | `hnsw` | Configuration value for vector stores opensearch DEFAULT indexing ann algorithm. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__SPACE_TYPE` | `cosinesimil` | Optional | `cosinesimil` | Configuration value for vector stores opensearch DEFAULT options space type. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__METHOD` | `hnsw` | Optional | `hnsw` | Configuration value for vector stores opensearch DEFAULT options method. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__ENGINE` | `nmslib` | Optional | `nmslib` | Configuration value for vector stores opensearch DEFAULT options engine. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__EF_CONSTRUCTION` | `128` | Optional | `128` | Configuration value for vector stores opensearch DEFAULT options ef construction. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__M` | `24` | Optional | `24` | Configuration value for vector stores opensearch DEFAULT options m. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__EF_SEARCH` | `100` | Optional | `100` | Configuration value for vector stores opensearch DEFAULT options ef search. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__INDEX_KNN` | `true` | Optional | `true` | Configuration value for vector stores opensearch DEFAULT options index knn. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__INDEX_KNN_ALGO_PARAM_EF_SEARCH` | `100` | Optional | `100` | Configuration value for vector stores opensearch DEFAULT options index knn algo param ef search. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___SEARCH__LIMIT` | `5` | Optional | `5` | Configuration value for vector stores opensearch DEFAULT search limit. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___SEARCH__K` | `-` | Optional | `<set as needed>` | Configuration value for vector stores opensearch DEFAULT search k. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores opensearch DEFAULT access control read groups. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores opensearch DEFAULT access control write groups. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__READ_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores opensearch DEFAULT access control read users. |
| `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores opensearch DEFAULT access control write users. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___URL` | `http://localhost:8080` | Deployment dependent | `https://service.example.com` | Endpoint or connection URL for vector stores weaviate DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___API_KEY` | `-` | Deployment dependent | `your-api-key` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___COLLECTION_NAME` | `expert_agent_default` | Optional | `expert_agent_default` | Configuration value for vector stores weaviate DEFAULT collection name. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for vector stores weaviate DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___INDEXING__DISTANCE_METRIC` | `cosine` | Optional | `cosine` | Configuration value for vector stores weaviate DEFAULT indexing distance metric. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___INDEXING__INDEX_TYPE` | `ann` | Optional | `ann` | Configuration value for vector stores weaviate DEFAULT indexing index type. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___INDEXING__ANN_ALGORITHM` | `hnsw` | Optional | `hnsw` | Configuration value for vector stores weaviate DEFAULT indexing ann algorithm. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__VECTOR_INDEX_TYPE` | `hnsw` | Optional | `hnsw` | Configuration value for vector stores weaviate DEFAULT options vector index type. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__EF_CONSTRUCTION` | `128` | Optional | `128` | Configuration value for vector stores weaviate DEFAULT options ef construction. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__MAX_CONNECTIONS` | `64` | Optional | `64` | Configuration value for vector stores weaviate DEFAULT options max connections. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__DYNAMIC_EF_MIN` | `100` | Optional | `100` | Configuration value for vector stores weaviate DEFAULT options dynamic ef min. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__DYNAMIC_EF_MAX` | `500` | Optional | `500` | Configuration value for vector stores weaviate DEFAULT options dynamic ef max. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__DYNAMIC_EF_FACTOR` | `8` | Optional | `8` | Configuration value for vector stores weaviate DEFAULT options dynamic ef factor. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__FILTER_STRATEGY` | `acorn` | Optional | `acorn` | Configuration value for vector stores weaviate DEFAULT options filter strategy. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__FLAT_SEARCH_CUTOFF` | `40000` | Optional | `40000` | Configuration value for vector stores weaviate DEFAULT options flat search cutoff. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__VECTOR_CACHE_MAX_OBJECTS` | `1000000000` | Optional | `1000000000` | Configuration value for vector stores weaviate DEFAULT options vector cache max objects. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___SEARCH__LIMIT` | `5` | Optional | `5` | Configuration value for vector stores weaviate DEFAULT search limit. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___SEARCH__ALPHA` | `0.5` | Optional | `0.5` | Configuration value for vector stores weaviate DEFAULT search alpha. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___SEARCH__FUSION_STRATEGY` | `ranked` | Optional | `ranked` | Configuration value for vector stores weaviate DEFAULT search fusion strategy. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores weaviate DEFAULT access control read groups. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores weaviate DEFAULT access control write groups. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__READ_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores weaviate DEFAULT access control read users. |
| `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores weaviate DEFAULT access control write users. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___HOST` | `localhost` | Optional | `0.0.0.0` | Host binding or upstream host for vector stores pgvector DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___PORT` | `5432` | Optional | `5432` | Port for vector stores pgvector DEFAULT connections. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___DATABASE` | `expert_agent` | Optional | `expert_agent` | Configuration value for vector stores pgvector DEFAULT database. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___USERNAME` | `postgres` | Optional | `service-admin` | Configuration value for vector stores pgvector DEFAULT username. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___PASSWORD` | `-` | Deployment dependent | `your-secure-password` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___COLLECTION_NAME` | `expert_agent_default` | Optional | `expert_agent_default` | Configuration value for vector stores pgvector DEFAULT collection name. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for vector stores pgvector DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___INDEXING__DISTANCE_METRIC` | `cosine` | Optional | `cosine` | Configuration value for vector stores pgvector DEFAULT indexing distance metric. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___INDEXING__INDEX_TYPE` | `ivfflat` | Optional | `ivfflat` | Configuration value for vector stores pgvector DEFAULT indexing index type. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___INDEXING__ANN_ALGORITHM` | `ivfflat` | Optional | `ivfflat` | Configuration value for vector stores pgvector DEFAULT indexing ann algorithm. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__IVFFLAT_LISTS` | `100` | Optional | `100` | Configuration value for vector stores pgvector DEFAULT options ivfflat lists. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__IVFFLAT_PROBES` | `10` | Optional | `10` | Configuration value for vector stores pgvector DEFAULT options ivfflat probes. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__HNSW_M` | `16` | Optional | `16` | Configuration value for vector stores pgvector DEFAULT options hnsw m. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__HNSW_EF_CONSTRUCTION` | `200` | Optional | `200` | Configuration value for vector stores pgvector DEFAULT options hnsw ef construction. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__HNSW_EF_SEARCH` | `-` | Optional | `<set as needed>` | Configuration value for vector stores pgvector DEFAULT options hnsw ef search. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__VECTOR_TYPE` | `vector` | Optional | `vector` | Configuration value for vector stores pgvector DEFAULT options vector type. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__ITERATIVE_SCAN` | `false` | Optional | `false` | Configuration value for vector stores pgvector DEFAULT options iterative scan. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__MAX_PROBES` | `-` | Optional | `<set as needed>` | Configuration value for vector stores pgvector DEFAULT options max probes. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__MAX_SCAN_TUPLES` | `-` | Optional | `<set as needed>` | Configuration value for vector stores pgvector DEFAULT options max scan tuples. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___SEARCH__LIMIT` | `5` | Optional | `5` | Configuration value for vector stores pgvector DEFAULT search limit. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores pgvector DEFAULT access control read groups. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores pgvector DEFAULT access control write groups. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__READ_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores pgvector DEFAULT access control read users. |
| `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores pgvector DEFAULT access control write users. |

## `vector_stores_config`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___HOST` | `localhost` | Optional | `0.0.0.0` | Host binding or upstream host for vector stores config chroma DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___PORT` | `8000` | Optional | `8000` | Port for vector stores config chroma DEFAULT connections. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___COLLECTION_NAME` | `expert_default` | Optional | `expert_default` | Configuration value for vector stores config chroma DEFAULT collection name. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for vector stores config chroma DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config chroma DEFAULT access control read groups. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config chroma DEFAULT access control write groups. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__READ_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config chroma DEFAULT access control read users. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config chroma DEFAULT access control write users. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___HOST` | `localhost` | Optional | `0.0.0.0` | Host binding or upstream host for vector stores config qdrant DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___PORT` | `6333` | Optional | `6333` | Port for vector stores config qdrant DEFAULT connections. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___API_KEY` | `-` | Deployment dependent | `your-api-key` | Credential or authentication setting for the related subsystem. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___COLLECTION_NAME` | `expert_agent_default` | Optional | `expert_agent_default` | Configuration value for vector stores config qdrant DEFAULT collection name. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ENABLED` | `true` | Optional | `true` | Toggle for vector stores config qdrant DEFAULT. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config qdrant DEFAULT access control read groups. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config qdrant DEFAULT access control write groups. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__READ_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config qdrant DEFAULT access control read users. |
| `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | `[]` | Optional | `<set as needed>` | Configuration value for vector stores config qdrant DEFAULT access control write users. |

## `web_server`

| Variable | Default | Required | Example | Description |
|----------|---------|----------|---------|-------------|
| `CLOUD_DOG__WEB_SERVER__HOST` | `0.0.0.0` | Optional | `0.0.0.0` | Host binding or upstream host for web server. |
| `CLOUD_DOG__WEB_SERVER__PORT` | `8080` | Optional | `8080` | Port for web server connections. |
| `CLOUD_DOG__WEB_SERVER__DEBUG` | `false` | Optional | `false` | Configuration value for web server debug. |
| `CLOUD_DOG__WEB_SERVER__LOG_FILE` | `/var/log/expert/web.log` | Optional | `/var/log/expert/web.log` | Configuration value for web server log file. |
| `CLOUD_DOG__WEB_SERVER__STATIC_PATH` | `./static` | Optional | `./static` | Configuration value for web server static path. |
| `CLOUD_DOG__WEB_SERVER__TEMPLATE_PATH` | `./templates` | Optional | `./templates` | Configuration value for web server template path. |
| `CLOUD_DOG__WEB_SERVER__ENABLED` | `true` | Optional | `true` | Toggle for web server. |

## Vault Support

| Variable | Purpose | Example |
|----------|---------|---------|
| `VAULT_ADDR` | Vault server URL when using secret-backed config resolution. | `https://your-vault-server` |
| `VAULT_TOKEN` | Token-based authentication for Vault when applicable. | `your-vault-token` |
| `VAULT_MOUNT_POINT` | Secret mount used by your Vault deployment. | `secret` |
| `VAULT_CONFIG_PATH` | Config path holding service settings. | `services/your-service` |
