# Expert Agent — Orchestration Use Cases

Reference: W28A-874 FR-ORCH-01 through FR-ORCH-06

---

## Scenario 1: Web Content Pipeline

**Goal:** A controller expert researches a topic by searching the web, stores
extracted content, optionally translates it, and maintains a 90-day rolling
content log with visited-site deduplication.

### Actors
- **Operator** — triggers the pipeline via WebUI, REST, or MCP
- **Controller Expert** — orchestrates the workflow via prompt directives
- **search-mcp** — web search and content extraction (external MCP service)
- **file-mcp** — file storage and retrieval (external MCP service)
- **Translator Expert** — translates content to target language (sub-expert)

### Expert Configuration

```yaml
controller:
  name: "web-content-researcher"
  is_controller: true
  default_execution_mode: transactional
  context_retention: rolling
  context_retention_limit: 50
  bindings:
    - service: search-mcp    # priority 1
    - service: file-mcp      # priority 2
    - sub_expert: translator  # priority 3
  prompt: |
    You are a research coordinator. Your task is to research the given topic
    using web search, store the results, and optionally translate them.

    Available tools: {{available_tools}}
    Previously visited sites: {{context:variables.visited_sites}}

    Workflow:
    1. Search for the topic using the search tool. Skip sites already visited.
    2. Extract the top 3 results' content.
    3. Write each result to file storage using file-mcp write_file.
    4. If translation is requested, delegate to the translator expert.
    5. Update the visited_sites list.
    6. Return a summary of what was found, stored, and translated.
```

### Execution Flow

1. Operator sends: `POST /experts/{id}/execute`
   ```json
   {
     "input_text": "Research advances in quantum error correction in 2026",
     "parameters": {"translate": "fr"},
     "context": {
       "variables": {"visited_sites": ["arxiv.org/2601.12345"]},
       "context_group_id": "research-quantum-2026"
     }
   }
   ```

2. Controller expert receives prompt with `{{available_tools}}` expanded to
   include `search`, `write_file`, `read_file`, `delegate_to_expert`.

3. LLM emits tool calls:
   - `search(query="quantum error correction 2026", max_results=5)` → search-mcp
   - `write_file(path="/research/quantum-ec-20260410.md", content="...")` → file-mcp
   - `delegate_to_expert(expert="translator", input="...", parameters={"target_lang":"fr"})` → translator expert

4. Each tool call routes through `ServiceCompositionManager` (for services) or
   `DelegationManager` (for sub-experts). Results flow back into the LLM context.

5. LLM produces final summary. Controller updates visited_sites via knowledge base.

6. Response returned to operator with `output_text`, `services_invoked`, `delegations`.

### Knowledge Management

- **visited_sites** — session-scoped knowledge entry, updated per run
- **content_log** — 90-day rolling log stored via `KnowledgeHistoryManager`
  with `retention_days=90` and `knowledge_type=research_log`
- **context_group_id** — `"research-quantum-2026"` links multiple runs so
  the controller can build on prior research without re-fetching

### Re-Run Behaviour

On subsequent runs with the same `context_group_id`:
1. Controller reads `visited_sites` from context variables
2. Search results filtered against already-visited URLs
3. Only new content is stored and translated
4. Content log appended (not replaced)

---

## Scenario 2: File Processing Pipeline

**Goal:** A controller expert receives a directory path, lists files, processes
each file through a specialist expert, aggregates results, and writes a summary.

### Actors
- **Operator** — triggers via REST or scenario runner
- **Controller Expert** — orchestrates per-file processing
- **file-mcp** — file listing and read/write (external MCP service)
- **Analyser Expert** — processes individual file content (sub-expert)

### Scenario Definition

```yaml
scenario:
  name: "file-processing-pipeline"
  version: 1
  description: "Process all files in a directory through an analyser expert"
  steps:
    - id: list_files
      type: service
      service: file-mcp
      tool: dir_list
      input: { path: "${input.directory_path}", recursive: false }
      output: file_list
      on_error: abort

    - id: process_each
      type: expert
      expert: analyser
      input: "Analyse this file content and extract key findings: ${step.file_content}"
      for_each: "${file_list.files}"
      pre_step:
        service: file-mcp
        tool: read_file
        input: { path: "${item.path}" }
        output: file_content
      output: analysis_results
      on_error: skip

    - id: aggregate
      type: expert
      expert: web-content-researcher
      input: |
        Summarise these analysis results into a single report:
        ${analysis_results}
      output: summary_report
      on_error: abort

    - id: write_report
      type: service
      service: file-mcp
      tool: write_file
      input:
        path: "${input.directory_path}/analysis-report.md"
        content: "${summary_report}"
      output: report_path
      on_error: abort
```

### Execution Flow

1. Operator invokes: `POST /scenarios/file-processing-pipeline/run`
   ```json
   { "input": { "directory_path": "/data/invoices/2026-q1" } }
   ```

2. Scenario engine creates a parent session.

3. Step 1 (`list_files`): `ServiceCompositionManager.invoke_tool("file-mcp", "dir_list", ...)`
   → returns `{files: [{path: "/data/invoices/2026-q1/inv001.pdf", ...}, ...]}`.

4. Step 2 (`process_each`): For each file in `file_list.files`:
   - Pre-step reads file content via `file-mcp.read_file`
   - Analyser expert processes content via `TransactionalExecutor.execute()`
   - Each iteration creates a child session
   - Results collected into `analysis_results` array

5. Step 3 (`aggregate`): Controller expert summarises all results.

6. Step 4 (`write_report`): Summary written to file-mcp.

7. Parent session contains the full delegation tree.

### Error Handling

- Step 1 (`list_files`): `on_error: abort` — pipeline stops if directory listing fails
- Step 2 (`process_each`): `on_error: skip` — individual file failures don't stop the pipeline;
  failed files are logged and excluded from aggregation
- Step 3/4: `on_error: abort` — aggregation/write failures stop the pipeline

---

## Scenario 3: Chat-Client Integration

**Goal:** chat-client configures expert-agent as an MCP server. Users chat
through the chat-client WebUI; messages are forwarded to expert-agent which
orchestrates sub-experts and services, with responses flowing back to the user.

### Actors
- **End User** — interacts via chat-client WebUI
- **chat-client** — proxy layer, session management, WebUI
- **expert-agent** — configured as MCP server for chat-client
- **Sub-Experts** — domain specialists delegated to by the controller
- **External Services** — search-mcp, file-mcp, sql-agent, etc.

### Configuration

**chat-client side:**
```yaml
mcp:
  servers:
    - name: expert-agent
      transport: streamable_http
      base_url: https://expertagent.example.com/mcp
      api_key_header: X-API-Key
      api_key: ${vault.dev.models.expert_agent.api_key}
```

**expert-agent side:**
```yaml
controller:
  name: "assistant"
  is_controller: true
  default_execution_mode: chat
  context_retention: rolling
  context_retention_limit: 30
  bindings:
    - service: search-mcp    # web search
    - service: file-mcp      # file operations
    - service: sql-agent     # database queries
    - sub_expert: translator  # translation
    - sub_expert: summariser  # summarisation
```

### Message Flow

```
User (browser)
  │ "Find quarterly revenue from the database and write a report"
  │
  ▼
chat-client WebUI
  │ POST /sessions/{id}/messages/stream
  │ → chat-client API creates user message
  │ → chat-client calls expert-agent via MCP
  │
  ▼
expert-agent MCP server
  │ tools/call chat {expert_id, session_id, message}
  │ → SessionManager creates/resumes session
  │ → LLM receives prompt + context + tool surface
  │
  ▼
LLM decides tool calls:
  │ 1. sql-agent.execute_query("SELECT quarter, revenue FROM financials")
  │ 2. delegate_to_expert("summariser", "Summarise: ${query_results}")
  │ 3. file-mcp.write_file("/reports/q1-revenue.md", "${summary}")
  │
  ▼
expert-agent returns response to chat-client
  │ {output_text, tool_calls: [...], delegations: [...]}
  │
  ▼
chat-client WebUI
  │ Renders assistant message with:
  │   - Response text
  │   - Tool call details (expandable)
  │   - Sub-expert delegation details (expandable)
  │
  ▼
User sees complete response with full audit trail
```

### Session Management

- **chat-client session:** Maintains the user-facing conversation history.
  Messages include the expert-agent response and metadata about tool calls.
- **expert-agent session:** Maintains the expert's conversation history with
  full context including tool results and delegation outputs. Linked to
  chat-client session via `correlation_id`.
- **Sub-expert sessions:** Child sessions created per delegation, linked
  via `parent_session_id` for audit.

### Context Continuity

Follow-up messages in the same chat-client session reuse the same
expert-agent session (via `session_id` in the MCP call). The expert-agent's
rolling context window retains the last 30 messages, with older messages
summarised by `SessionManager.summarize()`.

This enables multi-turn workflows:
1. "Find quarterly revenue" → sql-agent query → results
2. "Now compare to last year" → same session, context preserved
3. "Write a report with both" → file-mcp write, using accumulated context

---

## WebUI Enhancement Outline (D4)

Pages/components needed to support FR-ORCH-01 through FR-ORCH-06:

| Page/Component | Description | @cloud-dog/ui Components |
|----------------|-------------|--------------------------|
| Expert Composition Editor | Priority-ordered binding manager on Expert detail page | `DataTable` (drag-reorder), `EntityDialog`, `Badge` (service type) |
| Controller Toggle | Expert form field to mark `is_controller`, set `default_execution_mode`, `context_retention` | `Select`, `Switch`, `Input` |
| Composition Topology View | Visual graph of expert → sub-experts → services | Custom SVG/Canvas component (new) |
| Scenarios Page | Scenario CRUD with DataTable listing | `DataTable`, `EntityDialog`, `Badge` |
| Scenario Step Editor | Ordered step list with conditional branching | `DataTable` (drag-reorder), `EntityDialog`, `Select`, `JsonBlock` |
| Scenario Runner | Execute scenario with real-time step progress | `Progress`, `Badge` (step status), `JsonBlock` (step output), `Card` |
| Chat Timeline Enhancement | Tool calls and delegations inline in chat | `ChatMessage`, `ToolCallPanel`, `Badge`, `JsonBlock` |
| Context Inspector | View/edit context variables for a session | `JsonBlock`, `DataTable`, `EntityDialog` |

## Test Plan Outline (D5)

### FR-ORCH-01: Expert Composition

| Category | Test |
|----------|------|
| API | Create expert with multiple service + sub-expert bindings at different priorities |
| API | Verify unified tool surface returns tools in priority order |
| API | Verify name collision resolution — highest priority wins |
| WebUI | Binding editor creates, reorders, and removes bindings |

### FR-ORCH-02: Controller Orchestration

| Category | Test |
|----------|------|
| API | Controller expert delegates to sub-expert via LLM-emitted tool call |
| API | Loop detection blocks self-referencing controller chains |
| API | Max depth enforcement on controller delegation |
| Integration | Controller calls 2+ sub-experts in sequence within a single prompt execution |

### FR-ORCH-03: Execution Modes

| Category | Test |
|----------|------|
| API | Execute expert in transactional mode — verify single-shot result |
| API | Execute expert in chat mode — verify multi-turn context retention |
| API | Execute expert in hybrid mode — verify per-turn pre/post service calls |
| API | Override default mode per invocation |

### FR-ORCH-04: Remote Execution with Context

| Category | Test |
|----------|------|
| API | Pass prior_messages in context — verify LLM receives them |
| API | Pass documents in context — verify they appear in prompt |
| API | Pass variables — verify prompt interpolation |
| API | Context retention: none — verify context discarded between calls |
| API | Context retention: rolling — verify only last N messages kept |
| API | Context group — verify two sessions with same group_id share knowledge |
| MCP | Execute via MCP tools/call with same context payload |

### FR-ORCH-05: Scenario Workflows

| Category | Test |
|----------|------|
| API | Create scenario with 3 steps — verify CRUD |
| API | Execute scenario — verify steps run in order |
| API | Conditional step — verify skip when condition is false |
| API | Error handling: retry step, skip step, abort scenario |
| API | For-each step — verify iteration over array output |
| Integration | End-to-end scenario with file-mcp + sub-expert |
| WebUI | Scenario designer creates steps with drag-and-drop |
| WebUI | Scenario runner shows real-time progress |

### FR-ORCH-06: Prompt Integration

| Category | Test |
|----------|------|
| API | `{{available_tools}}` expands to bound tool list |
| API | `{{service:search-mcp:tools}}` expands to search-mcp tools only |
| API | `{{expert:translator:capabilities}}` expands to sub-expert info |
| API | `{{context:variables}}` expands to current context variables |
| API | `{{scenario:current_step}}` expands during scenario execution |
| API | `{{scenario:prior_outputs}}` includes outputs from completed steps |
