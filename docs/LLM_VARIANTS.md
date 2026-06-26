# expert-agent LLM Variants: Settings and Test Success

## Purpose

- Record the expert-agent LLM variants that are validated in the current evidence set, without inventing model settings or reproducing secret-bearing env values.
- Align this service document with platform package and documentation rules: use the single LLM interface, keep config-driven provider selection, and publish permanent docs under `docs/` rather than `working/` (`cloud-dog-ai-platform-standards/RULES.md:61-86,577-616`, `cloud-dog-ai-platform-standards/docs/standards/50-llm-interfaces.md:17-28,33-65,363-412,478-500`).

## Platform-Package Usage (§1.4)

- `src/common/llm_client.py` is the service's single LLM interface and wraps `cloud_dog_llm` instead of implementing provider adapters locally. The module states that purpose in its docstring, imports the platform request/message/session types and error taxonomy, builds the platform config, and initializes the runtime client through `get_llm_client(...)` (`expert-agent-mcp-server/src/common/llm_client.py:18-20,32-41,87-92,122-145`).
- `src/config/loader.py` is explicitly a compatibility layer over `cloud_dog_config`, and imports the platform config loader plus env parsing helpers rather than replacing them (`expert-agent-mcp-server/src/config/loader.py:20-21,39-43`).
- Honest MCP transport classification per §6.21: expert-agent's MCP transport code is still a **server-side bespoke transport surface**, not a client-side MCP abstraction. The file implements JSON-RPC `initialize/tools/list/tools/call`, streamable HTTP `/mcp`, HTTP JSON-RPC `/messages`, legacy SSE `/sse` + `/message`, and stdio handling (`expert-agent-mcp-server/src/servers/mcp/server.py:457-550,680-830,884-910`). W28A-927m classifies this exact file as server-side and recommends later migration work rather than claiming the migration is already complete (`cloud-dog-ai-platform-standards/working/W28A-927m-MCP-TRANSPORT-5-SERVICE-AUDIT-REPORT.md:30,53-54`; `cloud-dog-ai-platform-standards/AGENT-LESSONS.md:749-780`).

## Shared Runtime Defaults

- Service defaults remain provider-agnostic but currently pin the default runtime to `provider=ollama`, `model=qwen3:14b`, `temperature=0.7`, `top_k=40`, `top_p=0.9`, `max_tokens=1024`, and `timeout=300` (`expert-agent-mcp-server/defaults.yaml:63-72`).
- The committed AT baseline narrows the runtime for test execution to `provider=ollama`, `model=qwen3:14b`, and `timeout=90`, with AT retry controls and longer HTTP budgets defined under `expert.test.*` (`expert-agent-mcp-server/tests/env-AT:5-10,37-40`).
- The MariaDB and Postgres AT overlays preserve the same LLM baseline, while the local-docker AT overlay keeps the same qwen3 baseline on docker-local ports (`expert-agent-mcp-server/tests/env-AT-mariadb:5-10,35-39`, `expert-agent-mcp-server/tests/env-AT-postgres:5-10,35-39`, `expert-agent-mcp-server/tests/env-AT-local-docker:153-171`).
- Delegation depth is part of the shared execution contract rather than a per-model tweak: defaults set `service_composition.max_delegation_depth=3`, the env and parameter references expose the same value, and `DelegationManager` enforces the bound-or-default `max_depth` at runtime (`expert-agent-mcp-server/defaults.yaml:101-107`, `expert-agent-mcp-server/docs/ENV-REFERENCE.md:262`, `expert-agent-mcp-server/docs/PARAMETERS.md:262`, `expert-agent-mcp-server/src/core/expert/delegation.py:74-76`).

## Ollama Variants

### Variant A: Ollama / `qwen3:14b`

- **Provider**: `ollama`
- **Model**: `qwen3:14b`
- **Endpoint class**: `llm1` in the validated matrix
- **Env profile**: the committed AT env files still pin qwen3 on the shared baseline, while the validated `llm1` routing is preserved in the W28A-926a matrix evidence (`expert-agent-mcp-server/tests/env-AT:37-40`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:26-29`)
- **Settings**: shared defaults remain `temperature=0.7`, `top_k=40`, `top_p=0.9`, `max_tokens=1024`, `timeout=300`; the AT baseline adds retry budgets and a narrower `timeout=90` test overlay (`expert-agent-mcp-server/defaults.yaml:63-72`, `expert-agent-mcp-server/tests/env-AT:5-10,37-40`)
- **Coverage**: smoke `5/5`; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:28`)

### Variant B: Ollama / `qwen3.5:9b`

- **Provider**: `ollama`
- **Model**: `qwen3.5:9b`
- **Endpoint class**: `llm1`
- **Env profile**: no dedicated committed per-model env file is preserved; the validated run used generated matrix env overrides layered on top of the shared AT baseline (`expert-agent-mcp-server/tests/env-AT:37-40`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:29,61-70,126-130`)
- **Settings**: validated with the shared defaults plus a matrix-specific `NUM_CTX=16384` lesson and an `LLM__TIMEOUT=240` override to avoid aborting inside the AT envelope (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:29,61-70,126-130`)
- **Coverage**: smoke `5/5`; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:29`)

### Variant C: Ollama / `gemma4:e4b`

- **Provider**: `ollama`
- **Model**: `gemma4:e4b`
- **Endpoint class**: `llm1`
- **Env profile**: shared AT baseline plus per-run matrix override; no separate committed env block is preserved for this model (`expert-agent-mcp-server/tests/env-AT:37-40`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:30`)
- **Settings**: no model-specific override is recorded beyond the normal defaults/baseline pairing (`expert-agent-mcp-server/defaults.yaml:63-72`, `expert-agent-mcp-server/tests/env-AT:5-10,37-40`)
- **Coverage**: smoke `5/5`; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:30`)

### Variant D: Ollama / `qwen3.5:27b`

- **Provider**: `ollama`
- **Model**: `qwen3.5:27b`
- **Endpoint class**: `llm2`
- **Env profile**: shared AT baseline plus per-run matrix override; validated endpoint comes from the 926a matrix row (`expert-agent-mcp-server/tests/env-AT:37-40`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:31`)
- **Settings**: no committed model-specific override is preserved beyond the shared defaults and AT retry/timeout controls (`expert-agent-mcp-server/defaults.yaml:63-72`, `expert-agent-mcp-server/tests/env-AT:5-10,37-40`)
- **Coverage**: smoke `5/5`; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:31`)

### Variant E: Ollama / `ibm/granite4:tiny-h`

- **Provider**: `ollama`
- **Model**: `ibm/granite4:tiny-h`
- **Endpoint class**: `llm2`
- **Env profile**: shared AT baseline plus per-run matrix override (`expert-agent-mcp-server/tests/env-AT:37-40`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:32`)
- **Settings**: this run required the stricter out-of-scope refusal prompt and `temperature=0.0`, which is the only per-model tuning called out in the preserved evidence (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:32`)
- **Coverage**: smoke `5/5`; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:32`)

### Variant F: Ollama / `ibm/granite4:small-h`

- **Provider**: `ollama`
- **Model**: `ibm/granite4:small-h`
- **Endpoint class**: `llm2`
- **Env profile**: shared AT baseline plus per-run matrix override (`expert-agent-mcp-server/tests/env-AT:37-40`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:33`)
- **Settings**: no committed model-specific override is preserved beyond the shared defaults and AT retry/timeout controls (`expert-agent-mcp-server/defaults.yaml:63-72`, `expert-agent-mcp-server/tests/env-AT:5-10,37-40`)
- **Coverage**: smoke `5/5`; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:33`)

### Variant G: Ollama / `gemma4:26b`

- **Provider**: `ollama`
- **Model**: `gemma4:26b`
- **Endpoint class**: `llm2`
- **Env profile**: shared AT baseline plus per-run matrix override (`expert-agent-mcp-server/tests/env-AT:37-40`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:34`)
- **Settings**: no committed model-specific override is preserved beyond the shared defaults and AT retry/timeout controls (`expert-agent-mcp-server/defaults.yaml:63-72`, `expert-agent-mcp-server/tests/env-AT:5-10,37-40`)
- **Coverage**: smoke `5/5`; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:34`)

## OpenRouter Variants

- OpenRouter in this service is configured through the `openai` provider path rather than a bespoke `openrouter` provider. The project lesson records the required override pattern: set `CLOUD_DOG__EXPERT__LLM__PROVIDER=openai`, point the base URL at the OpenRouter-compatible endpoint, and pass the model as a provider/model identifier; no service code changes are required because `cloud_dog_llm` handles the provider abstraction (`expert-agent-mcp-server/AGENT-LESSONS.md:434-447`).
- W28A-926b fixes the shared runtime envelope for the OpenRouter phase: provider `openai`, OpenRouter-compatible endpoint, timeout `120s`, and the exact 160-test AT subset made of AT1.1, AT1.11, AT1.12, AT1.16, AT1.101, and AT1.102 (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:12-20`; `expert-agent-mcp-server/AGENT-LESSONS.md:460-472`).
- The committed `tests/env-AT*` files remain Ollama/qwen3 baselines; OpenRouter model switching was done through runtime env overrides per config precedence rather than committed env-file rewrites (`expert-agent-mcp-server/tests/env-AT:37-40,61-67`, `expert-agent-mcp-server/AGENT-LESSONS.md:443-447`).

### Variant H: OpenRouter / `qwen/qwen3.5-27b`

- **Provider**: `openai` (OpenRouter-compatible)
- **Model**: `qwen/qwen3.5-27b`
- **Endpoint class**: OpenRouter-compatible gateway
- **Env profile**: runtime env override layered over the committed AT baseline (`expert-agent-mcp-server/AGENT-LESSONS.md:443-447`)
- **Settings**: provider `openai`, OpenRouter-compatible endpoint, timeout `120s` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:16-20`)
- **Coverage**: smoke PASS; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:24-30`)

### Variant I: OpenRouter / `qwen/qwen3.5-35b-a3b`

- **Provider**: `openai` (OpenRouter-compatible)
- **Model**: `qwen/qwen3.5-35b-a3b`
- **Endpoint class**: OpenRouter-compatible gateway
- **Env profile**: runtime env override layered over the committed AT baseline (`expert-agent-mcp-server/AGENT-LESSONS.md:443-447`)
- **Settings**: provider `openai`, OpenRouter-compatible endpoint, timeout `120s` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:16-20`)
- **Coverage**: smoke PASS; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:24-30`)

### Variant J: OpenRouter / `openai/gpt-5.4`

- **Provider**: `openai` (OpenRouter-compatible)
- **Model**: `openai/gpt-5.4`
- **Endpoint class**: OpenRouter-compatible gateway
- **Env profile**: runtime env override layered over the committed AT baseline (`expert-agent-mcp-server/AGENT-LESSONS.md:443-447`)
- **Settings**: provider `openai`, OpenRouter-compatible endpoint, timeout `120s` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:16-20`)
- **Coverage**: smoke PASS; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:24-30`)

### Variant K: OpenRouter / `google/gemma-4-31b-it`

- **Provider**: `openai` (OpenRouter-compatible)
- **Model**: `google/gemma-4-31b-it`
- **Endpoint class**: OpenRouter-compatible gateway
- **Env profile**: runtime env override layered over the committed AT baseline (`expert-agent-mcp-server/AGENT-LESSONS.md:443-447`)
- **Settings**: provider `openai`, OpenRouter-compatible endpoint, timeout `120s` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:16-20`)
- **Coverage**: smoke PASS; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:24-30`)

### Variant L: OpenRouter / `anthropic/claude-sonnet-4.6`

- **Provider**: `openai` (OpenRouter-compatible)
- **Model**: `anthropic/claude-sonnet-4.6`
- **Endpoint class**: OpenRouter-compatible gateway
- **Env profile**: runtime env override layered over the committed AT baseline (`expert-agent-mcp-server/AGENT-LESSONS.md:443-447`)
- **Settings**: provider `openai`, OpenRouter-compatible endpoint, timeout `120s` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:16-20`)
- **Coverage**: smoke PASS; AT subset `160/160` (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:24-30`)

## Capability Coverage

| Capability | Evidence | Coverage status |
|---|---|---|
| LLM validation and reasoning-quality smoke | AT1.101 validates prompt and LLM connectivity, while AT1.102 submits a real async channel chat, evaluates quality metrics, stores feedback, and re-reads the job quality record (`expert-agent-mcp-server/tests/application/AT1.101_LLMValidationTesting/test_llm_validation_testing.py:32-66`, `expert-agent-mcp-server/tests/application/AT1.102_ResponseQualityEvaluation/test_response_quality_evaluation.py:31-127`) | Included in both model matrices via the 160-test AT subset (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:19-20,34-35`; `expert-agent-mcp-server/AGENT-LESSONS.md:460-472`) |
| Multi-turn context retention | AT1.12 explicitly covers multi-turn conversation, message ordering, and context retention through repeated `/sessions/{id}/messages` calls and subsequent history checks (`expert-agent-mcp-server/tests/application/AT1.12_MultiTurnConversation/test_AT1_12_real.py:19-21,311-365,368-428,435-490`) | Included in both model matrices (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:19-20`; `expert-agent-mcp-server/AGENT-LESSONS.md:460-472`) |
| MCP/session tool workflows | AT1.11 is the dedicated MCP tool workflow suite and exercises session creation, message insertion, status retrieval, and history retrieval through the API contracts used by MCP tool surfaces (`expert-agent-mcp-server/tests/application/AT1.11_MCPToolWorkflows/test_mcp_tool_workflows.py:15-32,138-176,179-219`) | Included in both model matrices (`cloud-dog-ai-platform-standards/working/W28A-926b-EXPERT-AGENT-LLM-OPENROUTER-REPORT.md:19-20`; `expert-agent-mcp-server/AGENT-LESSONS.md:460-472`) |
| Multi-stage orchestration with external tool calls | The architecture defines transactional execution as a staged pipeline of pre-service calls, delegations, LLM generation, and post-service calls, and AT1.124 exercises that flow with an external file MCP service plus a delegated child expert (`expert-agent-mcp-server/docs/ARCHITECTURE.md:347-355,483-495`, `expert-agent-mcp-server/tests/application/AT1.124_RealServiceOrchestration/test_directory_processor.py:59-68,110-162`) | Covered by orchestration application tests, but not part of the 160-test LLM matrix subset (`expert-agent-mcp-server/tests/application/AT1.124_RealServiceOrchestration/test_directory_processor.py:18-22,130-168`) |
| Expert delegation with default depth 3 | Defaults, env reference, and parameter reference all pin `max_delegation_depth=3`; runtime enforcement is implemented in `DelegationManager`, unit tests bind `max_depth=3`, and AT1.124 demonstrates the live delegation path at depth 1 (`expert-agent-mcp-server/defaults.yaml:101-107`, `expert-agent-mcp-server/docs/ENV-REFERENCE.md:262`, `expert-agent-mcp-server/docs/PARAMETERS.md:262`, `expert-agent-mcp-server/src/core/expert/delegation.py:74-76,95-114`, `expert-agent-mcp-server/tests/unit/UT1.97_DelegationManager/test_delegation.py:39-49`, `expert-agent-mcp-server/tests/application/AT1.124_RealServiceOrchestration/test_directory_processor.py:106-158`) | Depth-3 support is configuration-backed and unit-covered; the preserved application evidence exercises live delegation at depth 1 rather than depth 3 |

## Downstream Dependencies

- LLM usage is central to this service's runtime: architecture maps LLM integration to `src/common/llm_client.py` and `src/core/llm/`, and the shared LLM client is the service-wide abstraction (`expert-agent-mcp-server/docs/ARCHITECTURE.md:101-109`, `expert-agent-mcp-server/src/common/llm_client.py:18-20,58-59`).
- The current repo state does **not** support the instruction's proposed "leaf / no downstream MCP calls" claim. The architecture explicitly models external MCP, A2A, and REST tool services, `discover_tools()` / `invoke_tool()` against remote MCP services, and transactional orchestration over those bound services (`expert-agent-mcp-server/docs/ARCHITECTURE.md:335,357-363,377-378,483-490`).
- AT1.124 confirms this with live evidence: it registers an external service of type `mcp`, binds it to an expert, executes `list_dir` and `read_file` service calls, and returns those invocations inside `services_invoked` (`expert-agent-mcp-server/tests/application/AT1.124_RealServiceOrchestration/test_directory_processor.py:59-68,101-123,154-162`).
- expert-agent is therefore documented here as both:
  - a **provider** of MCP/API/A2A surfaces to upstream callers (`expert-agent-mcp-server/docs/ARCHITECTURE.md:9-13`, `expert-agent-mcp-server/src/servers/mcp/server.py:680-830,884-910`)
  - a **consumer** of downstream LLM and external-service dependencies when orchestration is enabled (`expert-agent-mcp-server/docs/ARCHITECTURE.md:13,335,357-363`)

## Known Issues

- The service uses `cloud_dog_llm` for LLM abstraction, but its MCP transport layer remains a bespoke server-side implementation pending later migration work (`expert-agent-mcp-server/src/servers/mcp/server.py:457-550,680-830,884-910`, `cloud-dog-ai-platform-standards/working/W28A-927m-MCP-TRANSPORT-5-SERVICE-AUDIT-REPORT.md:30,53-54`).
- The committed `tests/env-AT*` files preserve only the Ollama/qwen3 default baseline. Non-baseline Ollama rows from W28A-926a and all OpenRouter rows from W28A-926b were validated via runtime or generated env overrides rather than committed per-model env files (`expert-agent-mcp-server/tests/env-AT:37-40,61-67`, `cloud-dog-ai-platform-standards/working/W28A-926a-EXPERT-AGENT-LLM-OLLAMA-REPORT.md:24-34,126-130`, `expert-agent-mcp-server/AGENT-LESSONS.md:443-447`).
- Delegation depth 3 is clearly configured and unit-tested, but the preserved application-test evidence currently demonstrates live delegation at depth 1 rather than a depth-3 scenario (`expert-agent-mcp-server/src/core/expert/delegation.py:74-76`, `expert-agent-mcp-server/tests/unit/UT1.97_DelegationManager/test_delegation.py:39-49`, `expert-agent-mcp-server/tests/application/AT1.124_RealServiceOrchestration/test_directory_processor.py:106-158`).

## Cross-links

- Platform LLM interface standard: `cloud-dog-ai-platform-standards/docs/standards/50-llm-interfaces.md`
- Platform LLM reference design: `cloud-dog-ai-platform-standards/docs/reference-designs/llm-reference.md`
- Service parameter reference: `expert-agent-mcp-server/docs/PARAMETERS.md`
- Service environment reference: `expert-agent-mcp-server/docs/ENV-REFERENCE.md`
- Service requirements: `expert-agent-mcp-server/docs/REQUIREMENTS.md`
- Service architecture: `expert-agent-mcp-server/docs/ARCHITECTURE.md`
