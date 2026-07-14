# Codebase Reference: Redis Iris Agent

## 1. Project Overview

Redis Iris Agent is a Pydantic AI-powered conversational agent that lets users query live factory-floor data in plain English. It connects to the **Redis Iris Context Retriever** (a managed MCP server that auto-generates query tools from a Redis data model) and optionally to **Redis Iris Agent Memory** (a managed service for cross-session long-term memory). The included demo dataset models a predictive-maintenance scenario for a fictional company, CrestForge Industries, with machines, alerts, work orders, technicians, spare parts, and fault history.

The system ships in two runtime modes: an interactive terminal REPL (`iris-agent`) and a FastAPI HTTP server with Server-Sent Events streaming (`iris-api`). Both modes share the same agent core.

---

## 2. Directory Structure

```
src/
├── __init__.py                  # Package root — sets __version__ = "0.1.0"
│
├── agent/                       # Core agent logic (model, tools, prompts, CLI)
│   ├── __init__.py              # Re-exports build_agent, build_toolset, main
│   ├── config.py                # Settings dataclass + load_settings() from env
│   ├── model_provider.py        # LLM model factory (Anthropic / OpenAI / OpenRouter / Google)
│   ├── prompts.py               # All prompt strings and CLI help text (no logic)
│   ├── memory.py                # Agent Memory client wrapper (Identity, MemoryService)
│   ├── agent.py                 # Agent construction: build_toolset(), build_agent()
│   └── cli.py                   # Interactive terminal REPL — entry point "iris-agent"
│
├── api/                         # FastAPI HTTP server
│   ├── __init__.py              # Module docstring only
│   ├── models.py                # Pydantic request/response schemas
│   ├── state.py                 # AppState dataclass + create_state() startup factory
│   └── app.py                   # FastAPI routes, SSE streaming — entry point "iris-api"
│
├── utils/                       # Shared utilities
│   ├── __init__.py              # Module docstring only
│   └── tool_names.py            # safe_name_map() — sanitise MCP tool names for LLMs
│
└── crestforge/                  # Demo dataset provisioning and seeding
    ├── __init__.py              # Module docstring only
    ├── configure.py             # Provision the Context Surface + mint an agent key
    └── seed.py                  # Seed Redis JSON data + pre-seed Agent Memory
```

---

## 3. Module-by-Module Breakdown

### `src/__init__.py`
**Purpose:** Package marker. Sets `__version__ = "0.1.0"`.  
**Key symbols:** `__version__`  
**Dependencies:** None.

---

### `src/agent/config.py`
**Purpose:** Loads and validates all runtime settings from environment variables (via `python-dotenv`). Acts as the single source of truth for configuration; every other module that needs env values imports from here.

**Key symbols:**
- `DEFAULT_MCP_URL = "https://gcp-us-east4.context-surfaces.redis.io/mcp"` — fallback MCP endpoint.
- `ConfigError(RuntimeError)` — raised when `CONTEXT_RETRIEVER_AGENT_KEY` is absent.
- `Settings` (dataclass, slots) — holds `agent_key`, `mcp_url`, and three optional Agent Memory fields (`memory_endpoint`, `memory_store_id`, `memory_key`). The computed property `memory_enabled` returns `True` only when all three memory fields are set.
- `load_settings() -> Settings` — calls `load_dotenv()`, reads env vars, raises `ConfigError` on missing required values.

**Environment variables read:** `CONTEXT_RETRIEVER_AGENT_KEY` (required), `CTX_MCP_URL`, `AGENT_MEMORY_ENDPOINT`, `AGENT_MEMORY_STORE_ID`, `AGENT_MEMORY_KEY`.

**Imported by:** `agent.py`, `cli.py`, `api/state.py`, `crestforge/configure.py`, `crestforge/seed.py`.

---

### `src/agent/model_provider.py`
**Purpose:** Builds a provider-agnostic Pydantic AI `Model` object from env vars. Isolates all provider-specific imports into private builder functions so the rest of the codebase never touches provider SDKs directly.

**Key symbols:**
- `OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"` — base URL for OpenRouter.
- `ModelConfigError(ValueError)` — raised when `PROVIDER`, `MODEL_NAME`, or `API_KEY` is missing/unsupported.
- `build_model() -> Model` — reads `PROVIDER`, `MODEL_NAME`, `API_KEY` and dispatches to one of four builder functions.
- `_anthropic_model()` — returns `AnthropicModel` via `AnthropicProvider`.
- `_openai_model()` — returns `OpenAIChatModel` via `OpenAIProvider`.
- `_openrouter_model()` — returns `OpenAIChatModel` via `OpenAIProvider` pointed at OpenRouter.
- `_google_model()` — returns `GeminiModel` via `GoogleProvider`.

**Supported providers:** `anthropic`, `openai`, `openrouter`, `google`.

**Environment variables read:** `PROVIDER`, `MODEL_NAME`, `API_KEY`.

**Imported by:** `agent.py`, `cli.py`, `api/state.py`.

---

### `src/agent/prompts.py`
**Purpose:** Central store for all user-facing strings and LLM prompts. No logic; import constants only.

**Key symbols:**
- `SYSTEM_PROMPT` — tells the LLM it is a data assistant connected to Context Retriever over MCP. Describes the four tool-name conventions (`get_`, `filter_`, `search_`, `find_...range`), instructs the model to ground answers in live data, and to admit gaps.
- `MEMORY_PROMPT` — addendum injected when Agent Memory is enabled. Explains `search_memory` and `store_memory` tools and when to use them.
- `HELP` — Rich-formatted help text shown by the CLI `/help` command.

**Imported by:** `agent.py`, `cli.py`.

---

### `src/agent/memory.py`
**Purpose:** Thin wrapper over the `redis-agent-memory` SDK. Manages two memory layers: session (short-term, TTL-scoped per session) and long-term (cross-session, semantic search per user). The SDK library is an optional dependency; if absent, the module sets `AgentMemory = None` and raises a clear error only when memory is actually requested.

**Key symbols:**
- `Identity` (dataclass) — holds `owner_id` (user identity, stable across sessions) and `session_id` (mutable; rotated by `/newsession` / `/newshift`). Mutable by design for the cross-session recall demo.
- `MemoryService` — wraps an `AgentMemory` client bound to an `Identity`.
  - `from_settings(settings, identity) -> MemoryService` — class method; instantiates the SDK client from `Settings`.
  - `health() -> bool` — async reachability check; never raises.
  - `log_turn(role, text)` — async; appends a message event to session memory. Swallows all errors so logging never breaks the chat loop.
  - `search(query) -> str` — semantic search over this user's long-term memory; filters by `owner_id`.
  - `store(fact) -> str` — creates one long-term memory entry for this user; ID is `"{owner_id}-{ts_ms}"`.
- `_to_text(obj) -> str` — coerces SDK responses (Pydantic models or plain objects) to JSON strings for the LLM.
- `_now_ms() -> int` — current Unix timestamp in milliseconds.

**Optional dependency:** `redis_agent_memory` (from `redis-agent-memory` package). Import errors are caught silently; `AgentMemory` is set to `None`.

**Imported by:** `agent.py`, `cli.py`, `api/state.py`.

---

### `src/agent/agent.py`
**Purpose:** Constructs the Pydantic AI `Agent` and the MCP `MCPToolset`. This is the only place where the two are wired together.

**Key symbols:**
- `build_toolset(settings) -> MCPToolset` — creates an `MCPToolset` pointed at `settings.mcp_url` with `X-API-Key: {settings.agent_key}` header. The toolset connects to the Context Retriever MCP server.
- `build_agent(settings, toolset, memory=None) -> Agent` — assembles the Pydantic AI `Agent`. Calls `build_model()` for the LLM, sets the system instructions to `SYSTEM_PROMPT` (plus `MEMORY_PROMPT` when memory is enabled), and registers the `MCPToolset`. If `memory` is not `None`, calls `_attach_memory_tools()`.
- `_attach_memory_tools(agent, memory)` — registers two `@agent.tool_plain` async tools (`search_memory`, `store_memory`) that delegate to `MemoryService.search()` / `MemoryService.store()`. User identity is captured by closure; the LLM never sees or controls it.

**Imports:** `pydantic_ai.Agent`, `pydantic_ai.mcp.MCPToolset`, `config.Settings`, `model_provider.build_model`, `prompts.{MEMORY_PROMPT,SYSTEM_PROMPT}`, `memory.MemoryService` (TYPE_CHECKING only).

**Imported by:** `cli.py`, `api/state.py`, `agent/__init__.py`.

---

### `src/agent/cli.py`
**Purpose:** Interactive terminal REPL using `prompt_toolkit` for input and `rich` for output. Maintains full `message_history` across turns and supports a set of slash commands.

**Key symbols:**
- `DEFAULT_OWNER_ID = "machine-floor"` / `DEFAULT_SESSION_ID = "session-1"` — hardcoded demo identity; must match `MEMORY_OWNER` in `seed.py` so pre-seeded memories are found.
- `_MAX_INPUT = 8_000` — maximum user input length (truncated silently).
- `_banner(settings, identity, memory_on) -> Panel` — renders the startup Rich panel.
- `_render_tool_calls(new_messages)` — prints a dim `↳ <tool_name> <args>` line for each `ToolCallPart` in the agent's last response.
- `_list_tools(toolset)` — async; fetches and renders a Rich table of all Context Retriever tools.
- `_run() -> int` — async main loop. Loads settings, builds toolset, applies `safe_name_map`, builds agent + optional memory, then enters the `prompt_toolkit` REPL.
- `main()` — sync entry point (`iris-agent` console script). Silences `mcp.client.streamable_http` logger to suppress harmless 404s on session close.

**Slash commands handled:**
| Command | Effect |
|---|---|
| `/help` | Print `HELP` constant |
| `/tools` | List MCP tools |
| `/clear` | Clear `history` list |
| `/machine <id>` | Set `active_machine` (prepended to next prompt) |
| `/whoami` | Print identity, session, machine, memory status |
| `/newshift` / `/newsession` | Clear history + machine, increment session_id suffix |
| `/exit` / `/quit` | Return 0 |

**Imports:** `agent.{build_agent,build_toolset}`, `config.{ConfigError,Settings,load_settings}`, `memory.{Identity,MemoryService}`, `model_provider.ModelConfigError`, `prompts.HELP`, `utils.tool_names.safe_name_map`.

**Entry point:** `iris-agent` → `src.agent.cli:main`.

---

### `src/utils/tool_names.py`
**Purpose:** Sanitises MCP tool names so they satisfy Anthropic's and OpenAI's `^[a-zA-Z0-9_-]{1,128}$` constraint. The Context Retriever can generate names with spaces (e.g. `get_job queue_by_id`), which LLM provider APIs reject.

**Key symbols:**
- `_SAFE_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")` — the allowed pattern.
- `safe_name_map(tool_names: list[str]) -> dict[str, str]` — returns `{safe_name: original_name}` for every tool name that needs renaming. Replaces invalid chars with `_`, truncates to 128 characters, and appends `_2`, `_3`, … to resolve collisions. Only names that need renaming appear in the map; the caller passes it to `toolset.renamed(name_map)`.

**Imported by:** `cli.py`, `api/state.py`.

---

### `src/api/models.py`
**Purpose:** Pydantic schemas for the HTTP API request/response bodies.

**Key symbols:**
- `ChatRequest(BaseModel)` — `message: str`. Body for `POST /chat` and `POST /chat/sync`.
- `SetMachineRequest(BaseModel)` — `machine_id: str`. Body for `POST /session/machine`.
- `SessionInfo(BaseModel)` — `owner_id`, `session_id`, `active_machine`, `memory_on`, `history_length`, `tool_count`. Response schema for session endpoints.

**Imported by:** `api/app.py`.

---

### `src/api/state.py`
**Purpose:** Defines the single shared `AppState` object that lives for the lifetime of the FastAPI server. Mirrors the setup logic in `cli.py` but as a dataclass factory.

**Key symbols:**
- `DEFAULT_OWNER_ID = "machine-floor"` / `DEFAULT_SESSION_ID = "session-1"` — same as CLI defaults; shared identity for the demo.
- `AppState` (dataclass) — fields: `settings`, `toolset`, `agent`, `memory`, `identity`, `name_map`, `tool_names`, `active_machine` (mutable), `history: list[ModelMessage]` (mutable). All request handlers mutate `history` and `active_machine` in place.
- `create_state() -> tuple[AppState, list[str]]` — async factory called at server startup. Loads settings, builds toolset, lists tools, applies `safe_name_map`, optionally builds `MemoryService`, builds agent. Returns `(AppState, warnings)` where warnings are non-fatal issues (e.g. memory endpoint unreachable).

**Imported by:** `api/app.py`.

---

### `src/api/app.py`
**Purpose:** FastAPI application. Exposes the agent over HTTP with SSE streaming for the main chat endpoint. One global `_state: AppState | None` is set during lifespan.

**Key symbols:**
- `lifespan(app)` — async context manager (FastAPI lifespan). Calls `create_state()`, then enters `async with state.agent:` to keep the MCP connection open for the server lifetime. Sets `_state` to `None` on shutdown.
- `app` — `FastAPI` instance with CORS middleware (allow all origins for development).
- `_require_state()` — raises HTTP 503 if `_state` is `None` (startup not complete or failed).
- `_chat_sse(state, message)` — async generator; yields SSE events: `thinking`, one `tool_call` per MCP tool invoked, `text` (full answer), `done` (with session snapshot). Also logs turns to memory and updates `state.history`.

**API routes:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | SSE streaming chat |
| `POST` | `/chat/sync` | Synchronous chat (JSON response; for Swagger/Postman) |
| `GET` | `/session` | Returns current `SessionInfo` |
| `POST` | `/session/machine` | Sets `active_machine` |
| `POST` | `/session/new-shift` | Clears history + machine, increments session_id |
| `DELETE` | `/session/history` | Clears conversation history only |
| `GET` | `/tools` | Lists Context Retriever tools from MCP |
| `GET` | `/health` | Returns provider, model, mcp_url, memory_on, tool_count |

**Entry point:** `iris-api` → `src.api.app:main` (runs `uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload`).

---

### `src/crestforge/configure.py`
**Purpose:** One-time provisioning script. Creates (or updates) the "CrestForge Industries" Context Surface on Redis Cloud, waits for it to become active (up to 80 s), then mints a scoped agent key and writes it to `_agentkey.tmp` at the project root.

**Key symbols:**
- `SURFACE_NAME = "CrestForge Industries"` — display name of the Context Surface.
- `KEY_OUT` — path to `_agentkey.tmp` (git-ignored) relative to project root.
- Entity model classes (all extend `ContextModel` from `context_surfaces`):
  - `Machine` — `machine:{id}`, fields: id, name (text), type (tag), location (tag), status (tag), vibration_level (numeric), temperature_c (numeric), runtime_hours (numeric).
  - `Alert` — `alert:{id}`, fields: id, machine_id (tag), type (tag), severity (tag), status (tag), triggered_value (numeric), threshold (numeric).
  - `WorkOrder` — `work_order:{id}`, fields: id, machine_id (tag), technician_id (tag), type (tag), status (tag), priority (tag), description (text).
  - `FaultHistory` — `fault_history:{id}`, fields: id, machine_id (tag), fault_type (text), root_cause (text), resolution (text), downtime_hours (numeric).
  - `Technician` — `technician:{id}`, fields: id, name (text), specialty (tag), shift (tag), availability (tag), certifications (text).
  - `Part` — `part:{id}`, fields: id, name (text), category (tag), compatible_machine_type (tag), stock_level (numeric), reorder_point (numeric), lead_time_days (numeric).
- `ENTITIES = [Machine, Alert, WorkOrder, FaultHistory, Technician, Part]`
- `main() -> int` — async. Reads `CTX_ADMIN_KEY` and `REDIS_URL`, calls `ContextSurfacesClient` to list/create/update the surface, polls until `status == "active"`, then mints the agent key.

**CLI modes:**
- `python -m src.crestforge.configure` — create/update surface and mint agent key.
- `python -m src.crestforge.configure --probe` — list existing surfaces only.

**Environment variables read:** `CTX_ADMIN_KEY` (required), `REDIS_URL` (required).

**Entry point:** `crestforge-config` → `src.crestforge.configure:main`.

---

### `src/crestforge/seed.py`
**Purpose:** Populates Redis with the CrestForge demo dataset (as RedisJSON documents) and optionally pre-seeds six long-term memories into Agent Memory. Safe to rerun (upsert via `JSON.SET`).

**Key data constants:**
- `MACHINES` — 8 shop-floor machines (M104 Alpha Mill in `fault`, M312 Delta Comp, M207 Beta Press, M118 Gamma Belt, M225 Epsilon Arm, M401 Zeta Mill, M309 Eta Press, M502 Theta Conv).
- `ALERTS` — 3 sensor alerts (A301 critical vibration on M104, A308 warning temperature on M312, A295 resolved lubrication on M207).
- `WORK_ORDERS` — 3 work orders (WO1041 urgent repair for M104, WO1042 lubrication for M207, WO1038 completed inspection for M118).
- `FAULT_HISTORY` — 4 records (FH801 and FH802 for M104, FH810 for M312, FH795 for M207).
- `TECHNICIANS` — 5 technicians (T01 Marcus Webb mechanical, T03 Diana Cruz mechanical, T07 Rajan Patel hydraulic, T11 Sofia Lin electrical, T14 Owen Brandt pneumatic).
- `PARTS` — 5 spare parts (P201 SKF 6205 Bearing, P202 SKF 6305 Bearing, P310 Compressor Oil Seal, P411 Hydraulic Valve Seal, P508 Conveyor Drive Belt).
- `DATASET: dict[str, list[dict]]` — combines all the above for bulk loading.
- `MEMORY_OWNER = "machine-floor"` — must match `DEFAULT_OWNER_ID` in `cli.py` and `state.py`.
- `LONG_TERM_MEMORIES` — 6 pre-built institutional knowledge facts (M104 bearing diagnosis, M104 parts stock, M312 seal vs. refrigerant, M207 hydraulic specialist rule, M118 belt tension schedule, M225 calibration after firmware update).

**Key functions:**
- `get_client() -> redis.Redis` — reads `REDIS_URL`, connects, pings.
- `load(client, flush)` — optionally `FLUSHDB`, then upserts all DATASET entities as `JSON.SET` docs.
- `verify(client)` — scans key counts per entity and prints samples.
- `seed_memories()` — async; connects to Agent Memory and bulk-creates the 6 long-term memories. Uses timestamp-suffixed IDs for idempotency (service deduplicates by id).
- `main() -> int` — parses `--flush`, `--verify`, `--no-memory` flags, calls the above.

**CLI modes:**
- `python -m src.crestforge.seed` — upsert data + seed memories.
- `python -m src.crestforge.seed --flush` — FLUSHDB first, then seed.
- `python -m src.crestforge.seed --verify` — count and print samples only.
- `python -m src.crestforge.seed --no-memory` — skip Agent Memory seeding.

**Environment variables read:** `REDIS_URL` (required), `AGENT_MEMORY_ENDPOINT`, `AGENT_MEMORY_STORE_ID`, `AGENT_MEMORY_KEY`.

**Entry point:** `crestforge-seed` → `src.crestforge.seed:main`.

---

## 4. Data Flow

### CLI path

```
User types at terminal
        │
        ▼
cli.py  _run()          ← prompt_toolkit reads input
        │
        ├─ slash commands handled inline (no agent call)
        │
        ├─ memory.log_turn("user", ...)   [if memory enabled]
        │
        ▼
agent.py  agent.run(prompt, message_history=history)
        │
        ├─ Pydantic AI sends prompt + tool definitions to LLM
        │
        ▼
LLM decides which tool(s) to call
        │
        ▼
MCPToolset → HTTP POST to Context Retriever MCP (X-API-Key auth)
        │       URL: CTX_MCP_URL/mcp
        │
        ▼
Redis Iris Context Retriever executes query against Redis
        │  (JSON.GET, FT.SEARCH, FT.AGGREGATE depending on tool)
        │
        ▼
Tool result returned to LLM → final text response
        │
        ▼
cli.py  _render_tool_calls()   ← prints "↳ tool_name {args}"
        │
        ├─ console.print(Markdown(result.output))
        │
        ├─ memory.log_turn("assistant", ...)   [if memory enabled]
        │
        ▼
history = result.all_messages()   ← accumulated for next turn
```

### API (HTTP/SSE) path

```
HTTP POST /chat  {"message": "..."}
        │
        ▼
app.py  chat()  → _chat_sse(state, message)   [async generator]
        │
        ├─ yields  {"type": "thinking"}
        │
        ├─ state.memory.log_turn("user", ...)   [if memory enabled]
        │
        ▼
state.agent.run(prompt, message_history=state.history)
        │
        └─ (same LLM → MCP → Redis path as CLI)
        │
        ▼
for each ToolCallPart in result.new_messages():
        yields  {"type": "tool_call", "name": ..., "args": ...}
        │
        ▼
yields  {"type": "text", "content": result.output}
        │
        ├─ state.memory.log_turn("assistant", ...)   [if memory enabled]
        │
        ├─ state.history = result.all_messages()
        │
        ▼
yields  {"type": "done", "session": {...}}
```

### Memory recall flow (when Agent Memory is enabled)

```
Agent turn begins
        │
        ▼
LLM calls search_memory(query="...")    ← sees this tool alongside MCP tools
        │
        ▼
MemoryService.search()
  → AgentMemory.search_long_term_memory_async(
        filter={owner_id: {eq: identity.owner_id}})
        │
        ▼
Returns JSON of matching memories → LLM incorporates into answer
        │
        ▼
LLM optionally calls store_memory(fact="...")
        │
        ▼
MemoryService.store()
  → AgentMemory.bulk_create_long_term_memories_async([{id, owner_id, text}])
```

---

## 5. Key Abstractions

### `Settings` (agent/config.py)
Immutable runtime config. Validated once at startup; passed through the call chain to `build_toolset`, `build_agent`, `MemoryService.from_settings`. The `memory_enabled` property controls whether the memory branch is activated.

### `MCPToolset` (pydantic_ai.mcp)
Pydantic AI's built-in MCP client. Points at the Context Retriever HTTP endpoint and auto-discovers all tools at startup. The agent registers it via `toolsets=[toolset]`; all tool dispatch is handled transparently by the framework. When tool names contain spaces, `toolset.renamed(name_map)` returns a proxy that translates safe names back to originals on the wire.

### `Agent` (pydantic_ai)
The Pydantic AI agent. Holds the LLM model, toolsets, and system instructions. Runs an agentic loop internally: sends prompt + tool schemas → receives tool calls → executes tools → re-submits results until the model produces a final text response. Used as an async context manager (`async with agent:`) to keep the MCP connection alive.

### `Identity` + `MemoryService` (agent/memory.py)
Two-layer memory abstraction. `Identity` is a mutable value object that decouples user identity (`owner_id`) from the conversation session (`session_id`). `MemoryService` is bound to an `Identity` instance; all reads/writes are scoped to `owner_id` so the model can never cross user boundaries.

### `AppState` (api/state.py)
Single-instance server state. Acts as a simple in-process session store for the single-user demo. The FastAPI lifespan creates one `AppState` and all route handlers mutate it. In a multi-user deployment this would be replaced by per-request session lookup.

### Tool-name sanitisation (utils/tool_names.py)
Defensive preprocessing step. Context Retriever entity names may contain spaces; both Anthropic and OpenAI reject tool names that don't match `^[a-zA-Z0-9_-]{1,128}$`. `safe_name_map()` produces a `{safe: original}` dict that is applied via `toolset.renamed()` before the agent is constructed. Only affected names appear in the map.

### Index-type → tool-name convention (crestforge/configure.py)
The Context Retriever generates MCP tool names deterministically from field index types:

| Index type | Generated tool pattern | Query behaviour |
|---|---|---|
| `is_key_component=True` | `get_{entity}_by_id` | Exact key lookup |
| `tag` | `filter_{entity}_by_{field}` | Exact-match filter |
| `text` | `search_{entity}_by_text` | Full-text keyword search |
| `numeric` | `find_{entity}_by_{field}_range` | Range query |

---

## 6. Environment Variables

| Variable | Required | Where used | Purpose |
|---|---|---|---|
| `CONTEXT_RETRIEVER_AGENT_KEY` | Yes (agent runtime) | `config.py` | API key sent as `X-API-Key` to the Context Retriever MCP server |
| `CTX_MCP_URL` | No | `config.py` | Override the Context Retriever MCP endpoint (default: `https://gcp-us-east4.context-surfaces.redis.io/mcp`) |
| `PROVIDER` | Yes | `model_provider.py` | LLM provider: `anthropic`, `openai`, `openrouter`, `google` |
| `MODEL_NAME` | Yes | `model_provider.py` | Model identifier (e.g. `claude-sonnet-4-6`, `gpt-4o`, `gemini-2.0-flash`) |
| `API_KEY` | Yes | `model_provider.py` | API key for the chosen LLM provider |
| `AGENT_MEMORY_ENDPOINT` | No (enables memory) | `config.py`, `memory.py`, `seed.py` | Managed Agent Memory service URL |
| `AGENT_MEMORY_STORE_ID` | No (enables memory) | `config.py`, `memory.py`, `seed.py` | Memory store identifier |
| `AGENT_MEMORY_KEY` | No (enables memory) | `config.py`, `memory.py`, `seed.py` | API key for Agent Memory |
| `REDIS_URL` | Yes (seed/configure) | `seed.py`, `configure.py` | Redis Cloud connection string (e.g. `redis://default:pass@host:port`) |
| `CTX_ADMIN_KEY` | Yes (configure only) | `configure.py` | Admin key for the Context Surfaces management API |

All variables are loaded via `python-dotenv` from a `.env` file in the project root. All three `AGENT_MEMORY_*` vars must be present together; if any is missing, memory is silently disabled.

---

## 7. Entry Points

### Interactive CLI

```bash
iris-agent
# or directly:
python -m src.agent.cli
```

Starts the terminal REPL. Connects to the Context Retriever MCP server, loads the Pydantic AI agent, and enters a `prompt_toolkit` read loop. Exit with `/exit`, `/quit`, or Ctrl-D.

### FastAPI HTTP Server

```bash
iris-api
# or directly:
uvicorn src.api.app:app --reload
# or:
python -m src.api.app
```

Starts the server on `http://0.0.0.0:8000`. Interactive docs at `http://localhost:8000/docs`. The primary chat endpoint is `POST /chat` (SSE streaming) and `POST /chat/sync` (blocking JSON).

### Dataset Provisioning (one-time setup)

```bash
# 1. Create / update the Context Surface and mint an agent key:
crestforge-config
# or: python -m src.crestforge.configure

# 2. Seed Redis with demo data and pre-build Agent Memory:
crestforge-seed
# or: python -m src.crestforge.seed

# Variants:
python -m src.crestforge.seed --flush       # wipe Redis first
python -m src.crestforge.seed --verify      # count keys, no writes
python -m src.crestforge.seed --no-memory   # skip Agent Memory seeding
python -m src.crestforge.configure --probe  # list surfaces, no changes
```
