---
template-id: T-PAR
template-version: 1.0
applies-to: docs/PARAMETERS.md
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

# Parameters

This reference is generated from `defaults.yaml`. Each key can be overridden by the corresponding environment variable.

## `a2a_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `a2a_server.host` | `0.0.0.0` | `CLOUD_DOG__A2A_SERVER__HOST` | Host binding or upstream host for a2a server. |
| `a2a_server.port` | `8082` | `CLOUD_DOG__A2A_SERVER__PORT` | Port for a2a server connections. |
| `a2a_server.debug` | `false` | `CLOUD_DOG__A2A_SERVER__DEBUG` | Configuration value for a2a server debug. |
| `a2a_server.log_file` | `/var/log/expert/a2a.log` | `CLOUD_DOG__A2A_SERVER__LOG_FILE` | Configuration value for a2a server log file. |
| `a2a_server.enabled` | `true` | `CLOUD_DOG__A2A_SERVER__ENABLED` | Toggle for a2a server. |

## `api_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `api_server.host` | `0.0.0.0` | `CLOUD_DOG__API_SERVER__HOST` | Host binding or upstream host for api server. |
| `api_server.port` | `8083` | `CLOUD_DOG__API_SERVER__PORT` | Port for api server connections. |
| `api_server.debug` | `false` | `CLOUD_DOG__API_SERVER__DEBUG` | Credential or authentication setting for the related subsystem. |
| `api_server.log_file` | `/var/log/expert/api.log` | `CLOUD_DOG__API_SERVER__LOG_FILE` | Credential or authentication setting for the related subsystem. |
| `api_server.enabled` | `true` | `CLOUD_DOG__API_SERVER__ENABLED` | Credential or authentication setting for the related subsystem. |

## `app`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `app.name` | `Expert Agent MCP Server` | `CLOUD_DOG__APP__NAME` | Configuration value for app name. |
| `app.version` | `0.1.0` | `CLOUD_DOG__APP__VERSION` | Configuration value for app version. |
| `app.environment` | `development` | `CLOUD_DOG__APP__ENVIRONMENT` | Configuration value for app environment. |
| `app.url` | `<set per environment>` | `CLOUD_DOG__APP__URL` | Endpoint or connection URL for app. |

## `auth`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `auth.provider` | `local` | `CLOUD_DOG__AUTH__PROVIDER` | Configuration value for auth provider. |
| `auth.jwt_secret` | `<secret>` | `CLOUD_DOG__AUTH__JWT_SECRET` | Credential or authentication setting for the related subsystem. |
| `auth.session_timeout_minutes` | `60` | `CLOUD_DOG__AUTH__SESSION_TIMEOUT_MINUTES` | Configuration value for auth session timeout minutes. |
| `auth.password_min_length` | `8` | `CLOUD_DOG__AUTH__PASSWORD_MIN_LENGTH` | Credential or authentication setting for the related subsystem. |
| `auth.password_require_complexity` | `true` | `CLOUD_DOG__AUTH__PASSWORD_REQUIRE_COMPLEXITY` | Credential or authentication setting for the related subsystem. |
| `auth.lockout_enabled` | `false` | `CLOUD_DOG__AUTH__LOCKOUT_ENABLED` | Toggle for auth lockout. |
| `auth.lockout_max_attempts` | `5` | `CLOUD_DOG__AUTH__LOCKOUT_MAX_ATTEMPTS` | Configuration value for auth lockout max attempts. |
| `auth.lockout_window_seconds` | `300` | `CLOUD_DOG__AUTH__LOCKOUT_WINDOW_SECONDS` | Timeout or duration control for auth lockout window. |
| `auth.lockout_seconds` | `300` | `CLOUD_DOG__AUTH__LOCKOUT_SECONDS` | Timeout or duration control for auth lockout. |

## `auth_providers`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `auth_providers.local.enabled` | `true` | `CLOUD_DOG__AUTH_PROVIDERS__LOCAL__ENABLED` | Toggle for auth providers local. |
| `auth_providers.google.enabled` | `false` | `CLOUD_DOG__AUTH_PROVIDERS__GOOGLE__ENABLED` | Toggle for auth providers google. |
| `auth_providers.google.client_id` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__GOOGLE__CLIENT_ID` | Configuration value for auth providers google client id. |
| `auth_providers.google.client_secret` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__GOOGLE__CLIENT_SECRET` | Credential or authentication setting for the related subsystem. |
| `auth_providers.linkedin.enabled` | `false` | `CLOUD_DOG__AUTH_PROVIDERS__LINKEDIN__ENABLED` | Toggle for auth providers linkedin. |
| `auth_providers.linkedin.client_id` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__LINKEDIN__CLIENT_ID` | Configuration value for auth providers linkedin client id. |
| `auth_providers.linkedin.client_secret` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__LINKEDIN__CLIENT_SECRET` | Credential or authentication setting for the related subsystem. |
| `auth_providers.keycloak.enabled` | `false` | `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__ENABLED` | Toggle for auth providers keycloak. |
| `auth_providers.keycloak.server_url` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__SERVER_URL` | Endpoint or connection URL for auth providers keycloak server. |
| `auth_providers.keycloak.realm` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__REALM` | Configuration value for auth providers keycloak realm. |
| `auth_providers.keycloak.client_id` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__CLIENT_ID` | Configuration value for auth providers keycloak client id. |
| `auth_providers.keycloak.client_secret` | `-` | `CLOUD_DOG__AUTH_PROVIDERS__KEYCLOAK__CLIENT_SECRET` | Credential or authentication setting for the related subsystem. |

## `cache`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `cache.enabled` | `true` | `CLOUD_DOG__CACHE__ENABLED` | Toggle for cache. |
| `cache.backend` | `memory` | `CLOUD_DOG__CACHE__BACKEND` | Configuration value for cache backend. |
| `cache.ttl_seconds` | `3600` | `CLOUD_DOG__CACHE__TTL_SECONDS` | Timeout or duration control for cache ttl. |
| `cache.max_entries` | `1000` | `CLOUD_DOG__CACHE__MAX_ENTRIES` | Configuration value for cache max entries. |

## `circuit`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `circuit.hard_error_threshold` | `5` | `CLOUD_DOG__CIRCUIT__HARD_ERROR_THRESHOLD` | Configuration value for circuit hard error threshold. |
| `circuit.soft_error_threshold` | `3` | `CLOUD_DOG__CIRCUIT__SOFT_ERROR_THRESHOLD` | Configuration value for circuit soft error threshold. |
| `circuit.reset_timeout_seconds` | `60` | `CLOUD_DOG__CIRCUIT__RESET_TIMEOUT_SECONDS` | Timeout or duration control for circuit reset timeout. |

## `db`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `db.uri` | `sqlite:///expert.db` | `CLOUD_DOG__DB__URI` | Endpoint or connection URL for db. |
| `db.pool_size` | `10` | `CLOUD_DOG__DB__POOL_SIZE` | Configuration value for db pool size. |
| `db.max_overflow` | `20` | `CLOUD_DOG__DB__MAX_OVERFLOW` | Configuration value for db max overflow. |
| `db.echo` | `false` | `CLOUD_DOG__DB__ECHO` | Configuration value for db echo. |

## `default_expert`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `default_expert` | `_DEFAULT_` | `CLOUD_DOG__DEFAULT_EXPERT` | Configuration value for default expert. |

## `embeddings`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `embeddings.provider` | `ollama` | `CLOUD_DOG__EMBEDDINGS__PROVIDER` | Configuration value for embeddings provider. |
| `embeddings.base_url` | `<set per environment>` | `CLOUD_DOG__EMBEDDINGS__BASE_URL` | Endpoint or connection URL for embeddings base. |
| `embeddings.model` | `bge-m3:567m` | `CLOUD_DOG__EMBEDDINGS__MODEL` | Configuration value for embeddings model. |
| `embeddings.dimension` | `1024` | `CLOUD_DOG__EMBEDDINGS__DIMENSION` | Configuration value for embeddings dimension. |
| `embeddings.batch_size` | `10` | `CLOUD_DOG__EMBEDDINGS__BATCH_SIZE` | Configuration value for embeddings batch size. |
| `embeddings.timeout` | `300` | `CLOUD_DOG__EMBEDDINGS__TIMEOUT` | Timeout or duration control for embeddings. |

## `experts`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `experts._DEFAULT_.name` | `General Assistant` | `CLOUD_DOG__EXPERTS___DEFAULT___NAME` | Configuration value for experts DEFAULT name. |
| `experts._DEFAULT_.title` | `General Purpose Expert` | `CLOUD_DOG__EXPERTS___DEFAULT___TITLE` | Configuration value for experts DEFAULT title. |
| `experts._DEFAULT_.description` | `A general purpose expert assistant for various tasks` | `CLOUD_DOG__EXPERTS___DEFAULT___DESCRIPTION` | Configuration value for experts DEFAULT description. |
| `experts._DEFAULT_.llm_provider` | `ollama` | `CLOUD_DOG__EXPERTS___DEFAULT___LLM_PROVIDER` | Configuration value for experts DEFAULT llm provider. |
| `experts._DEFAULT_.llm_model` | `qwen3:14b` | `CLOUD_DOG__EXPERTS___DEFAULT___LLM_MODEL` | Configuration value for experts DEFAULT llm model. |
| `experts._DEFAULT_.llm_temperature` | `0.7` | `CLOUD_DOG__EXPERTS___DEFAULT___LLM_TEMPERATURE` | Configuration value for experts DEFAULT llm temperature. |
| `experts._DEFAULT_.llm_max_tokens` | `1024` | `CLOUD_DOG__EXPERTS___DEFAULT___LLM_MAX_TOKENS` | Configuration value for experts DEFAULT llm max tokens. |
| `experts._DEFAULT_.enabled` | `true` | `CLOUD_DOG__EXPERTS___DEFAULT___ENABLED` | Toggle for experts DEFAULT. |
| `experts._DEFAULT_.history_enabled` | `true` | `CLOUD_DOG__EXPERTS___DEFAULT___HISTORY_ENABLED` | Toggle for experts DEFAULT history. |
| `experts._DEFAULT_.vector_store_enabled` | `true` | `CLOUD_DOG__EXPERTS___DEFAULT___VECTOR_STORE_ENABLED` | Toggle for experts DEFAULT vector store. |
| `experts._DEFAULT_.tools_enabled` | `false` | `CLOUD_DOG__EXPERTS___DEFAULT___TOOLS_ENABLED` | Toggle for experts DEFAULT tools. |
| `experts._DEFAULT_.access_control.public` | `false` | `CLOUD_DOG__EXPERTS___DEFAULT___ACCESS_CONTROL__PUBLIC` | Configuration value for experts DEFAULT access control public. |
| `experts._DEFAULT_.access_control.allowed_groups` | `[]` | `CLOUD_DOG__EXPERTS___DEFAULT___ACCESS_CONTROL__ALLOWED_GROUPS` | Configuration value for experts DEFAULT access control allowed groups. |
| `experts._DEFAULT_.access_control.allowed_users` | `[]` | `CLOUD_DOG__EXPERTS___DEFAULT___ACCESS_CONTROL__ALLOWED_USERS` | Configuration value for experts DEFAULT access control allowed users. |

## `llm`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `llm.provider` | `ollama` | `CLOUD_DOG__LLM__PROVIDER` | Configuration value for llm provider. |
| `llm.base_url` | `<set per environment>` | `CLOUD_DOG__LLM__BASE_URL` | Endpoint or connection URL for llm base. |
| `llm.model` | `qwen3:14b` | `CLOUD_DOG__LLM__MODEL` | Configuration value for llm model. |
| `llm.temperature` | `0.7` | `CLOUD_DOG__LLM__TEMPERATURE` | Configuration value for llm temperature. |
| `llm.top_k` | `40` | `CLOUD_DOG__LLM__TOP_K` | Configuration value for llm top k. |
| `llm.top_p` | `0.9` | `CLOUD_DOG__LLM__TOP_P` | Configuration value for llm top p. |
| `llm.max_tokens` | `1024` | `CLOUD_DOG__LLM__MAX_TOKENS` | Configuration value for llm max tokens. |
| `llm.timeout` | `300` | `CLOUD_DOG__LLM__TIMEOUT` | Timeout or duration control for llm. |
| `llm.default_system_prompt` | `You are a helpful expert assistant. Provide accurate, concise...` | `CLOUD_DOG__LLM__DEFAULT_SYSTEM_PROMPT` | Configuration value for llm default system prompt. |
| `llm.prompts.en` | `You are a helpful expert assistant. Provide accurate, concise...` | `CLOUD_DOG__LLM__PROMPTS__EN` | Configuration value for llm prompts en. |
| `llm.prompts.fr` | `Vous êtes un assistant expert utile. Fournissez des réponses ...` | `CLOUD_DOG__LLM__PROMPTS__FR` | Configuration value for llm prompts fr. |
| `llm.prompts.pl` | `Jesteś pomocnym asystentem eksperckim. Zapewniaj dokładne, zw...` | `CLOUD_DOG__LLM__PROMPTS__PL` | Configuration value for llm prompts pl. |

## `log`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `log.level` | `INFO` | `CLOUD_DOG__LOG__LEVEL` | Configuration value for log level. |
| `log.format` | `json` | `CLOUD_DOG__LOG__FORMAT` | Configuration value for log format. |
| `log.dump_config` | `false` | `CLOUD_DOG__LOG__DUMP_CONFIG` | Configuration value for log dump config. |
| `log.pii_redaction` | `true` | `CLOUD_DOG__LOG__PII_REDACTION` | Configuration value for log pii redaction. |
| `log.service_instance` | `${HOSTNAME:expert-agent-local}` | `CLOUD_DOG__LOG__SERVICE_INSTANCE` | Configuration value for log service instance. |
| `log.audit_log` | `logs/audit.log.jsonl` | `CLOUD_DOG__LOG__AUDIT_LOG` | Configuration value for log audit log. |
| `log.environment` | `${CLOUD_DOG_ENVIRONMENT:dev}` | `CLOUD_DOG__LOG__ENVIRONMENT` | Configuration value for log environment. |
| `log.retention.hot_days` | `14` | `CLOUD_DOG__LOG__RETENTION__HOT_DAYS` | Configuration value for log retention hot days. |
| `log.retention.cold_days` | `60` | `CLOUD_DOG__LOG__RETENTION__COLD_DAYS` | Configuration value for log retention cold days. |
| `log.retention.archive_format` | `gz` | `CLOUD_DOG__LOG__RETENTION__ARCHIVE_FORMAT` | Configuration value for log retention archive format. |
| `log.integrity.enabled` | `true` | `CLOUD_DOG__LOG__INTEGRITY__ENABLED` | Toggle for log integrity. |
| `log.integrity.interval_seconds` | `300` | `CLOUD_DOG__LOG__INTEGRITY__INTERVAL_SECONDS` | Timeout or duration control for log integrity interval. |
| `log.integrity.log_file` | `logs/audit-integrity.log` | `CLOUD_DOG__LOG__INTEGRITY__LOG_FILE` | Configuration value for log integrity log file. |
| `log.integrity.hash_algorithm` | `sha256` | `CLOUD_DOG__LOG__INTEGRITY__HASH_ALGORITHM` | Configuration value for log integrity hash algorithm. |
| `log.rotation.mode` | `size` | `CLOUD_DOG__LOG__ROTATION__MODE` | Configuration value for log rotation mode. |
| `log.rotation.max_bytes` | `10485760` | `CLOUD_DOG__LOG__ROTATION__MAX_BYTES` | Configuration value for log rotation max bytes. |
| `log.rotation.backup_count` | `10` | `CLOUD_DOG__LOG__ROTATION__BACKUP_COUNT` | Configuration value for log rotation backup count. |
| `log.rotation.when` | `midnight` | `CLOUD_DOG__LOG__ROTATION__WHEN` | Configuration value for log rotation when. |
| `log.rotation.interval` | `1` | `CLOUD_DOG__LOG__ROTATION__INTERVAL` | Configuration value for log rotation interval. |
| `log.rotation.compress` | `true` | `CLOUD_DOG__LOG__ROTATION__COMPRESS` | Configuration value for log rotation compress. |

## `mcp_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `mcp_server.host` | `0.0.0.0` | `CLOUD_DOG__MCP_SERVER__HOST` | Host binding or upstream host for mcp server. |
| `mcp_server.port` | `8081` | `CLOUD_DOG__MCP_SERVER__PORT` | Port for mcp server connections. |
| `mcp_server.debug` | `false` | `CLOUD_DOG__MCP_SERVER__DEBUG` | Configuration value for mcp server debug. |
| `mcp_server.log_file` | `/var/log/expert/mcp.log` | `CLOUD_DOG__MCP_SERVER__LOG_FILE` | Configuration value for mcp server log file. |
| `mcp_server.enabled` | `true` | `CLOUD_DOG__MCP_SERVER__ENABLED` | Toggle for mcp server. |
| `mcp_server.transport` | `sse` | `CLOUD_DOG__MCP_SERVER__TRANSPORT` | Configuration value for mcp server transport. |

## `metrics`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `metrics.enabled` | `true` | `CLOUD_DOG__METRICS__ENABLED` | Toggle for metrics. |
| `metrics.prometheus_endpoint` | `/metrics` | `CLOUD_DOG__METRICS__PROMETHEUS_ENDPOINT` | Configuration value for metrics prometheus endpoint. |
| `metrics.collection_interval_seconds` | `30` | `CLOUD_DOG__METRICS__COLLECTION_INTERVAL_SECONDS` | Timeout or duration control for metrics collection interval. |

## `multimedia`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `multimedia.storage_path` | `storage/multimedia` | `CLOUD_DOG__MULTIMEDIA__STORAGE_PATH` | Configuration value for multimedia storage path. |
| `multimedia.max_file_size_mb` | `10` | `CLOUD_DOG__MULTIMEDIA__MAX_FILE_SIZE_MB` | Configuration value for multimedia max file size mb. |
| `multimedia.supported_formats` | `["jpg", "png", "mp3", "mp4", "txt", "md"]` | `CLOUD_DOG__MULTIMEDIA__SUPPORTED_FORMATS` | Configuration value for multimedia supported formats. |

## `privacy`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `privacy.pii_removal_enabled` | `true` | `CLOUD_DOG__PRIVACY__PII_REMOVAL_ENABLED` | Toggle for privacy pii removal. |
| `privacy.pii_patterns` | `[{"pattern": "\\b\\d{3}-\\d{2}-\\d{4}\\b", "replacement": "[REDACTED_SSN]", "description": "Social Security Number"}, {"...` | `CLOUD_DOG__PRIVACY__PII_PATTERNS` | Configuration value for privacy pii patterns. |
| `privacy.data_encryption_at_rest` | `true` | `CLOUD_DOG__PRIVACY__DATA_ENCRYPTION_AT_REST` | Configuration value for privacy data encryption at rest. |
| `privacy.user_data_retention_days` | `365` | `CLOUD_DOG__PRIVACY__USER_DATA_RETENTION_DAYS` | Configuration value for privacy user data retention days. |

## `prompts`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `prompts.min_description_chars` | `30` | `CLOUD_DOG__PROMPTS__MIN_DESCRIPTION_CHARS` | Configuration value for prompts min description chars. |
| `prompts.entropy_min_unique_words` | `8` | `CLOUD_DOG__PROMPTS__ENTROPY_MIN_UNIQUE_WORDS` | Configuration value for prompts entropy min unique words. |
| `prompts.template_variables` | `["services", "tools", "sub_experts", "user", "session"]` | `CLOUD_DOG__PROMPTS__TEMPLATE_VARIABLES` | Configuration value for prompts template variables. |

## `queue`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `queue.max_retries` | `3` | `CLOUD_DOG__QUEUE__MAX_RETRIES` | Configuration value for queue max retries. |
| `queue.retry_delay_seconds` | `5` | `CLOUD_DOG__QUEUE__RETRY_DELAY_SECONDS` | Timeout or duration control for queue retry delay. |
| `queue.timeout_seconds` | `30` | `CLOUD_DOG__QUEUE__TIMEOUT_SECONDS` | Timeout or duration control for queue timeout. |

## `rate_limit`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `rate_limit.requests_per_minute` | `60` | `CLOUD_DOG__RATE_LIMIT__REQUESTS_PER_MINUTE` | Configuration value for rate limit requests per minute. |
| `rate_limit.burst_limit` | `10` | `CLOUD_DOG__RATE_LIMIT__BURST_LIMIT` | Configuration value for rate limit burst limit. |

## `redis`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `redis.host` | `localhost` | `CLOUD_DOG__REDIS__HOST` | Host binding or upstream host for redis. |
| `redis.port` | `6379` | `CLOUD_DOG__REDIS__PORT` | Port for redis connections. |
| `redis.db` | `0` | `CLOUD_DOG__REDIS__DB` | Configuration value for redis db. |
| `redis.username` | `-` | `CLOUD_DOG__REDIS__USERNAME` | Configuration value for redis username. |
| `redis.password` | `-` | `CLOUD_DOG__REDIS__PASSWORD` | Credential or authentication setting for the related subsystem. |
| `redis.token` | `-` | `CLOUD_DOG__REDIS__TOKEN` | Credential or authentication setting for the related subsystem. |
| `redis.ssl` | `false` | `CLOUD_DOG__REDIS__SSL` | Configuration value for redis ssl. |
| `redis.socket_connect_timeout_seconds` | `10` | `CLOUD_DOG__REDIS__SOCKET_CONNECT_TIMEOUT_SECONDS` | Timeout or duration control for redis socket connect timeout. |
| `redis.timeout` | `5` | `CLOUD_DOG__REDIS__TIMEOUT` | Timeout or duration control for redis. |

## `security`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `security.audit_secret_key` | `<secret>` | `CLOUD_DOG__SECURITY__AUDIT_SECRET_KEY` | Credential or authentication setting for the related subsystem. |

## `server_id`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `server_id` | `${HOSTNAME:expert-agent-local}` | `CLOUD_DOG__SERVER_ID` | Configuration value for server id. |

## `service_composition`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `service_composition.tool_discovery_cache_ttl` | `300` | `CLOUD_DOG__SERVICE_COMPOSITION__TOOL_DISCOVERY_CACHE_TTL` | Configuration value for service composition tool discovery cache ttl. |
| `service_composition.invocation_timeout` | `30` | `CLOUD_DOG__SERVICE_COMPOSITION__INVOCATION_TIMEOUT` | Timeout or duration control for service composition invocation. |
| `service_composition.circuit_breaker_threshold` | `5` | `CLOUD_DOG__SERVICE_COMPOSITION__CIRCUIT_BREAKER_THRESHOLD` | Configuration value for service composition circuit breaker threshold. |
| `service_composition.circuit_breaker_reset` | `60` | `CLOUD_DOG__SERVICE_COMPOSITION__CIRCUIT_BREAKER_RESET` | Configuration value for service composition circuit breaker reset. |
| `service_composition.max_delegation_depth` | `3` | `CLOUD_DOG__SERVICE_COMPOSITION__MAX_DELEGATION_DEPTH` | Configuration value for service composition max delegation depth. |
| `service_composition.transactional_session_persist` | `false` | `CLOUD_DOG__SERVICE_COMPOSITION__TRANSACTIONAL_SESSION_PERSIST` | Configuration value for service composition transactional session persist. |

## `session`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `session.default_ttl_hours` | `24` | `CLOUD_DOG__SESSION__DEFAULT_TTL_HOURS` | Configuration value for session default ttl hours. |
| `session.history_retention_days` | `30` | `CLOUD_DOG__SESSION__HISTORY_RETENTION_DAYS` | Configuration value for session history retention days. |
| `session.context_window_size` | `32768` | `CLOUD_DOG__SESSION__CONTEXT_WINDOW_SIZE` | Configuration value for session context window size. |
| `session.max_history_messages` | `100` | `CLOUD_DOG__SESSION__MAX_HISTORY_MESSAGES` | Configuration value for session max history messages. |
| `session.max_sessions_per_user` | `10` | `CLOUD_DOG__SESSION__MAX_SESSIONS_PER_USER` | Configuration value for session max sessions per user. |
| `session.max_sessions_per_group` | `50` | `CLOUD_DOG__SESSION__MAX_SESSIONS_PER_GROUP` | Configuration value for session max sessions per group. |
| `session.queue_enabled` | `true` | `CLOUD_DOG__SESSION__QUEUE_ENABLED` | Toggle for session queue. |

## `test`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `test.http_timeout_seconds` | `60` | `CLOUD_DOG__TEST__HTTP_TIMEOUT_SECONDS` | Timeout or duration control for test http timeout. |

## `tracing`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `tracing.enabled` | `false` | `CLOUD_DOG__TRACING__ENABLED` | Toggle for tracing. |
| `tracing.provider` | `jaeger` | `CLOUD_DOG__TRACING__PROVIDER` | Configuration value for tracing provider. |
| `tracing.endpoint` | `http://localhost:14268/api/traces` | `CLOUD_DOG__TRACING__ENDPOINT` | Configuration value for tracing endpoint. |

## `vault`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `vault.server` | `-` | `CLOUD_DOG__VAULT__SERVER` | Configuration value for vault server. |
| `vault.key` | `-` | `CLOUD_DOG__VAULT__KEY` | Credential or authentication setting for the related subsystem. |
| `vault.mount_point` | `-` | `CLOUD_DOG__VAULT__MOUNT_POINT` | Configuration value for vault mount point. |
| `vault.config_path` | `-` | `CLOUD_DOG__VAULT__CONFIG_PATH` | Configuration value for vault config path. |
| `vault.timeout_seconds` | `5` | `CLOUD_DOG__VAULT__TIMEOUT_SECONDS` | Timeout or duration control for vault timeout. |

## `vector_stores`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `vector_stores.common.indexing.distance_metric` | `cosine` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__DISTANCE_METRIC` | Configuration value for vector stores common indexing distance metric. |
| `vector_stores.common.indexing.index_type` | `ann` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__INDEX_TYPE` | Configuration value for vector stores common indexing index type. |
| `vector_stores.common.indexing.ann_algorithm` | `hnsw` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__ANN_ALGORITHM` | Configuration value for vector stores common indexing ann algorithm. |
| `vector_stores.common.indexing.compression_enabled` | `false` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__COMPRESSION_ENABLED` | Toggle for vector stores common indexing compression. |
| `vector_stores.common.indexing.quantization_type` | `-` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__QUANTIZATION_TYPE` | Configuration value for vector stores common indexing quantization type. |
| `vector_stores.common.indexing.shards` | `1` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__SHARDS` | Configuration value for vector stores common indexing shards. |
| `vector_stores.common.indexing.replicas` | `0` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__REPLICAS` | Configuration value for vector stores common indexing replicas. |
| `vector_stores.common.indexing.persistence` | `true` | `CLOUD_DOG__VECTOR_STORES__COMMON__INDEXING__PERSISTENCE` | Configuration value for vector stores common indexing persistence. |
| `vector_stores.common.search.limit` | `5` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__LIMIT` | Configuration value for vector stores common search limit. |
| `vector_stores.common.search.top_k` | `-` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__TOP_K` | Configuration value for vector stores common search top k. |
| `vector_stores.common.search.pre_filter` | `false` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__PRE_FILTER` | Configuration value for vector stores common search pre filter. |
| `vector_stores.common.search.offset` | `0` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__OFFSET` | Configuration value for vector stores common search offset. |
| `vector_stores.common.search.score_threshold` | `-` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__SCORE_THRESHOLD` | Configuration value for vector stores common search score threshold. |
| `vector_stores.common.search.min_score` | `-` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__MIN_SCORE` | Configuration value for vector stores common search min score. |
| `vector_stores.common.search.max_distance` | `-` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__MAX_DISTANCE` | Configuration value for vector stores common search max distance. |
| `vector_stores.common.search.include_vectors` | `false` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_VECTORS` | Configuration value for vector stores common search include vectors. |
| `vector_stores.common.search.include_metadata` | `true` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_METADATA` | Configuration value for vector stores common search include metadata. |
| `vector_stores.common.search.include_distances` | `true` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_DISTANCES` | Configuration value for vector stores common search include distances. |
| `vector_stores.common.search.include_scores` | `true` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__INCLUDE_SCORES` | Configuration value for vector stores common search include scores. |
| `vector_stores.common.search.hybrid_enabled` | `false` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__HYBRID_ENABLED` | Toggle for vector stores common search hybrid. |
| `vector_stores.common.search.hybrid_alpha` | `0.5` | `CLOUD_DOG__VECTOR_STORES__COMMON__SEARCH__HYBRID_ALPHA` | Configuration value for vector stores common search hybrid alpha. |
| `vector_stores.chroma._DEFAULT_.host` | `localhost` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___HOST` | Host binding or upstream host for vector stores chroma DEFAULT. |
| `vector_stores.chroma._DEFAULT_.port` | `8000` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___PORT` | Port for vector stores chroma DEFAULT connections. |
| `vector_stores.chroma._DEFAULT_.collection_name` | `expert_default` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___COLLECTION_NAME` | Configuration value for vector stores chroma DEFAULT collection name. |
| `vector_stores.chroma._DEFAULT_.enabled` | `true` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ENABLED` | Toggle for vector stores chroma DEFAULT. |
| `vector_stores.chroma._DEFAULT_.indexing.distance_metric` | `cosine` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___INDEXING__DISTANCE_METRIC` | Configuration value for vector stores chroma DEFAULT indexing distance metric. |
| `vector_stores.chroma._DEFAULT_.indexing.index_type` | `ann` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___INDEXING__INDEX_TYPE` | Configuration value for vector stores chroma DEFAULT indexing index type. |
| `vector_stores.chroma._DEFAULT_.indexing.ann_algorithm` | `hnsw` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___INDEXING__ANN_ALGORITHM` | Configuration value for vector stores chroma DEFAULT indexing ann algorithm. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_space` | `cosine` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_SPACE` | Configuration value for vector stores chroma DEFAULT options hnsw space. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_construction_ef` | `200` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_CONSTRUCTION_EF` | Configuration value for vector stores chroma DEFAULT options hnsw construction ef. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_M` | `16` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_M` | Configuration value for vector stores chroma DEFAULT options hnsw M. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_search_ef` | `50` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_SEARCH_EF` | Configuration value for vector stores chroma DEFAULT options hnsw search ef. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_num_threads` | `4` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_NUM_THREADS` | Configuration value for vector stores chroma DEFAULT options hnsw num threads. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_resize_factor` | `1.2` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_RESIZE_FACTOR` | Configuration value for vector stores chroma DEFAULT options hnsw resize factor. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_batch_size` | `100` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_BATCH_SIZE` | Configuration value for vector stores chroma DEFAULT options hnsw batch size. |
| `vector_stores.chroma._DEFAULT_.options.hnsw_sync_threshold` | `10000` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___OPTIONS__HNSW_SYNC_THRESHOLD` | Configuration value for vector stores chroma DEFAULT options hnsw sync threshold. |
| `vector_stores.chroma._DEFAULT_.search.limit` | `5` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___SEARCH__LIMIT` | Configuration value for vector stores chroma DEFAULT search limit. |
| `vector_stores.chroma._DEFAULT_.search.include` | `["metadatas", "documents", "distances"]` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___SEARCH__INCLUDE` | Configuration value for vector stores chroma DEFAULT search include. |
| `vector_stores.chroma._DEFAULT_.access_control.read_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | Configuration value for vector stores chroma DEFAULT access control read groups. |
| `vector_stores.chroma._DEFAULT_.access_control.write_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | Configuration value for vector stores chroma DEFAULT access control write groups. |
| `vector_stores.chroma._DEFAULT_.access_control.read_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__READ_USERS` | Configuration value for vector stores chroma DEFAULT access control read users. |
| `vector_stores.chroma._DEFAULT_.access_control.write_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | Configuration value for vector stores chroma DEFAULT access control write users. |
| `vector_stores.qdrant._DEFAULT_.host` | `localhost` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___HOST` | Host binding or upstream host for vector stores qdrant DEFAULT. |
| `vector_stores.qdrant._DEFAULT_.port` | `6333` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___PORT` | Port for vector stores qdrant DEFAULT connections. |
| `vector_stores.qdrant._DEFAULT_.api_key` | `-` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___API_KEY` | Credential or authentication setting for the related subsystem. |
| `vector_stores.qdrant._DEFAULT_.collection_name` | `expert_agent_default` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___COLLECTION_NAME` | Configuration value for vector stores qdrant DEFAULT collection name. |
| `vector_stores.qdrant._DEFAULT_.enabled` | `true` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ENABLED` | Toggle for vector stores qdrant DEFAULT. |
| `vector_stores.qdrant._DEFAULT_.indexing.distance_metric` | `cosine` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___INDEXING__DISTANCE_METRIC` | Configuration value for vector stores qdrant DEFAULT indexing distance metric. |
| `vector_stores.qdrant._DEFAULT_.indexing.index_type` | `ann` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___INDEXING__INDEX_TYPE` | Configuration value for vector stores qdrant DEFAULT indexing index type. |
| `vector_stores.qdrant._DEFAULT_.indexing.ann_algorithm` | `hnsw` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___INDEXING__ANN_ALGORITHM` | Configuration value for vector stores qdrant DEFAULT indexing ann algorithm. |
| `vector_stores.qdrant._DEFAULT_.options.hnsw_m` | `16` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_M` | Configuration value for vector stores qdrant DEFAULT options hnsw m. |
| `vector_stores.qdrant._DEFAULT_.options.hnsw_ef_construct` | `200` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_EF_CONSTRUCT` | Configuration value for vector stores qdrant DEFAULT options hnsw ef construct. |
| `vector_stores.qdrant._DEFAULT_.options.hnsw_full_scan_threshold` | `10000` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_FULL_SCAN_THRESHOLD` | Configuration value for vector stores qdrant DEFAULT options hnsw full scan threshold. |
| `vector_stores.qdrant._DEFAULT_.options.hnsw_max_indexing_threads` | `0` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_MAX_INDEXING_THREADS` | Configuration value for vector stores qdrant DEFAULT options hnsw max indexing threads. |
| `vector_stores.qdrant._DEFAULT_.options.hnsw_on_disk` | `false` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__HNSW_ON_DISK` | Configuration value for vector stores qdrant DEFAULT options hnsw on disk. |
| `vector_stores.qdrant._DEFAULT_.options.shard_number` | `1` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__SHARD_NUMBER` | Configuration value for vector stores qdrant DEFAULT options shard number. |
| `vector_stores.qdrant._DEFAULT_.options.sharding_method` | `auto` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__SHARDING_METHOD` | Configuration value for vector stores qdrant DEFAULT options sharding method. |
| `vector_stores.qdrant._DEFAULT_.options.replication_factor` | `1` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__REPLICATION_FACTOR` | Configuration value for vector stores qdrant DEFAULT options replication factor. |
| `vector_stores.qdrant._DEFAULT_.options.write_consistency_factor` | `1` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__WRITE_CONSISTENCY_FACTOR` | Configuration value for vector stores qdrant DEFAULT options write consistency factor. |
| `vector_stores.qdrant._DEFAULT_.options.read_fan_out_factor` | `1` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__READ_FAN_OUT_FACTOR` | Configuration value for vector stores qdrant DEFAULT options read fan out factor. |
| `vector_stores.qdrant._DEFAULT_.options.on_disk_payload` | `false` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__ON_DISK_PAYLOAD` | Configuration value for vector stores qdrant DEFAULT options on disk payload. |
| `vector_stores.qdrant._DEFAULT_.options.quantization_enabled` | `false` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__QUANTIZATION_ENABLED` | Toggle for vector stores qdrant DEFAULT options quantization. |
| `vector_stores.qdrant._DEFAULT_.options.quantization_type` | `scalar` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__QUANTIZATION_TYPE` | Configuration value for vector stores qdrant DEFAULT options quantization type. |
| `vector_stores.qdrant._DEFAULT_.options.quantization_always_ram` | `true` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___OPTIONS__QUANTIZATION_ALWAYS_RAM` | Configuration value for vector stores qdrant DEFAULT options quantization always ram. |
| `vector_stores.qdrant._DEFAULT_.search.limit` | `5` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___SEARCH__LIMIT` | Configuration value for vector stores qdrant DEFAULT search limit. |
| `vector_stores.qdrant._DEFAULT_.search.with_payload` | `true` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___SEARCH__WITH_PAYLOAD` | Configuration value for vector stores qdrant DEFAULT search with payload. |
| `vector_stores.qdrant._DEFAULT_.search.with_vector` | `false` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___SEARCH__WITH_VECTOR` | Configuration value for vector stores qdrant DEFAULT search with vector. |
| `vector_stores.qdrant._DEFAULT_.access_control.read_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | Configuration value for vector stores qdrant DEFAULT access control read groups. |
| `vector_stores.qdrant._DEFAULT_.access_control.write_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | Configuration value for vector stores qdrant DEFAULT access control write groups. |
| `vector_stores.qdrant._DEFAULT_.access_control.read_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__READ_USERS` | Configuration value for vector stores qdrant DEFAULT access control read users. |
| `vector_stores.qdrant._DEFAULT_.access_control.write_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | Configuration value for vector stores qdrant DEFAULT access control write users. |
| `vector_stores.opensearch._DEFAULT_.host` | `localhost` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___HOST` | Host binding or upstream host for vector stores opensearch DEFAULT. |
| `vector_stores.opensearch._DEFAULT_.port` | `1201` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___PORT` | Port for vector stores opensearch DEFAULT connections. |
| `vector_stores.opensearch._DEFAULT_.username` | `-` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___USERNAME` | Configuration value for vector stores opensearch DEFAULT username. |
| `vector_stores.opensearch._DEFAULT_.password` | `-` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___PASSWORD` | Credential or authentication setting for the related subsystem. |
| `vector_stores.opensearch._DEFAULT_.collection_name` | `expert_agent_default` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___COLLECTION_NAME` | Configuration value for vector stores opensearch DEFAULT collection name. |
| `vector_stores.opensearch._DEFAULT_.enabled` | `true` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ENABLED` | Toggle for vector stores opensearch DEFAULT. |
| `vector_stores.opensearch._DEFAULT_.indexing.distance_metric` | `cosine` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___INDEXING__DISTANCE_METRIC` | Configuration value for vector stores opensearch DEFAULT indexing distance metric. |
| `vector_stores.opensearch._DEFAULT_.indexing.index_type` | `ann` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___INDEXING__INDEX_TYPE` | Configuration value for vector stores opensearch DEFAULT indexing index type. |
| `vector_stores.opensearch._DEFAULT_.indexing.ann_algorithm` | `hnsw` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___INDEXING__ANN_ALGORITHM` | Configuration value for vector stores opensearch DEFAULT indexing ann algorithm. |
| `vector_stores.opensearch._DEFAULT_.options.space_type` | `cosinesimil` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__SPACE_TYPE` | Configuration value for vector stores opensearch DEFAULT options space type. |
| `vector_stores.opensearch._DEFAULT_.options.method` | `hnsw` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__METHOD` | Configuration value for vector stores opensearch DEFAULT options method. |
| `vector_stores.opensearch._DEFAULT_.options.engine` | `nmslib` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__ENGINE` | Configuration value for vector stores opensearch DEFAULT options engine. |
| `vector_stores.opensearch._DEFAULT_.options.ef_construction` | `128` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__EF_CONSTRUCTION` | Configuration value for vector stores opensearch DEFAULT options ef construction. |
| `vector_stores.opensearch._DEFAULT_.options.m` | `24` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__M` | Configuration value for vector stores opensearch DEFAULT options m. |
| `vector_stores.opensearch._DEFAULT_.options.ef_search` | `100` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__EF_SEARCH` | Configuration value for vector stores opensearch DEFAULT options ef search. |
| `vector_stores.opensearch._DEFAULT_.options.index_knn` | `true` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__INDEX_KNN` | Configuration value for vector stores opensearch DEFAULT options index knn. |
| `vector_stores.opensearch._DEFAULT_.options.index_knn_algo_param_ef_search` | `100` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___OPTIONS__INDEX_KNN_ALGO_PARAM_EF_SEARCH` | Configuration value for vector stores opensearch DEFAULT options index knn algo param ef search. |
| `vector_stores.opensearch._DEFAULT_.search.limit` | `5` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___SEARCH__LIMIT` | Configuration value for vector stores opensearch DEFAULT search limit. |
| `vector_stores.opensearch._DEFAULT_.search.k` | `-` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___SEARCH__K` | Configuration value for vector stores opensearch DEFAULT search k. |
| `vector_stores.opensearch._DEFAULT_.access_control.read_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | Configuration value for vector stores opensearch DEFAULT access control read groups. |
| `vector_stores.opensearch._DEFAULT_.access_control.write_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | Configuration value for vector stores opensearch DEFAULT access control write groups. |
| `vector_stores.opensearch._DEFAULT_.access_control.read_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__READ_USERS` | Configuration value for vector stores opensearch DEFAULT access control read users. |
| `vector_stores.opensearch._DEFAULT_.access_control.write_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__OPENSEARCH___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | Configuration value for vector stores opensearch DEFAULT access control write users. |
| `vector_stores.weaviate._DEFAULT_.url` | `http://localhost:8080` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___URL` | Endpoint or connection URL for vector stores weaviate DEFAULT. |
| `vector_stores.weaviate._DEFAULT_.api_key` | `-` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___API_KEY` | Credential or authentication setting for the related subsystem. |
| `vector_stores.weaviate._DEFAULT_.collection_name` | `expert_agent_default` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___COLLECTION_NAME` | Configuration value for vector stores weaviate DEFAULT collection name. |
| `vector_stores.weaviate._DEFAULT_.enabled` | `true` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ENABLED` | Toggle for vector stores weaviate DEFAULT. |
| `vector_stores.weaviate._DEFAULT_.indexing.distance_metric` | `cosine` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___INDEXING__DISTANCE_METRIC` | Configuration value for vector stores weaviate DEFAULT indexing distance metric. |
| `vector_stores.weaviate._DEFAULT_.indexing.index_type` | `ann` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___INDEXING__INDEX_TYPE` | Configuration value for vector stores weaviate DEFAULT indexing index type. |
| `vector_stores.weaviate._DEFAULT_.indexing.ann_algorithm` | `hnsw` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___INDEXING__ANN_ALGORITHM` | Configuration value for vector stores weaviate DEFAULT indexing ann algorithm. |
| `vector_stores.weaviate._DEFAULT_.options.vector_index_type` | `hnsw` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__VECTOR_INDEX_TYPE` | Configuration value for vector stores weaviate DEFAULT options vector index type. |
| `vector_stores.weaviate._DEFAULT_.options.ef_construction` | `128` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__EF_CONSTRUCTION` | Configuration value for vector stores weaviate DEFAULT options ef construction. |
| `vector_stores.weaviate._DEFAULT_.options.max_connections` | `64` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__MAX_CONNECTIONS` | Configuration value for vector stores weaviate DEFAULT options max connections. |
| `vector_stores.weaviate._DEFAULT_.options.dynamic_ef_min` | `100` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__DYNAMIC_EF_MIN` | Configuration value for vector stores weaviate DEFAULT options dynamic ef min. |
| `vector_stores.weaviate._DEFAULT_.options.dynamic_ef_max` | `500` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__DYNAMIC_EF_MAX` | Configuration value for vector stores weaviate DEFAULT options dynamic ef max. |
| `vector_stores.weaviate._DEFAULT_.options.dynamic_ef_factor` | `8` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__DYNAMIC_EF_FACTOR` | Configuration value for vector stores weaviate DEFAULT options dynamic ef factor. |
| `vector_stores.weaviate._DEFAULT_.options.filter_strategy` | `acorn` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__FILTER_STRATEGY` | Configuration value for vector stores weaviate DEFAULT options filter strategy. |
| `vector_stores.weaviate._DEFAULT_.options.flat_search_cutoff` | `40000` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__FLAT_SEARCH_CUTOFF` | Configuration value for vector stores weaviate DEFAULT options flat search cutoff. |
| `vector_stores.weaviate._DEFAULT_.options.vector_cache_max_objects` | `1000000000` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___OPTIONS__VECTOR_CACHE_MAX_OBJECTS` | Configuration value for vector stores weaviate DEFAULT options vector cache max objects. |
| `vector_stores.weaviate._DEFAULT_.search.limit` | `5` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___SEARCH__LIMIT` | Configuration value for vector stores weaviate DEFAULT search limit. |
| `vector_stores.weaviate._DEFAULT_.search.alpha` | `0.5` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___SEARCH__ALPHA` | Configuration value for vector stores weaviate DEFAULT search alpha. |
| `vector_stores.weaviate._DEFAULT_.search.fusion_strategy` | `ranked` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___SEARCH__FUSION_STRATEGY` | Configuration value for vector stores weaviate DEFAULT search fusion strategy. |
| `vector_stores.weaviate._DEFAULT_.access_control.read_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | Configuration value for vector stores weaviate DEFAULT access control read groups. |
| `vector_stores.weaviate._DEFAULT_.access_control.write_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | Configuration value for vector stores weaviate DEFAULT access control write groups. |
| `vector_stores.weaviate._DEFAULT_.access_control.read_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__READ_USERS` | Configuration value for vector stores weaviate DEFAULT access control read users. |
| `vector_stores.weaviate._DEFAULT_.access_control.write_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__WEAVIATE___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | Configuration value for vector stores weaviate DEFAULT access control write users. |
| `vector_stores.pgvector._DEFAULT_.host` | `localhost` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___HOST` | Host binding or upstream host for vector stores pgvector DEFAULT. |
| `vector_stores.pgvector._DEFAULT_.port` | `5432` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___PORT` | Port for vector stores pgvector DEFAULT connections. |
| `vector_stores.pgvector._DEFAULT_.database` | `expert_agent` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___DATABASE` | Configuration value for vector stores pgvector DEFAULT database. |
| `vector_stores.pgvector._DEFAULT_.username` | `postgres` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___USERNAME` | Configuration value for vector stores pgvector DEFAULT username. |
| `vector_stores.pgvector._DEFAULT_.password` | `-` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___PASSWORD` | Credential or authentication setting for the related subsystem. |
| `vector_stores.pgvector._DEFAULT_.collection_name` | `expert_agent_default` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___COLLECTION_NAME` | Configuration value for vector stores pgvector DEFAULT collection name. |
| `vector_stores.pgvector._DEFAULT_.enabled` | `true` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ENABLED` | Toggle for vector stores pgvector DEFAULT. |
| `vector_stores.pgvector._DEFAULT_.indexing.distance_metric` | `cosine` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___INDEXING__DISTANCE_METRIC` | Configuration value for vector stores pgvector DEFAULT indexing distance metric. |
| `vector_stores.pgvector._DEFAULT_.indexing.index_type` | `ivfflat` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___INDEXING__INDEX_TYPE` | Configuration value for vector stores pgvector DEFAULT indexing index type. |
| `vector_stores.pgvector._DEFAULT_.indexing.ann_algorithm` | `ivfflat` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___INDEXING__ANN_ALGORITHM` | Configuration value for vector stores pgvector DEFAULT indexing ann algorithm. |
| `vector_stores.pgvector._DEFAULT_.options.ivfflat_lists` | `100` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__IVFFLAT_LISTS` | Configuration value for vector stores pgvector DEFAULT options ivfflat lists. |
| `vector_stores.pgvector._DEFAULT_.options.ivfflat_probes` | `10` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__IVFFLAT_PROBES` | Configuration value for vector stores pgvector DEFAULT options ivfflat probes. |
| `vector_stores.pgvector._DEFAULT_.options.hnsw_m` | `16` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__HNSW_M` | Configuration value for vector stores pgvector DEFAULT options hnsw m. |
| `vector_stores.pgvector._DEFAULT_.options.hnsw_ef_construction` | `200` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__HNSW_EF_CONSTRUCTION` | Configuration value for vector stores pgvector DEFAULT options hnsw ef construction. |
| `vector_stores.pgvector._DEFAULT_.options.hnsw_ef_search` | `-` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__HNSW_EF_SEARCH` | Configuration value for vector stores pgvector DEFAULT options hnsw ef search. |
| `vector_stores.pgvector._DEFAULT_.options.vector_type` | `vector` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__VECTOR_TYPE` | Configuration value for vector stores pgvector DEFAULT options vector type. |
| `vector_stores.pgvector._DEFAULT_.options.iterative_scan` | `false` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__ITERATIVE_SCAN` | Configuration value for vector stores pgvector DEFAULT options iterative scan. |
| `vector_stores.pgvector._DEFAULT_.options.max_probes` | `-` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__MAX_PROBES` | Configuration value for vector stores pgvector DEFAULT options max probes. |
| `vector_stores.pgvector._DEFAULT_.options.max_scan_tuples` | `-` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___OPTIONS__MAX_SCAN_TUPLES` | Configuration value for vector stores pgvector DEFAULT options max scan tuples. |
| `vector_stores.pgvector._DEFAULT_.search.limit` | `5` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___SEARCH__LIMIT` | Configuration value for vector stores pgvector DEFAULT search limit. |
| `vector_stores.pgvector._DEFAULT_.access_control.read_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | Configuration value for vector stores pgvector DEFAULT access control read groups. |
| `vector_stores.pgvector._DEFAULT_.access_control.write_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | Configuration value for vector stores pgvector DEFAULT access control write groups. |
| `vector_stores.pgvector._DEFAULT_.access_control.read_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__READ_USERS` | Configuration value for vector stores pgvector DEFAULT access control read users. |
| `vector_stores.pgvector._DEFAULT_.access_control.write_users` | `[]` | `CLOUD_DOG__VECTOR_STORES__PGVECTOR___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | Configuration value for vector stores pgvector DEFAULT access control write users. |

## `vector_stores_config`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `vector_stores_config.chroma._DEFAULT_.host` | `localhost` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___HOST` | Host binding or upstream host for vector stores config chroma DEFAULT. |
| `vector_stores_config.chroma._DEFAULT_.port` | `8000` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___PORT` | Port for vector stores config chroma DEFAULT connections. |
| `vector_stores_config.chroma._DEFAULT_.collection_name` | `expert_default` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___COLLECTION_NAME` | Configuration value for vector stores config chroma DEFAULT collection name. |
| `vector_stores_config.chroma._DEFAULT_.enabled` | `true` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ENABLED` | Toggle for vector stores config chroma DEFAULT. |
| `vector_stores_config.chroma._DEFAULT_.access_control.read_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | Configuration value for vector stores config chroma DEFAULT access control read groups. |
| `vector_stores_config.chroma._DEFAULT_.access_control.write_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | Configuration value for vector stores config chroma DEFAULT access control write groups. |
| `vector_stores_config.chroma._DEFAULT_.access_control.read_users` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__READ_USERS` | Configuration value for vector stores config chroma DEFAULT access control read users. |
| `vector_stores_config.chroma._DEFAULT_.access_control.write_users` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__CHROMA___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | Configuration value for vector stores config chroma DEFAULT access control write users. |
| `vector_stores_config.qdrant._DEFAULT_.host` | `localhost` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___HOST` | Host binding or upstream host for vector stores config qdrant DEFAULT. |
| `vector_stores_config.qdrant._DEFAULT_.port` | `6333` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___PORT` | Port for vector stores config qdrant DEFAULT connections. |
| `vector_stores_config.qdrant._DEFAULT_.api_key` | `-` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___API_KEY` | Credential or authentication setting for the related subsystem. |
| `vector_stores_config.qdrant._DEFAULT_.collection_name` | `expert_agent_default` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___COLLECTION_NAME` | Configuration value for vector stores config qdrant DEFAULT collection name. |
| `vector_stores_config.qdrant._DEFAULT_.enabled` | `true` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ENABLED` | Toggle for vector stores config qdrant DEFAULT. |
| `vector_stores_config.qdrant._DEFAULT_.access_control.read_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__READ_GROUPS` | Configuration value for vector stores config qdrant DEFAULT access control read groups. |
| `vector_stores_config.qdrant._DEFAULT_.access_control.write_groups` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_GROUPS` | Configuration value for vector stores config qdrant DEFAULT access control write groups. |
| `vector_stores_config.qdrant._DEFAULT_.access_control.read_users` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__READ_USERS` | Configuration value for vector stores config qdrant DEFAULT access control read users. |
| `vector_stores_config.qdrant._DEFAULT_.access_control.write_users` | `[]` | `CLOUD_DOG__VECTOR_STORES_CONFIG__QDRANT___DEFAULT___ACCESS_CONTROL__WRITE_USERS` | Configuration value for vector stores config qdrant DEFAULT access control write users. |

## `web_server`

| Key | Default | Environment Override | Description |
|-----|---------|----------------------|-------------|
| `web_server.host` | `0.0.0.0` | `CLOUD_DOG__WEB_SERVER__HOST` | Host binding or upstream host for web server. |
| `web_server.port` | `8080` | `CLOUD_DOG__WEB_SERVER__PORT` | Port for web server connections. |
| `web_server.debug` | `false` | `CLOUD_DOG__WEB_SERVER__DEBUG` | Configuration value for web server debug. |
| `web_server.log_file` | `/var/log/expert/web.log` | `CLOUD_DOG__WEB_SERVER__LOG_FILE` | Configuration value for web server log file. |
| `web_server.static_path` | `./static` | `CLOUD_DOG__WEB_SERVER__STATIC_PATH` | Configuration value for web server static path. |
| `web_server.template_path` | `./templates` | `CLOUD_DOG__WEB_SERVER__TEMPLATE_PATH` | Configuration value for web server template path. |
| `web_server.enabled` | `true` | `CLOUD_DOG__WEB_SERVER__ENABLED` | Toggle for web server. |
